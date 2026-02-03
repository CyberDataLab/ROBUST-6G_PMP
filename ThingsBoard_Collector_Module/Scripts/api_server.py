#!/usr/bin/env python3
"""
REST API server for ThingsBoard data collection with continuous polling support.
Implements endpoints for starting, stopping, and monitoring device data collection.
"""

import os
import json
import logging
import hashlib
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Set
from flask import Flask, request, jsonify
from confluent_kafka import Producer, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic

from thingsboard_api import ThingsBoardClient, datetime_to_epoch_ms

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

KAFKA_BOOTSTRAP = "kafka_robust6g-node1.lan:9094"

# Global tracking of active monitoring threads
active_devices: Dict[str, Dict] = {}
active_devices_lock = threading.Lock() #Mutex

MAX_CONCURRENT_DEVICES = 100
POLL_INTERVAL_SECONDS = 30


def ensure_kafka_topic(topic_name: str) -> bool:
    """
    Ensure a Kafka topic exists. Create it if it doesn't.
    
    Args:
        topic_name: Name of the Kafka topic
        
    Returns:
        True if topic exists or was created successfully
    """
    try:
        admin = AdminClient({'bootstrap.servers': KAFKA_BOOTSTRAP})
        

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


def publish_to_kafka(topic: str, data: Dict) -> bool:
    """
    Publish data to a Kafka topic.
    
    Args:
        topic: Kafka topic name
        data: Dictionary to publish as JSON
        
    Returns:
        True if published successfully
    """
    producer = Producer({
        'bootstrap.servers': KAFKA_BOOTSTRAP,
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


def continuous_poll_device(config: Dict, stop_event: threading.Event):
    """
    Continuously poll ThingsBoard for device alarms and publish to Kafka.
    Runs in a separate thread per device.
    
    Args:
        config: Configuration dictionary with TB connection details
        stop_event: Threading event to signal stop
    """
    entity_id = config['entityId']
    entity_type = config.get('entityType', 'DEVICE')
    topic_name = f"thingsboard_{entity_id}"
    
    logger.info(f"🔄 Starting continuous polling for device {entity_id}")
    
    # Initialize ThingsBoard client
    tb_client = ThingsBoardClient(
        host=config['thingsboardsIP'],
        port=config['thingsboardPort'],
        username=os.getenv("TB_USERNAME", "tenant@thingsboard.org"),
        password=os.getenv("TB_PASSWORD", "tenant")
    )
    
    # Initial authentication
    if not tb_client.authenticate():
        logger.error(f"❌ Failed initial authentication for device {entity_id}")
        return
    
    seen_alarm_hashes: Set[str] = set()# Avoid duplicates
    
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
                stop_event.wait(POLL_INTERVAL_SECONDS)
                continue
            
            # Filter new alarms
            all_alarms = alarms_data.get('data', [])
            new_alarms = []
            
            for alarm in all_alarms:
                alarm_hash = generate_alarm_hash(alarm)
                if alarm_hash not in seen_alarm_hashes:
                    new_alarms.append(alarm)
                    seen_alarm_hashes.add(alarm_hash)
            
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
                
                if publish_to_kafka(topic_name, kafka_payload):
                    total_alarms_published += len(new_alarms)
                    logger.info(f"📤 Published {len(new_alarms)} new alarm(s) for {entity_id}")
            
            # Update device stats
            with active_devices_lock:
                if entity_id in active_devices:
                    active_devices[entity_id]['last_poll'] = datetime.now(timezone.utc)
                    active_devices[entity_id]['total_polls'] = total_polls
                    active_devices[entity_id]['total_alarms_sent'] = total_alarms_published
            
        except Exception as e:
            logger.error(f"❌ Error polling device {entity_id}: {e}")
        
        # Wait for next poll or stop signal
        stop_event.wait(POLL_INTERVAL_SECONDS)
    
    logger.info(f"🛑 Stopped polling device {entity_id} (polls: {total_polls}, alarms: {total_alarms_published})")


@app.route('/ConfigurationManagerThingsboard/collectDataFromThingsboard', methods=['POST'])
def collect_data_from_thingsboard():
    """
    Start continuous monitoring of a ThingsBoard device.
    
    Expected JSON payload:
    {
        "thingsboardsIP": "localhost",
        "thingsboardPort": 80,
        "entityId": "71c0e3e0-a8e1-11f0-a091-2d2de22ced6c",
        "entityType": "DEVICE"
    }
    
    Returns:
        200 OK if monitoring started successfully
        409 Conflict if device already being monitored
        400 Bad Request if payload is invalid
        503 Service Unavailable if max device limit reached
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400
        
        # Required fields
        tb_ip = data.get("thingsboardsIP")
        tb_port = data.get("thingsboardPort", 80)
        entity_id = data.get("entityId")
        entity_type = data.get("entityType", "DEVICE")
        
        if not tb_ip or not entity_id:
            return jsonify({
                "error": "Missing required fields: thingsboardsIP, entityId"
            }), 400
        
        # Check if already monitoring
        with active_devices_lock:
            if entity_id in active_devices:
                return jsonify({
                    "error": f"Device {entity_id} is already being monitored",
                    "started_at": active_devices[entity_id]['started_at'].isoformat()
                }), 409
            
            # Device limit
            if len(active_devices) >= MAX_CONCURRENT_DEVICES:
                return jsonify({
                    "error": f"Maximum concurrent devices limit reached ({MAX_CONCURRENT_DEVICES})"
                }), 503
        
        logger.info(f"📡 Starting monitoring for device {entity_id}")
        
        # Ensure Kafka topic exists
        topic_name = f"thingsboard_{entity_id}"
        if not ensure_kafka_topic(topic_name):
            return jsonify({"error": f"Failed to create Kafka topic: {topic_name}"}), 500
        
        # Create stop event and thread
        stop_event = threading.Event()
        
        config = {
            "thingsboardsIP": tb_ip,
            "thingsboardPort": tb_port,
            "entityId": entity_id,
            "entityType": entity_type
        }
        
        thread = threading.Thread(
            target=continuous_poll_device,
            args=(config, stop_event),
            daemon=True,
            name=f"tb-poller-{entity_id[:8]}"
        )
        
        # Register device
        with active_devices_lock:
            active_devices[entity_id] = {
                "thread": thread,
                "stop_event": stop_event,
                "started_at": datetime.now(timezone.utc),
                "last_poll": None,
                "total_polls": 0,
                "total_alarms_sent": 0,
                "config": config,
                "kafka_topic": topic_name
            }
        
        thread.start()
        
        return jsonify({
            "message": "Monitoring started successfully",
            "entity_id": entity_id,
            "kafka_topic": topic_name,
            "poll_interval_seconds": POLL_INTERVAL_SECONDS
        }), 200
        
    except Exception as e:
        logger.exception(f"❌ Unexpected error in collectDataFromThingsboard: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route('/ConfigurationManagerThingsboard/stopMonitoring', methods=['POST'])
def stop_monitoring():
    """
    Stop monitoring a specific device.
    
    Expected JSON payload:
    {
        "entityId": "71c0e3e0-a8e1-11f0-a091-2d2de22ced6c"
    }
    
    Returns:
        200 OK if stopped successfully
        404 Not Found if device not being monitored
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400
        
        entity_id = data.get("entityId")
        
        if not entity_id:
            return jsonify({"error": "Missing required field: entityId"}), 400
        
        with active_devices_lock:
            if entity_id not in active_devices:
                return jsonify({
                    "error": f"Device {entity_id} is not being monitored"
                }), 404
            
            device_info = active_devices[entity_id]
        
        logger.info(f"🛑 Stopping monitoring for device {entity_id}")
        
        device_info['stop_event'].set()
        
        device_info['thread'].join(timeout=10)
        
        if device_info['thread'].is_alive():
            logger.warning(f"⚠️ Thread for {entity_id} did not stop gracefully")
        
        with active_devices_lock:
            stats = {
                "total_polls": active_devices[entity_id]['total_polls'],
                "total_alarms_sent": active_devices[entity_id]['total_alarms_sent'],
                "duration_seconds": (datetime.now(timezone.utc) - active_devices[entity_id]['started_at']).total_seconds()
            }
            del active_devices[entity_id]
        
        return jsonify({
            "message": "Monitoring stopped successfully",
            "entity_id": entity_id,
            "statistics": stats
        }), 200
        
    except Exception as e:
        logger.exception(f"❌ Error stopping monitoring: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route('/ConfigurationManagerThingsboard/monitoringStatus', methods=['GET'])
def monitoring_status():
    """
    Get status of all monitored devices.
    
    Returns:
        200 OK with list of monitored devices and their status
    """
    try:
        with active_devices_lock:
            status = {}
            for entity_id, info in active_devices.items():
                status[entity_id] = {
                    "started_at": info['started_at'].isoformat(),
                    "last_poll": info['last_poll'].isoformat() if info['last_poll'] else None,
                    "is_alive": info['thread'].is_alive(),
                    "total_polls": info['total_polls'],
                    "total_alarms_sent": info['total_alarms_sent'],
                    "kafka_topic": info['kafka_topic'],
                    "config": {
                        "thingsboardsIP": info['config']['thingsboardsIP'],
                        "thingsboardPort": info['config']['thingsboardPort'],
                        "entityType": info['config']['entityType']
                    }
                }
        
        return jsonify({
            "active_devices": len(status),
            "max_devices": MAX_CONCURRENT_DEVICES,
            "poll_interval_seconds": POLL_INTERVAL_SECONDS,
            "devices": status
        }), 200
        
    except Exception as e:
        logger.exception(f"❌ Error getting monitoring status: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint with thread status.
    """
    with active_devices_lock:
        active_count = len(active_devices)
        alive_threads = sum(1 for info in active_devices.values() if info['thread'].is_alive())
    
    return jsonify({
        "status": "healthy",
        "service": "ThingsBoard Collector",
        "kafka_bootstrap": KAFKA_BOOTSTRAP,
        "active_devices": active_count,
        "alive_threads": alive_threads,
        "max_devices": MAX_CONCURRENT_DEVICES
    }), 200


def shutdown_handler(signum, frame):
    """
    Gracefully shutdown all monitoring threads.
    """
    logger.info("🛑 Received shutdown signal, stopping all monitoring threads...")
    
    with active_devices_lock:
        device_ids = list(active_devices.keys())
    
    for device_id in device_ids:
        try:
            active_devices[device_id]['stop_event'].set()
        except Exception as e:
            logger.error(f"Error signaling stop for {device_id}: {e}")
    
    # Wait for all threads to finish
    for device_id in device_ids:
        try:
            thread = active_devices[device_id]['thread']
            thread.join(timeout=10)
            if thread.is_alive():
                logger.warning(f"⚠️ Thread for {device_id} did not stop in time")
        except Exception as e:
            logger.error(f"Error joining thread for {device_id}: {e}")
    
    logger.info("✅ All monitoring threads stopped")
    sys.exit(0)


if __name__ == '__main__':
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning) # Suppress InsecureRequestWarning from urllib3
    
    # Shutdown handlers
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    logger.info("🚀 Starting ThingsBoard Collector API Server")
    logger.info(f"   Kafka Bootstrap: {KAFKA_BOOTSTRAP}")
    logger.info(f"   Max Concurrent Devices: {MAX_CONCURRENT_DEVICES}")
    logger.info(f"   Poll Interval: {POLL_INTERVAL_SECONDS}s")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False
    )