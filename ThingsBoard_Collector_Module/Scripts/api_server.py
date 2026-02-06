#!/usr/bin/env python3
"""
REST API server for ThingsBoard data collection with continuous polling support.
Implements endpoints for starting, stopping, and monitoring device data collection.
"""

import os
import logging
import signal
import sys
import threading
from datetime import datetime, timezone
from typing import Dict
from flask import Flask, request, jsonify

from thingsboard_api import ThingsBoardClient
from utils import start_device_monitoring, stop_device_monitoring, shutdown_all_threads

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka_robust6g-node1.lan:9094")
TB_USERNAME = os.getenv("TB_USERNAME", "tenant@thingsboard.org")
TB_PASSWORD = os.getenv("TB_PASSWORD", "tenant")

MAX_CONCURRENT_DEVICES = int(os.getenv("MAX_CONCURRENT_DEVICES", "100"))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

active_devices: Dict[str, Dict] = {}
active_devices_lock = threading.Lock() #Mutex


def validate_string_param(data: Dict, param_name: str, required: bool = True) -> tuple:
    """
    Validate that a parameter is a non-empty string.
    
    Args:
        data: Request JSON data
        param_name: Parameter name to validate
        required: Whether parameter is required
        
    Returns:
        Tuple of (is_valid, error_message, value)
    """
    value = data.get(param_name)
    
    if value is None:
        if required:
            return False, f"Missing required field: '{param_name}'", None
        return True, None, None
    
    if not isinstance(value, str):
        return False, f"Field '{param_name}' must be a string, got {type(value).__name__}", None
    
    if required and not value.strip():
        return False, f"Field '{param_name}' cannot be empty", None
    
    return True, None, value


def validate_int_param(data: Dict, param_name: str, required: bool = True, 
                       min_value: int = None, max_value: int = None) -> tuple:
    """
    Validate that a parameter is an integer within optional bounds.
    
    Args:
        data: Request JSON data
        param_name: Parameter name to validate
        required: Whether parameter is required
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
        
    Returns:
        Tuple of (is_valid, error_message, value)
    """
    value = data.get(param_name)
    
    if value is None:
        if required:
            return False, f"Missing required field: '{param_name}'", None
        return True, None, None
    
    if not isinstance(value, int) or isinstance(value, bool):
        return False, f"Field '{param_name}' must be an integer, got {type(value).__name__}", None
    
    if min_value is not None and value < min_value:
        return False, f"Field '{param_name}' must be >= {min_value}", None
    
    if max_value is not None and value > max_value:
        return False, f"Field '{param_name}' must be <= {max_value}", None
    
    return True, None, value


def validate_bool_param(data: Dict, param_name: str, required: bool = True) -> tuple:
    """
    Validate that a parameter is a boolean.
    
    Args:
        data: Request JSON data
        param_name: Parameter name to validate
        required: Whether parameter is required
        
    Returns:
        Tuple of (is_valid, error_message, value)
    """
    value = data.get(param_name)
    
    if value is None:
        if required:
            return False, f"Missing required field: '{param_name}'", None
        return True, None, None
    
    if not isinstance(value, bool):
        return False, f"Field '{param_name}' must be a boolean, got {type(value).__name__}", None
    
    return True, None, value


def validate_list_param(data: Dict, param_name: str, required: bool = True) -> tuple:
    """
    Validate that a parameter is a list.
    
    Args:
        data: Request JSON data
        param_name: Parameter name to validate
        required: Whether parameter is required
        
    Returns:
        Tuple of (is_valid, error_message, value)
    """
    value = data.get(param_name)
    
    if value is None:
        if required:
            return False, f"Missing required field: '{param_name}'", None
        return True, None, None
    
    if not isinstance(value, list):
        return False, f"Field '{param_name}' must be a list, got {type(value).__name__}", None
    
    return True, None, value


def shutdown_handler(signum, frame):
    """
    Gracefully shutdown all monitoring threads on signal.
    """
    logger.info("🛑 Received shutdown signal")
    shutdown_all_threads(active_devices, active_devices_lock)
    sys.exit(0)


@app.route('/ConfigurationManagerThingsboard/collectDataFromThingsboard', methods=['POST'])
def collect_data_from_thingsboard():
    """
    Start continuous monitoring of one or more ThingsBoard devices.
    Supports both single device and batch mode.
    
    Expected JSON payload (single device):
    {
        "thingsboardsIP": "localhost",
        "thingsboardPort": 8099,
        "entityId": "71c0e3e0-a8e1-11f0-a091-2d2de22ced6c",
        "entityType": "DEVICE"  # optional, defaults to "DEVICE"
    }
    
    Expected JSON payload (multiple devices):
    {
        "thingsboardsIP": "localhost",
        "thingsboardPort": 8099,
        "entityIds": [
            "71c0e3e0-a8e1-11f0-a091-2d2de22ced6c",
            "abc123-456-789...",
            "def456-789-012..."
        ],
        "entityType": "DEVICE"  # optional, defaults to "DEVICE"
    }
    
    Returns:
        200 OK with monitoring details
        400 Bad Request if validation fails
        401 Unauthorized if ThingsBoard authentication fails
        404 Not Found if device doesn't exist in ThingsBoard
        429 Too Many Requests if device limit reached
        500 Internal Server Error for unexpected errors
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400
        
        is_valid, error, tb_ip = validate_string_param(data, "thingsboardsIP", required=True)
        if not is_valid:
            return jsonify({"error": error}), 400
        
        is_valid, error, tb_port = validate_int_param(data, "thingsboardPort", required=True, 
                                                       min_value=1, max_value=65535)
        if not is_valid:
            return jsonify({"error": error}), 400
        
        is_valid, error, entity_type = validate_string_param(data, "entityType", required=True)
        if not is_valid:
            return jsonify({"error": error}), 400
        entity_type = entity_type or "DEVICE"
        
        # Single device and batch mode
        entity_id_single = data.get("entityId")
        entity_ids_batch = data.get("entityIds")
        
        if not entity_id_single and not entity_ids_batch:
            return jsonify({
                "error": "Missing required field: either 'entityId' (single) or 'entityIds' (batch)"
            }), 400
        
        # Normalize to list
        if entity_id_single:
            is_valid, error, entity_id_single = validate_string_param(data, "entityId", required=True)
            if not is_valid:
                return jsonify({"error": error}), 400
            entity_ids = [entity_id_single]
        else:
            is_valid, error, entity_ids = validate_list_param(data, "entityIds", required=True)
            if not is_valid:
                return jsonify({"error": error}), 400
            
            for idx, eid in enumerate(entity_ids):  # Validate each item in list is string
                if not isinstance(eid, str):
                    return jsonify({
                        "error": f"entityIds[{idx}] must be a string, got {type(eid).__name__}"
                    }), 400
                if not eid.strip():
                    return jsonify({
                        "error": f"entityIds[{idx}] cannot be empty"
                    }), 400
        
        with active_devices_lock:
            current_count = len(active_devices)
        
        if current_count + len(entity_ids) > MAX_CONCURRENT_DEVICES:
            return jsonify({
                "error": f"Device limit exceeded. Current: {current_count}, Requested: {len(entity_ids)}, Max: {MAX_CONCURRENT_DEVICES}"
            }), 429
        
        # Prevalidation: Check devices exist in ThingsBoard
        logger.info(f"🔍 Validating {len(entity_ids)} device(s) in ThingsBoard...")
        
        tb_client = ThingsBoardClient(
            host=tb_ip,
            port=tb_port,
            username=TB_USERNAME,
            password=TB_PASSWORD
        )
        
        if not tb_client.authenticate():
            return jsonify({
                "error": "Failed to authenticate with ThingsBoard. Check credentials or server availability."
            }), 401
        
        # Validate each device exists
        validation_errors = []
        for entity_id in entity_ids:
            if not tb_client.validate_device_exists(entity_id, entity_type):
                validation_errors.append({
                    "entity_id": entity_id,
                    "error": f"Device '{entity_id}' not found in ThingsBoard"
                })
        
        if validation_errors:
            return jsonify({
                "error": "One or more devices not found in ThingsBoard",
                "validation_errors": validation_errors
            }), 404
        
        logger.info(f"✅ All {len(entity_ids)} device(s) validated successfully")
        
        # Start monitoring
        results = []
        
        for entity_id in entity_ids:
            config = {
                "thingsboardsIP": tb_ip,
                "thingsboardPort": tb_port,
                "entityId": entity_id,
                "entityType": entity_type
            }
            
            result = start_device_monitoring(
                entity_id=entity_id,
                config=config,
                active_devices=active_devices,
                active_devices_lock=active_devices_lock,
                kafka_bootstrap=KAFKA_BOOTSTRAP,
                poll_interval=POLL_INTERVAL_SECONDS,
                tb_username=TB_USERNAME,
                tb_password=TB_PASSWORD
            )
            
            results.append(result)
        
        # Summarize results
        success_count = sum(1 for r in results if r['status'] == 'success')
        already_monitoring_count = sum(1 for r in results if r['status'] == 'already_monitoring')
        error_count = sum(1 for r in results if r['status'] == 'error')
        
        return jsonify({
            "message": f"Processed {len(entity_ids)} device(s)",
            "summary": {
                "total": len(entity_ids),
                "success": success_count,
                "already_monitoring": already_monitoring_count,
                "errors": error_count
            },
            "results": results
        }), 200
        
    except Exception as e:
        logger.exception(f"❌ Unexpected error in collectDataFromThingsboard: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route('/ConfigurationManagerThingsboard/stopMonitoring', methods=['POST'])
def stop_monitoring():
    """
    Stop monitoring specific device(s).
    Supports both single device and batch mode.
    
    Expected JSON payload (single device):
    {
        "entityId": "71c0e3e0-a8e1-11f0-a091-2d2de22ced6c"
    }
    
    Expected JSON payload (multiple devices):
    {
        "entityIds": [
            "71c0e3e0-a8e1-11f0-a091-2d2de22ced6c",
            "abc123-456-789...",
            "def456-789-012..."
        ]
    }
    
    Returns:
        200 OK with results for each device
        400 Bad Request if payload is invalid
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400
        
        # Single device and batch mode
        entity_id_single = data.get("entityId")
        entity_ids_batch = data.get("entityIds")
        
        if not entity_id_single and not entity_ids_batch:
            return jsonify({
                "error": "Missing required field: either 'entityId' (single) or 'entityIds' (batch)"
            }), 400
        
        # Normalize to list
        if entity_id_single:
            is_valid, error, entity_id_single = validate_string_param(data, "entityId", required=True)
            if not is_valid:
                return jsonify({"error": error}), 400
            entity_ids = [entity_id_single]
        else:
            is_valid, error, entity_ids = validate_list_param(data, "entityIds", required=True)
            if not is_valid:
                return jsonify({"error": error}), 400
            
            for idx, eid in enumerate(entity_ids):
                if not isinstance(eid, str):
                    return jsonify({
                        "error": f"entityIds[{idx}] must be a string, got {type(eid).__name__}"
                    }), 400
        
        results = []
        
        for entity_id in entity_ids:
            result = stop_device_monitoring(entity_id, active_devices, active_devices_lock)
            results.append(result)
        
        # Summarize results
        success_count = sum(1 for r in results if r['status'] == 'success')
        not_found_count = sum(1 for r in results if r['status'] == 'not_found')
        
        return jsonify({
            "message": f"Processed {len(entity_ids)} device(s)",
            "summary": {
                "total": len(entity_ids),
                "success": success_count,
                "not_found": not_found_count
            },
            "results": results
        }), 200
        
    except Exception as e:
        logger.exception(f"❌ Error stopping monitoring: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route('/ConfigurationManagerThingsboard/stopAllMonitoring', methods=['POST'])
def stop_all_monitoring():
    """
    Stop monitoring ALL active devices.
    Requires explicit confirmation to prevent accidental shutdowns.
    
    Expected JSON payload:
    {
        "confirm": true
    }
    
    Returns:
        200 OK with results for all stopped devices
        400 Bad Request if confirmation missing or invalid
    """
    try:
        data = request.get_json()
        
        is_valid, error, confirm = validate_bool_param(data, "confirm", required=True)
        if not is_valid:
            return jsonify({"error": error}), 400
        
        if confirm is not True:
            return jsonify({
                "error": "Missing confirmation. Send {\"confirm\": true} to proceed"
            }), 400
        
        with active_devices_lock:
            entity_ids = list(active_devices.keys())
        
        if not entity_ids:
            return jsonify({
                "message": "No devices are currently being monitored",
                "summary": {
                    "total": 0,
                    "success": 0,
                    "not_found": 0
                },
                "results": []
            }), 200
        
        logger.info(f"🛑 Stopping ALL monitoring ({len(entity_ids)} device(s))")
        
        # Stop each device
        results = []
        
        for entity_id in entity_ids:
            result = stop_device_monitoring(entity_id, active_devices, active_devices_lock)
            results.append(result)
        
        # Summarize results
        success_count = sum(1 for r in results if r['status'] == 'success')
        not_found_count = sum(1 for r in results if r['status'] == 'not_found')
        
        return jsonify({
            "message": f"Stopped monitoring all {len(entity_ids)} device(s)",
            "summary": {
                "total": len(entity_ids),
                "success": success_count,
                "not_found": not_found_count
            },
            "results": results
        }), 200
        
    except Exception as e:
        logger.exception(f"❌ Error stopping all monitoring: {e}")
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
                t = info.get('thread')
                is_alive = bool(t and t.is_alive())

                status[entity_id] = {
                    "started_at": info['started_at'].isoformat(),
                    "last_poll": info['last_poll'].isoformat() if info['last_poll'] else None,
                    "is_alive": is_alive,
                    "status": info.get('status', None),
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
        alive_threads = sum(
            1 for info in active_devices.values()
            if info.get('thread') and info['thread'].is_alive()
        )

    # Cuenta real de threads "monitor-*" vivos en el proceso (detecta huérfanos)
    monitor_threads_alive = sum(
        1 for t in threading.enumerate()
        if t.name.startswith("monitor-") and t.is_alive()
    )

    return jsonify({
        "status": "healthy",
        "service": "ThingsBoard Collector",
        "kafka_bootstrap": KAFKA_BOOTSTRAP,
        "active_devices": active_count,
        "alive_threads": alive_threads,  # threads vivos que SIGUES trackeando
        "monitor_threads_alive": monitor_threads_alive,  # threads "monitor-*" vivos reales
        "orphan_monitor_threads": max(0, monitor_threads_alive - alive_threads),
        "max_devices": MAX_CONCURRENT_DEVICES
    }), 200

if __name__ == '__main__':
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Handlers
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