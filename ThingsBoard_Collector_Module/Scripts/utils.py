#!/usr/bin/env python3
"""
Utility functions for ThingsBoard data collection system.
Contains Kafka operations, alarm processing, and thread management logic.

"""

import json
import logging
import hashlib
import threading
from datetime import datetime, timezone
from collections import deque
from typing import Dict, Set, Deque
from confluent_kafka import Producer, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic

from thingsboard_api import ThingsBoardClient

logger = logging.getLogger(__name__)
MAX_SEEN_ALARM_HASHES = 5000 

def ensure_kafka_topic(topic_name: str, bootstrap_servers: str) -> bool:
    """
    Ensure a Kafka topic exists. Create it if it doesn't.
    
    Args:
        topic_name: Name of the Kafka topic
        bootstrap_servers: Kafka bootstrap servers address
        
    Returns:
        True if topic exists or was created successfully
    """
    try:
        admin = AdminClient({'bootstrap.servers': bootstrap_servers})
        
        metadata = admin.list_topics(timeout=5)
        if topic_name in metadata.topics:
            logger.debug(f"Topic '{topic_name}' already exists")
            return True
        
        new_topic = NewTopic(
            topic=topic_name,
            num_partitions=1,
            replication_factor=1
        )
        
        fs = admin.create_topics([new_topic])
        
        # Wait for operation to complete
        for topic, f in fs.items():
            try:
                f.result()
                logger.info(f"✅ Created Kafka topic: {topic}")
                return True
            except Exception as e:
                logger.error(f"❌ Failed to create topic {topic}: {e}")
                return False
                
    except KafkaException as e:
        logger.error(f"❌ Kafka error while ensuring topic: {e}")
        return False


def publish_to_kafka(topic: str, data: Dict, bootstrap_servers: str) -> bool:
    """
    Publish data to a Kafka topic.
    
    Args:
        topic: Kafka topic name
        data: Dictionary to publish as JSON
        bootstrap_servers: Kafka bootstrap servers address
        
    Returns:
        True if published successfully
    """
    producer = Producer({
        'bootstrap.servers': bootstrap_servers,
        'linger.ms': 5,
        'compression.type': 'zstd'
    })
    
    def delivery_callback(err, msg):
        """Callback for message delivery confirmation."""
        if err:
            logger.error(f"❌ Message delivery failed: {err}")
        else:
            logger.debug(f"✅ Message delivered to {msg.topic()} [{msg.partition()}]")
    
    try:
        message = json.dumps(data, ensure_ascii=False).encode('utf-8')
        
        producer.produce(
            topic,
            value=message,
            callback=delivery_callback
        )
        
        producer.flush(timeout=10)
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to publish to Kafka: {e}")
        return False


def generate_alarm_hash(alarm: Dict) -> str:
    """
    Generate MD5 hash for an alarm to detect duplicates.
    
    Args:
        alarm: Alarm dictionary from ThingsBoard
        
    Returns:
        MD5 hash string
    """
    alarm_id = alarm.get('id', {}).get('id', '')
    alarm_type = alarm.get('type', '')
    created_time = alarm.get('createdTime', '')
    
    unique_string = f"{alarm_id}_{alarm_type}_{created_time}"
    return hashlib.md5(unique_string.encode('utf-8')).hexdigest()


def continuous_poll_device(config: Dict, stop_event: threading.Event, 
                          active_devices: Dict, active_devices_lock: threading.Lock,
                          kafka_bootstrap: str, poll_interval: int, tb_username: str, 
                          tb_password: str):
    """
    Continuously poll ThingsBoard for device alarms and publish to Kafka.
    Runs in a separate thread per device.
    
    Args:
        config: Configuration dictionary with TB connection details
        stop_event: Threading event to signal stop
        active_devices: Shared dictionary tracking active devices
        active_devices_lock: Lock for thread-safe access to active_devices
        kafka_bootstrap: Kafka bootstrap servers address
        poll_interval: Seconds between polls
        tb_username: ThingsBoard username
        tb_password: ThingsBoard password
    """
    entity_id = config['entityId']
    entity_type = config.get('entityType', 'DEVICE')
    topic_name = f"thingsboard_{entity_id}"
    
    logger.info(f"🔄 Starting continuous polling for device {entity_id}")
    
    # Mark as running (if still registered)
    with active_devices_lock:
        if entity_id in active_devices:
            active_devices[entity_id]['status'] = 'running'
    
    # If a stop was requested during startup, exit quickly without doing network work
    if stop_event.is_set():
        logger.info(f"🛑 Stop requested before polling loop started for device {entity_id}")
        with active_devices_lock:
            if entity_id in active_devices:
                active_devices[entity_id]['status'] = 'stopped'
        return
    
    # Initialize ThingsBoard client
    tb_client = ThingsBoardClient(
        host=config['thingsboardsIP'],
        port=config['thingsboardPort'],
        username=tb_username,
        password=tb_password
    )
    
    if not tb_client.authenticate():
        logger.error(f"❌ Failed initial authentication for device {entity_id}")
        with active_devices_lock:
            if entity_id in active_devices:
                active_devices[entity_id]['status'] = 'error'
        return
    
    # Avoid duplicates - bounded memory (simple LRU - Least Recently Used)
    seen_alarm_hashes: Set[str] = set()
    seen_alarm_hashes_queue: Deque[str] = deque()
    
    total_polls = 0
    total_alarms_published = 0
    
    while not stop_event.is_set():
        try:
            total_polls += 1
            
            # Get alarms from ThingsBoard
            alarms_data = tb_client.get_alarms(
                entity_id=entity_id,
                entity_type=entity_type,
                status="ACTIVE_UNACK"
            )
            
            if not alarms_data:
                logger.warning(f"⚠️ No data received from ThingsBoard for {entity_id}")
                stop_event.wait(poll_interval)
                continue
            
            # Filter new alarms
            all_alarms = alarms_data.get('data', [])
            new_alarms = []
            
            for alarm in all_alarms:
                alarm_hash = generate_alarm_hash(alarm)
                if alarm_hash not in seen_alarm_hashes:
                    new_alarms.append(alarm)
                    
                    seen_alarm_hashes.add(alarm_hash)
                    seen_alarm_hashes_queue.append(alarm_hash)
                    
                    if len(seen_alarm_hashes_queue) > MAX_SEEN_ALARM_HASHES:
                        old_hash = seen_alarm_hashes_queue.popleft()
                        seen_alarm_hashes.discard(old_hash)
            
            # New alarms to Kafka
            if new_alarms:
                kafka_payload = {
                    "source": "thingsboard",
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "collection_timestamp": datetime.now(timezone.utc).isoformat(),
                    "alarms": new_alarms,
                    "total_alarms": len(new_alarms)
                }
                
                if publish_to_kafka(topic_name, kafka_payload, kafka_bootstrap):
                    total_alarms_published += len(new_alarms)
                    logger.info(f"📤 Published {len(new_alarms)} new alarm(s) for {entity_id}")
            
            # Update device stats
            with active_devices_lock:
                if entity_id in active_devices and active_devices[entity_id]['status'] == 'running':
                    active_devices[entity_id]['last_poll'] = datetime.now(timezone.utc)
                    active_devices[entity_id]['total_polls'] = total_polls
                    active_devices[entity_id]['total_alarms_sent'] = total_alarms_published
            
        except Exception as e:
            logger.error(f"❌ Error polling device {entity_id}: {e}")
        
        # Wait for next poll or stop signal (interruptible)
        stop_event.wait(poll_interval)
    
    logger.info(f"🛑 Stopped polling device {entity_id} (polls: {total_polls}, alarms: {total_alarms_published})")
    
    # Mark final stats before thread exits
    with active_devices_lock:
        if entity_id in active_devices:
            active_devices[entity_id]['status'] = 'stopped'
            active_devices[entity_id]['total_polls'] = total_polls
            active_devices[entity_id]['total_alarms_sent'] = total_alarms_published



def start_device_monitoring(entity_id: str, config: Dict, active_devices: Dict,
                           active_devices_lock: threading.Lock, kafka_bootstrap: str,
                           poll_interval: int, tb_username: str, tb_password: str) -> Dict:
    """
    Start monitoring a single device with proper slot reservation to prevent race conditions.
    
    Args:
        entity_id: Device entity ID
        config: Device configuration
        active_devices: Shared dictionary tracking active devices
        active_devices_lock: Lock for thread-safe access
        kafka_bootstrap: Kafka bootstrap servers
        poll_interval: Poll interval in seconds
        tb_username: ThingsBoard username
        tb_password: ThingsBoard password
        
    Returns:
        Dictionary with status and details
    """
    topic_name = f"thingsboard_{entity_id}"
    
    # Reserve slot INSIDE lock to prevent race condition
    with active_devices_lock:
        if entity_id in active_devices:
            existing = active_devices[entity_id]
            existing_thread = existing.get('thread')
            existing_status = existing.get('status')
            
            # Allow restart if previous thread finished and is in a terminal state
            if existing_status in ('error', 'stopped', 'timeout') and (not existing_thread or not existing_thread.is_alive()):
                del active_devices[entity_id]
            else:
                return {
                    "entity_id": entity_id,
                    "status": "already_monitoring",
                    "message": f"Device {entity_id} is already being monitored (status: {existing_status})",
                    "kafka_topic": topic_name
                }
        
        # Reserve the slot immediately with "starting" status
        stop_event = threading.Event()
        active_devices[entity_id] = {
            "thread": None,  # Will be set after thread creation
            "stop_event": stop_event,
            "config": config,
            "kafka_topic": topic_name,
            "started_at": datetime.now(timezone.utc),
            "last_poll": None,
            "total_polls": 0,
            "total_alarms_sent": 0,
            "status": "starting"  # Marks as reserved
        }
    
    # Create Kafka topic OUTSIDE lock (can take time)
    if not ensure_kafka_topic(topic_name, kafka_bootstrap):
        # Failed to create topic, cleanup reservation (no thread yet)
        with active_devices_lock:
            if entity_id in active_devices and active_devices[entity_id].get('thread') is None:
                del active_devices[entity_id]
        
        return {
            "entity_id": entity_id,
            "status": "error",
            "message": f"Failed to create Kafka topic for device {entity_id}"
        }
    
    # If a stop was requested during startup, cancel before starting the thread
    with active_devices_lock:
        if entity_id not in active_devices:
            return {
                "entity_id": entity_id,
                "status": "canceled",
                "message": f"Start canceled for device {entity_id} (no longer registered)",
                "kafka_topic": topic_name
            }
        
        current_status = active_devices[entity_id].get('status')
        current_stop_event = active_devices[entity_id].get('stop_event')
        
        if current_stop_event and current_stop_event.is_set() or current_status in ('stopping', 'cancel_requested'):
            del active_devices[entity_id]
            logger.info(f"🛑 Start canceled for device {entity_id} (stop requested during startup)")
            
            return {
                "entity_id": entity_id,
                "status": "canceled",
                "message": f"Start canceled for device {entity_id} (stop requested during startup)",
                "kafka_topic": topic_name
            }
    
    # Create and start thread OUTSIDE lock (daemon=False for proper shutdown)
    thread = threading.Thread(
        target=continuous_poll_device,
        args=(config, stop_event, active_devices, active_devices_lock,
              kafka_bootstrap, poll_interval, tb_username, tb_password),
        daemon=False,  # NOT daemon - we want proper shutdown control
        name=f"monitor-{entity_id[:8]}"
    )
    thread.start()
    
    # Update with thread reference INSIDE lock
    stop_requested = False
    with active_devices_lock:
        if entity_id in active_devices:
            active_devices[entity_id]['thread'] = thread
            
            # If a stop came in while we were starting, reflect it in response
            current_status = active_devices[entity_id].get('status')
            if active_devices[entity_id]['stop_event'].is_set() or current_status in ('stopping', 'cancel_requested'):
                stop_requested = True
        else:
            stop_requested = True
    
    if stop_requested:
        logger.info(f"🛑 Device {entity_id} start completed but stop was requested concurrently")
        return {
            "entity_id": entity_id,
            "status": "canceled",
            "message": f"Device {entity_id} was stopped while starting",
            "kafka_topic": topic_name
        }
    
    logger.info(f"📡 Started monitoring device {entity_id}")
    
    return {
        "entity_id": entity_id,
        "status": "success",
        "message": f"Started continuous monitoring for device {entity_id}",
        "kafka_topic": topic_name
    }



def stop_device_monitoring(entity_id: str, active_devices: Dict,
                          active_devices_lock: threading.Lock,
                          timeout: int = 10) -> Dict:
    """
    Stop monitoring a single device with proper cleanup and orphan prevention.
    
    Args:
        entity_id: Device entity ID
        active_devices: Shared dictionary tracking active devices
        active_devices_lock: Lock for thread-safe access
        timeout: Seconds to wait for thread to stop
        
    Returns:
        Dictionary with status and details
    """
    # Extract info and signal stop INSIDE lock
    with active_devices_lock:
        if entity_id not in active_devices:
            return {
                "entity_id": entity_id,
                "status": "not_found",
                "message": f"Device {entity_id} is not being monitored"
            }
        
        device_info = active_devices[entity_id]
        current_status = device_info.get('status')
        thread = device_info.get('thread')
        
        # Check if already stopping/cancel requested
        if current_status in ('stopping', 'cancel_requested'):
            return {
                "entity_id": entity_id,
                "status": "already_stopping",
                "message": f"Device {entity_id} is already being stopped"
            }
        
        # Special case: stop requested while still starting (no thread yet)
        if current_status == 'starting' and (thread is None or getattr(thread, "ident", None) is None):
            device_info['status'] = 'cancel_requested'
            device_info['stop_event'].set()
            
            return {
                "entity_id": entity_id,
                "status": "stopping",
                "message": f"Stop requested for device {entity_id} during startup"
            }
        
        # Normal stop path
        device_info['status'] = 'stopping'
        device_info['stop_event'].set()
        
        # Extract references (don't delete yet)
        kafka_topic = device_info['kafka_topic']
        total_polls = device_info['total_polls']
        total_alarms = device_info['total_alarms_sent']
    
    # Join OUTSIDE lock (blocking operation)
    if thread and thread.is_alive():
        logger.info(f"⏳ Waiting up to {timeout}s for device {entity_id} thread to stop...")
        thread.join(timeout=timeout)
    
    # Check if thread actually stopped and cleanup INSIDE lock
    with active_devices_lock:
        if entity_id not in active_devices:
            # Another thread already cleaned up
            return {
                "entity_id": entity_id,
                "status": "success",
                "message": f"Device {entity_id} monitoring stopped (already cleaned up)"
            }
        
        thread = active_devices[entity_id].get('thread')
        
        # CRITICAL: Check if thread is actually dead before deleting
        if thread and thread.is_alive():
            # Thread didn't stop in time - DO NOT DELETE (prevent orphan)
            logger.error(f"❌ Thread for device {entity_id} did not stop within {timeout}s")
            active_devices[entity_id]['status'] = 'timeout'
            
            return {
                "entity_id": entity_id,
                "status": "timeout",
                "message": f"Device {entity_id} thread did not stop within {timeout}s (still alive)",
                "warning": "Thread marked as timeout - will remain in tracking to prevent orphan"
            }
        
        # Thread is confirmed dead OR was never started (startup canceled) -> safe to delete
        device_info = active_devices[entity_id]
        kafka_topic = device_info.get('kafka_topic')
        total_polls = device_info.get('total_polls', 0)
        total_alarms = device_info.get('total_alarms_sent', 0)
        
        del active_devices[entity_id]
    
    logger.info(f"🛑 Stopped monitoring device {entity_id} (polls: {total_polls}, alarms: {total_alarms})")
    
    return {
        "entity_id": entity_id,
        "status": "success",
        "message": f"Stopped monitoring device {entity_id}",
        "kafka_topic": kafka_topic,
        "statistics": {
            "total_polls": total_polls,
            "total_alarms_sent": total_alarms
        }
    }


def shutdown_all_threads(active_devices: Dict, active_devices_lock: threading.Lock,
                        timeout_per_thread: int = 10):
    """
    Gracefully shutdown all monitoring threads with proper timeout handling.
    
    Args:
        active_devices: Shared dictionary tracking active devices
        active_devices_lock: Lock for thread-safe access
        timeout_per_thread: Seconds to wait per thread
    """
    logger.info("🛑 Shutting down all monitoring threads...")
    
    with active_devices_lock:
        device_ids = list(active_devices.keys())
    
    if not device_ids:
        logger.info("✅ No active threads to stop")
        return
    
    logger.info(f"🛑 Stopping {len(device_ids)} device(s)...")
    
    # Stop each device
    failed_stops = []
    for entity_id in device_ids:
        result = stop_device_monitoring(entity_id, active_devices, active_devices_lock, 
                                       timeout=timeout_per_thread)
        if result['status'] == 'timeout':
            failed_stops.append(entity_id)
    
    if failed_stops:
        logger.warning(f"⚠️ {len(failed_stops)} thread(s) did not stop gracefully: {failed_stops}")
        logger.warning("These threads will be force-terminated when process exits")
    else:
        logger.info(f"✅ All {len(device_ids)} monitoring threads stopped successfully")
