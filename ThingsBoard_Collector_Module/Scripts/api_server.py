#!/usr/bin/env python3
"""
REST API server for ThingsBoard data collection following OpenAPI specification.
Implements /ConfigurationManagerThingsboard/collectDataFromThingsboard endpoint.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional
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

# Kafka external broker
KAFKA_BOOTSTRAP = "kafka_robust6g-node1.lan:9094"


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
        
        # Check if topic exists
        metadata = admin.list_topics(timeout=5)
        if topic_name in metadata.topics:
            logger.info(f"ℹ️  Topic '{topic_name}' already exists")
            return True
        
        # Create new topic
        new_topic = NewTopic(
            topic=topic_name,
            num_partitions=1,
            replication_factor=1
        )
        
        fs = admin.create_topics([new_topic])
        
        # Wait for operation to complete
        for topic, f in fs.items():
            try:
                f.result()  # Blocks until topic is created
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
            logger.info(f"✅ Message delivered to {msg.topic()} [{msg.partition()}]")
    
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


@app.route('/ConfigurationManagerThingsboard/collectDataFromThingsboard', methods=['POST'])
def collect_data_from_thingsboard():
    """
    Endpoint to collect data from ThingsBoard and publish to Kafka.
    
    Expected JSON payload (according to OpenAPI spec):
    {
        "thingsboardsIP": "locahlhost",
        "thingsboardPort": 8099,
        "entityId": "71c0e3e0-a8e1-11f0-a091-2d2de22ced6c",
        "entityType": "DEVICE",
        "timestampInit": "2025-01-28T10:00:00Z",  # Optional
        "timestampEnd": "2025-01-28T12:00:00Z"    # Optional
    }
    
    Returns:
        200 OK if successful
        400 Bad Request if payload is invalid
        500 Internal Server Error if operation fails
    """
    try:
        # Parse payload
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400
        
        # OpenAPI required fields
        tb_ip = data.get("thingsboardsIP")
        tb_port = data.get("thingsboardPort", 80)
        entity_id = data.get("entityId")
        entity_type = data.get("entityType", "DEVICE")
        
        if not tb_ip or not entity_id:
            return jsonify({
                "error": "Missing required fields: thingsboardsIP, entityId"
            }), 400
        
        # Optional timestamp filters
        timestamp_init = data.get("timestampInit")
        timestamp_end = data.get("timestampEnd")
        
        start_ts = None
        end_ts = None
        
        if timestamp_init:
            try:
                dt_init = datetime.fromisoformat(timestamp_init.replace('Z', '+00:00'))
                start_ts = datetime_to_epoch_ms(dt_init)
            except ValueError as e:
                return jsonify({"error": f"Invalid timestampInit format: {e}"}), 400
        
        if timestamp_end:
            try:
                dt_end = datetime.fromisoformat(timestamp_end.replace('Z', '+00:00'))
                end_ts = datetime_to_epoch_ms(dt_end)
            except ValueError as e:
                return jsonify({"error": f"Invalid timestampEnd format: {e}"}), 400
        
        logger.info(f"📡 Starting ThingsBoard data collection from {tb_ip}:{tb_port}")
        logger.info(f"   Entity: {entity_type}/{entity_id}")
        
        # Initialize ThingsBoard client
        tb_client = ThingsBoardClient(
            host=tb_ip,
            port=tb_port,
            username=os.getenv("TB_USERNAME", "tenant@thingsboard.org"),
            password=os.getenv("TB_PASSWORD", "tenant")
        )
        
        # Authenticate
        if not tb_client.authenticate():
            return jsonify({"error": "ThingsBoard authentication failed"}), 500
        
        # Retrieve alarms
        alarms_data = tb_client.get_alarms(
            entity_id=entity_id,
            entity_type=entity_type,
            status="ACTIVE_UNACK",  # Can be parameterized if needed
            start_ts=start_ts,
            end_ts=end_ts
        )
        
        if alarms_data is None:
            return jsonify({"error": "Failed to retrieve alarms from ThingsBoard"}), 500
        
        # Create Kafka topic if needed
        topic_name = f"thingsboard_{entity_id}"
        if not ensure_kafka_topic(topic_name):
            return jsonify({"error": f"Failed to create Kafka topic: {topic_name}"}), 500
        
        kafka_payload = {
            "source": "thingsboard",
            "entity_id": entity_id,
            "entity_type": entity_type,
            "collection_timestamp": datetime.now(timezone.utc).isoformat(),
            "alarms": alarms_data
        }
        
        if not publish_to_kafka(topic_name, kafka_payload):
            return jsonify({"error": "Failed to publish data to Kafka"}), 500
        
        return jsonify({
            "message": "Data collection successful",
            "entity_id": entity_id,
            "kafka_topic": topic_name,
            "alarms_count": alarms_data.get("totalElements", 0)
        }), 200
        
    except Exception as e:
        logger.exception(f"❌ Unexpected error in collectDataFromThingsboard: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for monitoring.
    """
    return jsonify({
        "status": "healthy",
        "service": "ThingsBoard Collector",
        "kafka_bootstrap": KAFKA_BOOTSTRAP
    }), 200


if __name__ == '__main__':
    # Suppress InsecureRequestWarning from urllib3 (since we use verify=False)
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    logger.info("🚀 Starting ThingsBoard Collector API Server")
    logger.info(f"   Kafka Bootstrap: {KAFKA_BOOTSTRAP}")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False
    )