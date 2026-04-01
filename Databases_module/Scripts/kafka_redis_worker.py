#!/usr/bin/env python3
"""
Kafka to Redis streaming worker with dynamic topic discovery and memory management.
Consumes messages from multiple Kafka topics and pushes them to Redis Lists
for real-time streaming via WebSocket API.

Features:
- Dynamic topic subscription with regex patterns
- Automatic topic discovery (polling every N seconds)
- Separate structures for streams with/without machine_id
- Active data retention management (delete old messages)
- Emergency memory cleanup when threshold reached
- Graceful shutdown handling
"""

import os
import sys
import json
import signal
import logging
import re
import threading
import time
from typing import Optional, Dict, Tuple, Set
from datetime import datetime, timedelta
from collections import defaultdict

import redis
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.admin import AdminClient

# ============================================================================
# CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Kafka Configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP")
KTRW_KAFKA_GROUP_ID = os.getenv("KTRW_KAFKA_GROUP_ID")
KTRW_KAFKA_AUTO_OFFSET_RESET = os.getenv("KTRW_KAFKA_AUTO_OFFSET_RESET")
KTRW_KAFKA_ENABLE_AUTO_COMMIT = os.getenv("KTRW_KAFKA_ENABLE_AUTO_COMMIT", "true").lower() == "true"
KTRW_KAFKA_TOPIC_REFRESH_INTERVAL = int(os.getenv("KTRW_KAFKA_TOPIC_REFRESH_INTERVAL", "30"))

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
REDIS_USER = int(os.getenv("REDIS_USER", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# Stream Configuration
KTRW_REDIS_MAX_STREAM_LENGTH = int(os.getenv("KTRW_REDIS_MAX_STREAM_LENGTH"))
KTRW_REDIS_STREAM_TTL_SECONDS = int(os.getenv("KTRW_REDIS_STREAM_TTL_SECONDS"))

# Memory Management Configuration
KTRW_REDIS_CLEANUP_INTERVAL = int(os.getenv("KTRW_REDIS_CLEANUP_INTERVAL", "300"))
KTRW_REDIS_RETENTION_HOURS = int(os.getenv("KTRW_REDIS_RETENTION_HOURS", "2"))
KTRW_REDIS_EMERGENCY_RETENTION_HOURS = int(os.getenv("KTRW_REDIS_EMERGENCY_RETENTION_HOURS", "1"))
KTRW_REDIS_MEMORY_THRESHOLD = float(os.getenv("KTRW_REDIS_MEMORY_THRESHOLD", "0.85"))

# Kafka Topic Names (from environment variables)
TELEGRAF_BASE_TOPIC = os.getenv("TELEGRAF_BASE_TOPIC", "telegraf_metrics")
FLUENTD_SYSLOG_BASE_TOPIC = os.getenv("FLUENTD_SYSLOG_BASE_TOPIC", "syslog_logs")
FLUENTD_SYSTEMD_BASE_TOPIC = os.getenv("FLUENTD_SYSTEMD_BASE_TOPIC", "systemd_logs")
FALCO_BASE_TOPIC = os.getenv("FALCO_BASE_TOPIC", "falco_events")
TSHARK_BASE_TOPIC = os.getenv("TSHARK_BASE_TOPIC", "tshark_traces")
SNORT_KAFKA_TOPIC_OUT = os.getenv("SNORT_KAFKA_TOPIC_OUT", "snort_alerts")
CIC_KAFKA_BASE_TOPIC_OUT = os.getenv("CIC_KAFKA_BASE_TOPIC_OUT", "cic_flow")

# Topic patterns to subscribe (regex patterns)
# Using environment variables for topic names
KAFKA_TOPIC_PATTERNS = [
    rf"^{TELEGRAF_BASE_TOPIC}.*",
    rf"^{FLUENTD_SYSLOG_BASE_TOPIC}.*",
    rf"^{FLUENTD_SYSTEMD_BASE_TOPIC}.*",
    rf"^{FALCO_BASE_TOPIC}.*",
    rf"^{TSHARK_BASE_TOPIC}.*",
    rf"^{SNORT_KAFKA_TOPIC_OUT}$",
    rf"^{CIC_KAFKA_BASE_TOPIC_OUT}$"
]

# Topics that do NOT have machine_id in payload (go to global streams)
TOPICS_WITHOUT_MACHINE_ID = {
    SNORT_KAFKA_TOPIC_OUT,
    CIC_KAFKA_BASE_TOPIC_OUT,
    TSHARK_BASE_TOPIC
}

# Mapping from topic patterns to data_type
TOPIC_TO_DATATYPE_MAPPING = {
    rf"^{TELEGRAF_BASE_TOPIC}.*": "health_metrics",
    rf"^{FLUENTD_SYSLOG_BASE_TOPIC}.*": "logs",
    rf"^{FLUENTD_SYSTEMD_BASE_TOPIC}.*": "logs",
    rf"^{FALCO_BASE_TOPIC}.*": "security_logs",
    rf"^{TSHARK_BASE_TOPIC}.*": "network_traces",
    rf"^{SNORT_KAFKA_TOPIC_OUT}$": "ids_alerts",
    rf"^{CIC_KAFKA_BASE_TOPIC_OUT}$": "network_flows"
}

# Global state
shutdown_flag = False
pause_consumption_flag = False


# ============================================================================
# KAFKA CONSUMER
# ============================================================================

def create_kafka_consumer() -> Consumer:
    """
    Create and configure Kafka consumer with regex subscription.
    """
    config = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": KTRW_KAFKA_GROUP_ID,
        "auto.offset.reset": KTRW_KAFKA_AUTO_OFFSET_RESET,
        "enable.auto.commit": KTRW_KAFKA_ENABLE_AUTO_COMMIT,
        "allow.auto.create.topics": False,
        "enable.partition.eof": False,
        "partition.assignment.strategy": "cooperative-sticky",
        "session.timeout.ms": 10000,
        "max.poll.interval.ms": 300000,
        "socket.keepalive.enable": True,
    }
    
    consumer = Consumer(config)
    logger.info(f"📡 Kafka consumer created with bootstrap: {KAFKA_BOOTSTRAP}")
    
    return consumer


def create_kafka_admin_client() -> AdminClient:
    """
    Create Kafka AdminClient for topic discovery.
    """
    config = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
    }
    
    return AdminClient(config)


def discover_matching_topics(admin_client: AdminClient) -> Set[str]:
    """
    Discover all Kafka topics that match our regex patterns.
    Returns set of matching topic names.
    """
    try:
        # Get cluster metadata
        metadata = admin_client.list_topics(timeout=10)
        all_topics = set(metadata.topics.keys())
        
        # Filter topics matching our patterns
        matching_topics = set()
        for topic in all_topics:
            for pattern in KAFKA_TOPIC_PATTERNS:
                if re.match(pattern, topic):
                    matching_topics.add(topic)
                    break
        
        return matching_topics
        
    except Exception as e:
        logger.error(f"❌ Error discovering topics: {e}")
        return set()


def topic_discovery_worker(consumer: Consumer, admin_client: AdminClient):
    """
    Background thread that periodically discovers new topics and updates consumer subscription.
    """
    global shutdown_flag
    
    logger.info(f"🔍 Topic discovery worker started (interval: {KTRW_KAFKA_TOPIC_REFRESH_INTERVAL}s)")
    
    current_topics = set()
    
    while not shutdown_flag:
        try:
            # Discover matching topics
            discovered_topics = discover_matching_topics(admin_client)
            
            # Check if there are changes
            if discovered_topics != current_topics:
                new_topics = discovered_topics - current_topics
                removed_topics = current_topics - discovered_topics
                
                if new_topics:
                    logger.info(f"➕ New topics discovered: {new_topics}")
                if removed_topics:
                    logger.info(f"➖ Topics removed: {removed_topics}")
                
                # Update subscription
                if discovered_topics:
                    topic_list = list(discovered_topics)
                    consumer.subscribe(topic_list)
                    logger.info(f"📡 Subscribed to {len(topic_list)} topics")
                    current_topics = discovered_topics
                else:
                    logger.warning("⚠️  No matching topics found, keeping previous subscription")
            
            # Sleep before next check
            time.sleep(KTRW_KAFKA_TOPIC_REFRESH_INTERVAL)
            
        except Exception as e:
            logger.error(f"❌ Error in topic discovery worker: {e}")
            time.sleep(KTRW_KAFKA_TOPIC_REFRESH_INTERVAL)
    
    logger.info("🛑 Topic discovery worker stopped")


# ============================================================================
# REDIS CLIENT
# ============================================================================

def create_redis_client() -> redis.Redis:
    """
    Create Redis client connection.
    """
    try:
        redis_password = REDIS_PASSWORD if REDIS_PASSWORD else None
        
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_USER,
            password=redis_password,
            decode_responses=False,
            socket_keepalive=True,
            socket_connect_timeout=5,
            retry_on_timeout=True
        )
        
        client.ping()
        logger.info(f"✅ Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        return client
        
    except redis.ConnectionError as e:
        logger.error(f"❌ Failed to connect to Redis: {e}")
        sys.exit(1)


def get_redis_memory_usage(redis_client: redis.Redis) -> Tuple[float, int, int]:
    """
    Get Redis memory usage information.
    Returns: (usage_ratio, used_bytes, max_bytes)
    """
    try:
        info = redis_client.info("memory")
        used_memory = info.get("used_memory", 0)
        max_memory = info.get("maxmemory", 0)
        
        if max_memory == 0:
            return 0.0, used_memory, 0
        
        usage_ratio = used_memory / max_memory
        return usage_ratio, used_memory, max_memory
        
    except Exception as e:
        logger.error(f"❌ Error getting Redis memory info: {e}")
        return 0.0, 0, 0


# ============================================================================
# DATA PROCESSING
# ============================================================================

def check_if_topic_without_machine_id(topic: str) -> bool:
    """
    Check if topic is in the whitelist of topics without machine_id.
    """
    # Check exact match first
    if topic in TOPICS_WITHOUT_MACHINE_ID:
        return True
    
    # Check if topic matches any pattern for topics without machine_id
    for topic_name in TOPICS_WITHOUT_MACHINE_ID:
        if topic.startswith(topic_name):
            return True
    
    return False


def extract_machine_id(message_bytes: bytes, topic: str) -> Optional[str]:
    """
    Extract machine_id from Kafka message payload.
    Handles different message formats with priority order.
    
    Returns None if topic is in whitelist or machine_id cannot be found.
    """
    # Priority 1: Check if topic is in whitelist (no machine_id expected)
    if check_if_topic_without_machine_id(topic):
        return None
    
    try:
        # Parse JSON
        message_str = message_bytes.decode('utf-8', errors='replace')
        data = json.loads(message_str)
        
        # Priority 2: Direct field "machine_id"
        if 'machine_id' in data:
            return str(data['machine_id'])
        
        # Priority 3: Nested in tags (telegraf format)
        if 'tags' in data and isinstance(data['tags'], dict):
            if 'machine_id' in data['tags']:
                return str(data['tags']['machine_id'])
        
        # Priority 4: Double parsing - message field contains JSON (Fluentd/Falco format)
        if 'message' in data and isinstance(data['message'], str):
            try:
                # Parse the nested JSON in the message field
                nested_data = json.loads(data['message'])
                if 'machine_id' in nested_data:
                    return str(nested_data['machine_id'])
            except (json.JSONDecodeError, TypeError):
                # If message is not JSON, continue to next strategy
                pass
        
        # Priority 5: Nested in output_fields (falco alternative format)
        if 'output_fields' in data and isinstance(data['output_fields'], dict):
            if 'machine_id' in data['output_fields']:
                return str(data['output_fields']['machine_id'])
        
        logger.warning(f"⚠️  No machine_id found in message from topic {topic}")
        return None
        
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(f"⚠️  Failed to parse message from {topic}: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error extracting machine_id from {topic}: {e}")
        return None


def get_data_type_from_topic(topic: str) -> Optional[str]:
    """
    Map Kafka topic name to data_type using regex patterns.
    """
    for pattern, data_type in TOPIC_TO_DATATYPE_MAPPING.items():
        if re.match(pattern, topic):
            return data_type
    
    logger.warning(f"⚠️  No data_type mapping found for topic: {topic}")
    return None


def push_to_redis(
    redis_client: redis.Redis,
    data_type: str,
    machine_id: Optional[str],
    message_bytes: bytes,
    topic: str
) -> bool:
    """
    Push message to Redis List and update metadata.
    
    Two types of streams:
    - With machine_id: {data_type}:{machine_id}
    - Without machine_id (global): global:{data_type}
    
    Returns True if successful, False otherwise.
    """
    try:
        # Determine stream key format
        if machine_id is None:
            # Global stream (no machine_id)
            stream_key = f"global:{data_type}"
            active_streams_set = "active_global_streams"
        else:
            # Regular stream (with machine_id)
            stream_key = f"{data_type}:{machine_id}"
            active_streams_set = "active_streams"
        
        # Add timestamp to message for cleanup purposes
        current_time = datetime.utcnow()
        timestamp_key = f"{stream_key}:timestamps"
        
        # Push message to list (LPUSH = left push, newest first)
        redis_client.lpush(stream_key, message_bytes)
        
        # Store timestamp for this message (for cleanup)
        redis_client.lpush(timestamp_key, current_time.isoformat())
        
        # Trim both lists to max length (keep only newest N messages)
        redis_client.ltrim(stream_key, 0, KTRW_REDIS_MAX_STREAM_LENGTH - 1)
        redis_client.ltrim(timestamp_key, 0, KTRW_REDIS_MAX_STREAM_LENGTH - 1)
        
        # Set expiration (TTL) on both keys
        redis_client.expire(stream_key, KTRW_REDIS_STREAM_TTL_SECONDS)
        redis_client.expire(timestamp_key, KTRW_REDIS_STREAM_TTL_SECONDS)
        
        # Add to active streams set (for discovery)
        redis_client.sadd(active_streams_set, stream_key)
        
        # Update last update timestamp
        last_update_key = f"{stream_key}:last_update"
        redis_client.set(last_update_key, current_time.isoformat(), ex=KTRW_REDIS_STREAM_TTL_SECONDS)
        
        # Store topic mapping for reference
        topic_key = f"{stream_key}:topic"
        redis_client.set(topic_key, topic, ex=KTRW_REDIS_STREAM_TTL_SECONDS)
        
        return True
        
    except redis.RedisError as e:
        logger.error(f"❌ Redis error pushing to {stream_key}: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error pushing to Redis: {e}")
        return False


# ============================================================================
# MEMORY MANAGEMENT AND CLEANUP
# ============================================================================

def cleanup_old_messages(redis_client: redis.Redis, retention_hours: int) -> Dict[str, int]:
    """
    Remove messages older than retention_hours from all streams.
    Returns dict with cleanup statistics.
    """
    stats = {
        "streams_processed": 0,
        "messages_deleted": 0,
        "errors": 0
    }
    
    cutoff_time = datetime.utcnow() - timedelta(hours=retention_hours)
    
    try:
        # Get all active streams (both regular and global)
        regular_streams = redis_client.smembers("active_streams")
        global_streams = redis_client.smembers("active_global_streams")
        all_streams = list(regular_streams) + list(global_streams)
        
        for stream_bytes in all_streams:
            stream_key = stream_bytes.decode('utf-8')
            timestamp_key = f"{stream_key}:timestamps"
            
            try:
                # Get all timestamps
                timestamps = redis_client.lrange(timestamp_key, 0, -1)
                
                if not timestamps:
                    continue
                
                # Find index of first message to keep (newest message older than cutoff)
                keep_from_index = -1
                for i, ts_bytes in enumerate(timestamps):
                    try:
                        ts_str = ts_bytes.decode('utf-8')
                        msg_time = datetime.fromisoformat(ts_str)
                        
                        if msg_time < cutoff_time:
                            keep_from_index = i
                            break
                    except (ValueError, UnicodeDecodeError):
                        continue
                
                # If we found old messages, trim them
                if keep_from_index > 0:
                    # Keep messages from index 0 to keep_from_index-1
                    redis_client.ltrim(stream_key, 0, keep_from_index - 1)
                    redis_client.ltrim(timestamp_key, 0, keep_from_index - 1)
                    
                    stats["messages_deleted"] += keep_from_index
                
                stats["streams_processed"] += 1
                
            except Exception as e:
                logger.error(f"❌ Error cleaning stream {stream_key}: {e}")
                stats["errors"] += 1
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error in cleanup_old_messages: {e}")
        stats["errors"] += 1
        return stats


def memory_management_worker(redis_client: redis.Redis):
    """
    Background thread that:
    1. Periodically cleans old messages (>RETENTION_HOURS)
    2. Monitors memory usage
    3. Triggers emergency cleanup if memory threshold exceeded
    """
    global shutdown_flag, pause_consumption_flag
    
    logger.info(f"🧹 Memory management worker started (interval: {KTRW_REDIS_CLEANUP_INTERVAL}s)")
    logger.info(f"📊 Retention: {KTRW_REDIS_RETENTION_HOURS}h, Emergency: {KTRW_REDIS_EMERGENCY_RETENTION_HOURS}h, Threshold: {KTRW_REDIS_MEMORY_THRESHOLD*100}%")
    
    while not shutdown_flag:
        try:
            # Check memory usage
            usage_ratio, used_bytes, max_bytes = get_redis_memory_usage(redis_client)
            used_mb = used_bytes / (1024 * 1024)
            max_mb = max_bytes / (1024 * 1024)
            
            logger.info(f"💾 Redis memory: {used_mb:.1f}MB / {max_mb:.1f}MB ({usage_ratio*100:.1f}%)")
            
            # Emergency cleanup if threshold exceeded
            if usage_ratio >= KTRW_REDIS_MEMORY_THRESHOLD:
                logger.warning(f"⚠️  Memory threshold exceeded ({usage_ratio*100:.1f}% >= {KTRW_REDIS_MEMORY_THRESHOLD*100}%)")
                logger.warning(f"🚨 EMERGENCY CLEANUP: Pausing consumption and deleting messages >{KTRW_REDIS_EMERGENCY_RETENTION_HOURS}h")
                
                # Pause Kafka consumption
                pause_consumption_flag = True
                time.sleep(2)
                
                # Emergency cleanup
                stats = cleanup_old_messages(redis_client, KTRW_REDIS_EMERGENCY_RETENTION_HOURS)
                logger.info(f"🧹 Emergency cleanup: {stats['messages_deleted']} messages deleted from {stats['streams_processed']} streams")
                
                # Resume consumption
                pause_consumption_flag = False
                logger.info("▶️  Consumption resumed after emergency cleanup")
            
            else:
                # Regular cleanup
                logger.info(f"🧹 Regular cleanup: Deleting messages >{KTRW_REDIS_RETENTION_HOURS}h")
                stats = cleanup_old_messages(redis_client, KTRW_REDIS_RETENTION_HOURS)
                logger.info(f"🧹 Cleanup complete: {stats['messages_deleted']} messages deleted from {stats['streams_processed']} streams")
            
            # Sleep before next cleanup cycle
            time.sleep(KTRW_REDIS_CLEANUP_INTERVAL)
            
        except Exception as e:
            logger.error(f"❌ Error in memory management worker: {e}")
            time.sleep(KTRW_REDIS_CLEANUP_INTERVAL)
    
    logger.info("🛑 Memory management worker stopped")


# ============================================================================
# MAIN WORKER LOOP
# ============================================================================

def main():
    """
    Main worker loop: consume from Kafka and push to Redis.
    Starts background threads for topic discovery and memory management.
    """
    global shutdown_flag, pause_consumption_flag
    
    logger.info("🚀 Starting Kafka → Redis streaming worker")
    logger.info(f"📋 Configuration:")
    logger.info(f"   - Kafka: {KAFKA_BOOTSTRAP}")
    logger.info(f"   - Redis: {REDIS_HOST}:{REDIS_PORT}")
    logger.info(f"   - Stream TTL: {KTRW_REDIS_STREAM_TTL_SECONDS}s ({KTRW_REDIS_STREAM_TTL_SECONDS/3600:.1f}h)")
    logger.info(f"   - Max stream length: {KTRW_REDIS_MAX_STREAM_LENGTH}")
    logger.info(f"   - Retention: {KTRW_REDIS_RETENTION_HOURS}h")
    logger.info(f"   - Topic refresh: {KTRW_KAFKA_TOPIC_REFRESH_INTERVAL}s")
    
    # Initialize connections
    kafka_consumer = create_kafka_consumer()
    kafka_admin = create_kafka_admin_client()
    redis_client = create_redis_client()
    
    # Initial topic discovery and subscription
    logger.info("🔍 Initial topic discovery...")
    initial_topics = discover_matching_topics(kafka_admin)
    if initial_topics:
        kafka_consumer.subscribe(list(initial_topics))
        logger.info(f"📡 Subscribed to {len(initial_topics)} topics: {initial_topics}")
    else:
        logger.warning("⚠️  No matching topics found on startup")
    
    # Start background threads
    topic_discovery_thread = threading.Thread(
        target=topic_discovery_worker,
        args=(kafka_consumer, kafka_admin),
        daemon=True
    )
    topic_discovery_thread.start()
    
    memory_management_thread = threading.Thread(
        target=memory_management_worker,
        args=(redis_client,),
        daemon=True
    )
    memory_management_thread.start()
    
    # Graceful shutdown handling
    def signal_handler(signum, frame):
        global shutdown_flag
        logger.info(f"\n🛑 Received signal {signum}, shutting down gracefully...")
        shutdown_flag = True
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Statistics
    stats = {
        "processed": 0,
        "pushed": 0,
        "failed": 0,
        "paused": 0,
        "by_data_type": defaultdict(int)
    }
    
    last_stats_log = time.time()
    stats_log_interval = 60
    
    try:
        logger.info("✅ Worker ready, waiting for messages...")
        
        while not shutdown_flag:
            # Check if consumption is paused (during emergency cleanup)
            if pause_consumption_flag:
                stats["paused"] += 1
                time.sleep(0.1)
                continue
            
            # Poll for messages
            msg = kafka_consumer.poll(timeout=1.0)
            
            if msg is None:
                continue
            
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    logger.error(f"❌ Kafka error: {msg.error()}")
                    continue
            
            # Process message
            stats["processed"] += 1
            topic = msg.topic()
            message_bytes = msg.value()
            
            # Extract machine_id (or None for global streams)
            machine_id = extract_machine_id(message_bytes, topic)
            
            # Get data_type
            data_type = get_data_type_from_topic(topic)
            if not data_type:
                stats["failed"] += 1
                kafka_consumer.commit(msg)
                continue
            
            # Push to Redis
            success = push_to_redis(
                redis_client,
                data_type,
                machine_id,
                message_bytes,
                topic
            )
            
            if success:
                stats["pushed"] += 1
                stats["by_data_type"][data_type] += 1
            else:
                stats["failed"] += 1
            
            # Commit offset
            kafka_consumer.commit(msg)
            
            # Log stats periodically
            if time.time() - last_stats_log >= stats_log_interval:
                logger.info(
                    f"📊 Stats (last {stats_log_interval}s): "
                    f"Processed={stats['processed']}, "
                    f"Pushed={stats['pushed']}, "
                    f"Failed={stats['failed']}, "
                    f"Paused={stats['paused']}"
                )
                logger.info(f"📊 By data_type: {dict(stats['by_data_type'])}")
                last_stats_log = time.time()
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ Fatal error in worker loop: {e}", exc_info=True)
    finally:
        logger.info(
            f"📊 Final stats: "
            f"Processed={stats['processed']}, "
            f"Pushed={stats['pushed']}, "
            f"Failed={stats['failed']}"
        )
        logger.info(f"📊 By data_type: {dict(stats['by_data_type'])}")
        logger.info("🔌 Closing connections...")
        kafka_consumer.close()
        redis_client.close()
        logger.info("✅ Worker shutdown complete")


if __name__ == "__main__":
    main()
