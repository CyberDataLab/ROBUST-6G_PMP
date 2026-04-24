"""
configuration_manager_logic.py  (v4)

Business logic layer for the Configuration Manager API.

Changes from v3:
- When a producer tool is deployed (tshark, telegraf, fluentd, falco, flow_module, snort3),
  the resolved topic values are saved to a fixed MongoDB CM document with _id="kafka_topics".
- When a consumer tool is deployed (flow_module, snort3, opensearch/logstash), the real topic
  values are read from that document before calling launch(), so the .env always has the
  correct topic names even if they differ from the defaults.
- If MongoDB CM is unreachable the Pydantic model defaults are used as fallback (no crash).
- PRODUCER_TOPIC_VARS and CONSUMER_TOPIC_VARS are imported from start_containers.py so the
  dependency map lives in a single place.
"""

import hashlib
import importlib.util
import json
import os
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv

from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import ServerSelectionTimeoutError

# ---------------------------------------------------------------------------
# Path to start_containers.py
# ---------------------------------------------------------------------------
LAUNCHER_PATH = Path(__file__).resolve().parent.parent.parent / "Launcher" / "start_containers.py"

# ---------------------------------------------------------------------------
# MongoDB Configuration Manager connection.
# MONGO_CM_URI is written to .init_pmp_env by start_containers.py on first run.
# ---------------------------------------------------------------------------
ENV_PATH = Path(__file__).resolve().parent.parent.parent / "Launcher" / ".init_pmp_env"
load_dotenv(ENV_PATH, override=True)

MONGO_CM_URI = (
    os.getenv("MONGO_CM_URI_HOST")
    or os.getenv("MONGO_CM_URI")
    or "mongodb://admin:admin@localhost:27018/?authSource=admin"
)
MONGO_CM_DB         = "configuration_manager"
MONGO_CM_COLLECTION = "deployments"
KAFKA_TOPICS_DOC_ID = "kafka_topics"   # fixed _id for the topics state document

# ---------------------------------------------------------------------------
# ALWAYS_ENV_VARS - mirrors start_containers.py, used to protect internal vars
# ---------------------------------------------------------------------------
ALWAYS_ENV_VARS: List[str] = [
    "MACHINE_ID",
    "NETWORK_MODE",
    "PFD",
    "COMPOSE_PROFILES",
    "TZ",
    "KAFKA_BOOTSTRAP",
    "KAFKA_LAN_HOSTNAME",
]

# ---------------------------------------------------------------------------
# Mapping: toolName as received in API -> (module, tool in MODULE_REGISTRY)
# ---------------------------------------------------------------------------
TOOL_NAME_TO_MODULE: Dict[str, Tuple[str, str]] = {
    "tshark":           ("collection_module",    "tshark"),
    "flow_module":      ("flow_module",          "flow_module"),
    "telegraf":         ("collection_module",    "telegraf"),
    "fluentd":          ("collection_module",    "fluentd"),
    "falco":            ("collection_module",    "falco"),
    "snort3":           ("alert_module",         "alert_module"),
    "kafka":            ("communication_module", "kafka"),
    "filebeat":         ("communication_module", "filebeat"),
    "mongodb":          ("db_module",            "mongodb"),
    "mongodb_cm":       ("db_module",            "mongodb_cm"),
    "redis":            ("db_module",            "redis"),
    "prometheus":       ("aggregation_module",   "prometheus"),
    "opensearch":       ("aggregation_module",   "opensearch"),
    "alarm_collector":  ("thingsboard_module",   "alarm_collector"),
}


# ===========================================================================
# Pydantic models for each tool.
# Every field carries its default value. extra="forbid" rejects unknown fields.
# ===========================================================================

class TelegrafConfig(BaseModel):
    """Pydantic model for Telegraf configurable environment variables."""
    model_config = {"extra": "forbid"}

    ENABLE_TELEGRAF:                str = "1"
    TELEGRAF_TO_PROMETHEUS_PORT:    str = "9273"
    TELEGRAF_BASE_TOPIC:            str = "telegraf_metrics"
    TELEGRAF_GENERAL_INTERVAL:      str = "30s"


class TsharkConfig(BaseModel):
    """Pydantic model for Tshark configurable environment variables."""
    model_config = {"extra": "forbid"}

    TSHARK_BASE_TOPIC:              str = "tshark_traces"
    TSHARK_SIZE_LIMIT_ROTATION:     str = "31457280"


class FluentdConfig(BaseModel):
    """Pydantic model for Fluentd configurable environment variables."""
    model_config = {"extra": "forbid"}

    ENABLE_FLUENTD:                 str = "1"
    FLUENTD_TO_PROMETHEUS_PORT:     str = "24231"
    FLUENTD_INTERNAL_PORT:          str = "24220"
    FLUENTD_FILE_SIZE_LIMIT:        str = "20971520"
    FLUENTD_SYSLOG_BASE_TOPIC:      str = "syslog_logs"
    FLUENTD_SYSTEMD_BASE_TOPIC:     str = "systemd_logs"


class FalcoConfig(BaseModel):
    """Pydantic model for Falco configurable environment variables."""
    model_config = {"extra": "forbid"}

    ENABLE_FALCO:                   str = "1"
    FALCO_BASE_TOPIC:               str = "falco_events"
    FALCO_SKIP_DRIVER_LOADER:       str = "1"
    FALCO_EXPORTER_PORT:            str = "9376"


class KafkaConfig(BaseModel):
    """Pydantic model for Kafka configurable environment variables."""
    model_config = {"extra": "forbid"}

    KAFKA_BOOTSTRAP:                str = "kafka_robust6g-node1.lan:9094"
    KAFKA_LAN_HOSTNAME:             str = "kafka_robust6g-node1.lan"
    KAFKA_PORT_EXTERNAL_LAN:        str = "9094"
    KAFKA_PORT_INTERNAL:            str = "29092"
    KAFKA_LOG_RETENTION_MS:         str = "86400000"
    KAFKA_LOG_RETENTION_BYTES:      str = "1073741824"
    KAFKA_LOG_CLEANUP_POLICY:       str = "delete"
    KAFKA_LOG_SEGMENT_BYTES:        str = "268435456"
    KAFKA_LOG_ROLL_MS:              str = "3600000"


class FilebeatConfig(BaseModel):
    """Pydantic model for Filebeat configurable environment variables."""
    model_config = {"extra": "forbid"}

    FILEBEAT_BULK_MAX_SIZE:         str = "4096"
    FILEBEAT_COMPRESION:            str = "lz4"


class PrometheusConfig(BaseModel):
    """Pydantic model for Prometheus configurable environment variables."""
    model_config = {"extra": "forbid"}

    PROMETHEUS_PORT:                    str = "9090"
    DISCOVERY_AGENT_SCAN_PORT:          str = "9999"
    DISCOVERY_AGENT_SCAN_TIMEOUT:       str = "0.2"
    DISCOVERY_AGENT_REFRESH_INTERVAL:   str = "30"
    DISCOVERY_AGENT_PORT:               str = "8100"


class OpenSearchConfig(BaseModel):
    """Pydantic model for OpenSearch + Logstash configurable environment variables."""
    model_config = {"extra": "forbid"}

    OPENSEARCH_HOST:                str = "opensearch-node"
    OPENSEARCH_CLUSTER_NAME:        str = "robust6g-cluster"
    OPENSEARCH_NODE_NAME:           str = "opensearch"
    OPENSEARCH_REST_API_PORT:       str = "9200"
    OPENSEARCH_ANALYSER_PORT:       str = "9600"
    OPENSEARCH_DASHBOARD_PORT:      str = "5601"
    # Logstash topic defaults - overridden with real values from MongoDB CM at deploy time
    TELEGRAF_BASE_TOPIC:            str = "telegraf_metrics"
    TSHARK_BASE_TOPIC:              str = "tshark_traces"
    FLUENTD_SYSLOG_BASE_TOPIC:      str = "syslog_logs"
    FLUENTD_SYSTEMD_BASE_TOPIC:     str = "systemd_logs"
    FALCO_BASE_TOPIC:               str = "falco_events"


class MongoDBConfig(BaseModel):
    """Pydantic model for MongoDB main instance configurable environment variables."""
    model_config = {"extra": "forbid"}

    MONGO_INITDB_ROOT_USERNAME:     str = "admin"
    MONGO_PORT:                     str = "27017"


class MongoDBCMConfig(BaseModel):
    """Pydantic model for MongoDB Configuration Manager instance configurable environment variables."""
    model_config = {"extra": "forbid"}

    MONGO_CM_INITDB_ROOT_USERNAME:  str = "admin"
    MONGO_CM_PORT:                  str = "27018"


class RedisConfig(BaseModel):
    """Pydantic model for Redis configurable environment variables."""
    model_config = {"extra": "forbid"}

    REDIS_HOST:                             str = "redis_robust6g"
    REDIS_PORT:                             str = "6379"
    REDIS_USER:                             str = "0"
    REDIS_PASSWORD:                         str = ""
    REDIS_MAXMEMORY_SAMPLES:                str = "5"
    REDIS_IO_THREADS:                       str = "4"
    REDIS_STREAM_NODE_MAX_BYTES:            str = "4096"
    REDIS_STREAM_NODE_MAX_ENTRIES:          str = "100"
    REDIS_MAXCLIENTS:                       str = "10000"
    KTRW_KAFKA_AUTO_OFFSET_RESET:           str = "latest"
    KTRW_KAFKA_ENABLE_AUTO_COMMIT:          str = "true"
    KTRW_KAFKA_GROUP_ID:                    str = "redis-streamer"
    KTRW_REDIS_MAX_STREAM_LENGTH:           str = "1000"
    KTRW_REDIS_STREAM_TTL_SECONDS:          str = "21600"
    KTRW_PARTITION_ASSIGNMENT_STRATEGY:     str = "cooperative-sticky"
    KTRW_SESSION_TIMEOUT_MS:                str = "10000"
    KTRW_MAX_POLL_INTERVAL_MS:              str = "300000"
    KTRW_KAFKA_TOPIC_REFRESH_INTERVAL:      str = "30"
    KTRW_REDIS_CLEANUP_INTERVAL:            str = "300"
    KTRW_REDIS_RETENTION_HOURS:             str = "2"
    KTRW_REDIS_EMERGENCY_RETENTION_HOURS:   str = "1"
    KTRW_REDIS_MEMORY_THRESHOLD:            str = "0.85"


class FlowModuleConfig(BaseModel):
    """Pydantic model for Flow Module configurable environment variables."""
    model_config = {"extra": "forbid"}

    # TSHARK_BASE_TOPIC default here is the fallback if MongoDB CM is unreachable.
    # The real value is resolved from MongoDB CM before launch() is called.
    TSHARK_BASE_TOPIC:                                  str = "tshark_traces"
    CIC_KAFKA_BASE_TOPIC_OUT:                           str = "cic_flow"
    FLOW_KAFKA_GROUP:                                   str = "flow-module"
    FLOW_PCAP_ROTATE_SIZE_MB:                           str = "102400"
    FLOW_CIC_ROTATE_SIZE_MB:                            str = "51200"
    FLOW_ROTATE_TIME_SEC:                               str = "0.5"
    FLOW_PACKET_QUEUE_MAX:                              str = "100000"
    FLOW_WRITER_FLUSH_EVERY:                            str = "100"
    FLOW_WATCHDOG_STALL_SECS:                           str = "120"
    FLOW_KAFKA_CONSUMER_AUTO_OFFSET_RESET:              str = "earliest"
    FLOW_KAFKA_CONSUMER_ENABLE_AUTO_COMMIT:             str = "true"
    FLOW_KAFKA_CONSUMER_PARTITION_ASSIGNMENT_STRATEGY:  str = "cooperative-sticky"
    FLOW_KAFKA_CONSUMER_ENABLE_PARTITION_EOF:           str = "true"
    FLOW_KAFKA_CONSUMER_ALLOW_AUTO_CREATE_TOPICS:       str = "true"
    FLOW_KAFKA_PRODUCER_LINGER_MS:                      str = "5"
    FLOW_KAFKA_PRODUCER_BATCH_SIZE:                     str = "32768"
    FLOW_KAFKA_PRODUCER_COMPRESSION:                    str = "zstd"


class Snort3Config(BaseModel):
    """Pydantic model for Snort3 (alert_module) configurable environment variables."""
    model_config = {"extra": "forbid"}

    # TSHARK_BASE_TOPIC default here is the fallback if MongoDB CM is unreachable.
    # The real value is resolved from MongoDB CM before launch() is called.
    TSHARK_BASE_TOPIC:                                      str = "tshark_traces"
    SNORT_KAFKA_GROUP_ID:                                   str = "alert-module"
    SNORT_KAFKA_TOPIC_IN:                                   str = "tshark_traces"
    SNORT_KAFKA_TOPIC_OUT:                                  str = "snort_alerts"
    SNORT_ALERT_TAP_IFACE:                                  str = "tap0"
    SNORT_KAFKA_MESSAGE_FIELD:                              str = "_source"
    SNORT_CONSUMER_KAFKA_AUTO_OFFSET_RESET:                 str = "earliest"
    SNORT_CONSUMER_KAFKA_ENABLE_AUTO_COMMIT:                str = "true"
    SNORT_CONSUMER_KAFKA_PARTITION_ASSIGNMENT_STRATEGY:     str = "cooperative-sticky"
    SNORT_CONSUMER_KAFKA_ENABLE_PARTITION_EOF:              str = "true"
    SNORT_CONSUMER_KAFKA_ALLOW_AUTO_CREATE_TOPICS:          str = "true"
    SNORT_CONSUMER_FETCH_MIN_BYTES:                         str = "1048576"
    SNORT_CONSUMER_FETCH_WAIT_MAX_MS:                       str = "50"
    SNORT_CONSUMER_QUEUED_MAX_MESSAGES_KBYTES:              str = "262144"
    SNORT_CONSUMER_MAX_POLL_INTERVAL_MS:                    str = "900000"
    SNORT_CONSUMER_SESSION_TIMEOUT_MS:                      str = "10000"
    SNORT_PRODUCER_KAFKA_PRODUCER_LINGER_MS:                str = "5"
    SNORT_PRODUCER_BATCH_NUM_MESSAGES:                      str = "10000"
    SNORT_PRODUCER_KAFKA_PRODUCER_BATCH_SIZE:               str = "32768"
    SNORT_PRODUCER_KAFKA_PRODUCER_COMPRESSION:              str = "zstd"


class AlarmCollectorConfig(BaseModel):
    """Pydantic model for ThingsBoard alarm collector configurable environment variables."""
    model_config = {"extra": "forbid"}

    TB_USERNAME:    str = "tenant@thingsboard.org"
    TB_PASSWORD:    str = "tenant"
    TB_USE_HTTPS:   str = "false"


# Map toolName -> its Pydantic config class
TOOL_CONFIG_MODELS: Dict[str, type] = {
    "tshark":           TsharkConfig,
    "flow_module":      FlowModuleConfig,
    "telegraf":         TelegrafConfig,
    "fluentd":          FluentdConfig,
    "falco":            FalcoConfig,
    "snort3":           Snort3Config,
    "kafka":            KafkaConfig,
    "filebeat":         FilebeatConfig,
    "mongodb":          MongoDBConfig,
    "mongodb_cm":       MongoDBCMConfig,
    "redis":            RedisConfig,
    "prometheus":       PrometheusConfig,
    "opensearch":       OpenSearchConfig,
    "alarm_collector":  AlarmCollectorConfig,
}


# ===========================================================================
# Request / Response models used by the API layer
# ===========================================================================

class DeployRequest(BaseModel):
    """
    Deployment request body. Contains only the env var overrides for the tool.
    The toolName is received as a query parameter in the API endpoint, not here.
    An empty body {} is valid and means: use all defaults for that tool.
    """
    configuration: Optional[Dict[str, Any]] = Field(default_factory=dict)


class UpdateConfigurationRequest(BaseModel):
    """Request to update an existing deployment identified by its config_id."""
    config_id: str
    configuration: Optional[Dict[str, Any]] = Field(default_factory=dict)


# ===========================================================================
# MongoDB helpers
# ===========================================================================

def get_mongo_collection() -> Optional[Collection]:
    """
    Return the MongoDB CM deployments collection, or None if unreachable.
    """
    try:
        client = MongoClient(MONGO_CM_URI, serverSelectionTimeoutMS=3000)
        client.server_info()
        db = client[MONGO_CM_DB]
        return db[MONGO_CM_COLLECTION]
    except ServerSelectionTimeoutError:
        print("Warning: MongoDB CM is unreachable. Deployments will not be persisted.")
        return None
    except Exception as e:
        print(f"Warning: MongoDB CM connection error: {e}")
        return None


def save_deployment_to_mongo(
    collection: Collection,
    config_id: str,
    endpoint: str,
    tool_name: str,
    resolved_env: Dict[str, str]
) -> None:
    """
    Insert or replace a deployment document in MongoDB using config_id as _id.
    """
    document = {
        "_id":          config_id,
        "endpoint":     endpoint,
        "tool_name":    tool_name,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "resolved_env": resolved_env,
    }
    try:
        collection.replace_one({"_id": config_id}, document, upsert=True)
    except Exception as e:
        print(f"Warning: could not save deployment to MongoDB: {e}")


def get_deployment_from_mongo(collection: Collection, config_id: str) -> Optional[Dict]:
    """
    Retrieve a deployment document from MongoDB by its config_id (_id field).
    """
    try:
        return collection.find_one({"_id": config_id})
    except Exception as e:
        print(f"Warning: could not read from MongoDB: {e}")
        return None


def update_kafka_topics_in_mongo(
    collection: Collection,
    producer_topic_updates: Dict[str, str]
) -> None:
    """
    Upsert the fixed kafka_topics document with the latest topic names published by a producer tool.
    The document uses _id=KAFKA_TOPICS_DOC_ID and stores one key per topic variable.
    """
    if not producer_topic_updates:
        return

    update_fields = dict(producer_topic_updates)
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        collection.update_one(
            {"_id": KAFKA_TOPICS_DOC_ID},
            {"$set": update_fields},
            upsert=True
        )
        print(f"kafka_topics document updated: {list(producer_topic_updates.keys())}")
    except Exception as e:
        print(f"Warning: could not update kafka_topics document: {e}")


def get_kafka_topics_from_mongo(collection: Collection) -> Dict[str, str]:
    """
    Read the current kafka_topics document from MongoDB CM.
    Returns an empty dict if the document does not exist yet or MongoDB is unreachable.
    """
    try:
        doc = collection.find_one({"_id": KAFKA_TOPICS_DOC_ID})
        if doc is None:
            return {}
        # Remove internal MongoDB fields before returning
        doc.pop("_id", None)
        doc.pop("updated_at", None)
        return {k: str(v) for k, v in doc.items()}
    except Exception as e:
        print(f"Warning: could not read kafka_topics from MongoDB: {e}")
        return {}


# ===========================================================================
# Core logic functions
# ===========================================================================

def _load_producer_consumer_maps() -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """
    Import PRODUCER_TOPIC_VARS and CONSUMER_TOPIC_VARS from start_containers.py.
    Returns (producer_map, consumer_map). Falls back to empty dicts on import error.
    """
    spec = importlib.util.spec_from_file_location("start_containers", str(LAUNCHER_PATH))

    if spec is None or spec.loader is None:
        print(f"Warning: could not load start_containers.py from {LAUNCHER_PATH}")
        return {}, {}

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"Warning: could not exec start_containers.py: {e}")
        return {}, {}

    producer_map = getattr(module, "PRODUCER_TOPIC_VARS", {})
    consumer_map = getattr(module, "CONSUMER_TOPIC_VARS", {})
    return producer_map, consumer_map


def validate_and_parse_config(
    tool_name: str,
    incoming_config: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, str]]:
    """
    Validate tool_name and parse the incoming config dict with the correct Pydantic model.
    Returns (is_valid, error_message, resolved_env_dict).
    Pydantic fills defaults for missing fields and rejects unknown fields (extra=forbid).
    """
    if tool_name not in TOOL_CONFIG_MODELS:
        valid_names = list(TOOL_CONFIG_MODELS.keys())
        return False, f"Unknown toolName '{tool_name}'. Valid tools: {valid_names}", {}

    config_model_class = TOOL_CONFIG_MODELS[tool_name]

    try:
        parsed_config = config_model_class.model_validate(incoming_config or {})
    except Exception as e:
        return False, f"Invalid configuration for tool '{tool_name}': {e}", {}

    resolved: Dict[str, str] = {
        k: str(v) for k, v in parsed_config.model_dump().items()
    }

    return True, "", resolved


def resolve_consumer_topics(
    tool_name: str,
    resolved_env: Dict[str, str],
    collection: Optional[Collection]
) -> Dict[str, str]:
    """
    For consumer tools, overwrite their topic variables with the real values stored
    in the kafka_topics MongoDB CM document. Falls back to Pydantic defaults (already
    in resolved_env) if MongoDB CM is unavailable or the document does not exist yet.
    """
    _, consumer_map = _load_producer_consumer_maps()

    needed_topics = consumer_map.get(tool_name, [])

    if not needed_topics:
        return resolved_env

    if collection is None:
        print(f"Warning: MongoDB CM unreachable. Using default topic values for '{tool_name}'.")
        return resolved_env

    stored_topics = get_kafka_topics_from_mongo(collection)

    if not stored_topics:
        print(f"Warning: kafka_topics document not found in MongoDB CM. Using defaults for '{tool_name}'.")
        return resolved_env

    updated_env = dict(resolved_env)

    # Special case: snort3 consumes the topic produced by tshark, but its actual input variable is SNORT_KAFKA_TOPIC_IN.
    if tool_name == "snort3" and "TSHARK_BASE_TOPIC" in stored_topics:
        real_tshark_topic = stored_topics["TSHARK_BASE_TOPIC"]

        if updated_env.get("TSHARK_BASE_TOPIC") != real_tshark_topic:
            print(
                f"  Topic override for 'snort3': "
                f"TSHARK_BASE_TOPIC = '{real_tshark_topic}' "
                f"(was '{updated_env.get('TSHARK_BASE_TOPIC')}')"
            )

        if updated_env.get("SNORT_KAFKA_TOPIC_IN") != real_tshark_topic:
            print(
                f"  Topic override for 'snort3': "
                f"SNORT_KAFKA_TOPIC_IN = '{real_tshark_topic}' "
                f"(was '{updated_env.get('SNORT_KAFKA_TOPIC_IN')}')"
            )

        updated_env["TSHARK_BASE_TOPIC"] = real_tshark_topic
        updated_env["SNORT_KAFKA_TOPIC_IN"] = real_tshark_topic

    for topic_var in needed_topics:
        if topic_var in stored_topics:
            real_value = stored_topics[topic_var]
            if updated_env.get(topic_var) != real_value:
                print(f"  Topic override for '{tool_name}': {topic_var} = '{real_value}' (was '{updated_env.get(topic_var)}')")
            updated_env[topic_var] = real_value
        else:
            print(f"  Warning: '{topic_var}' not in kafka_topics document. Using default '{updated_env.get(topic_var)}'.")

    return updated_env


def persist_producer_topics(
    tool_name: str,
    resolved_env: Dict[str, str],
    collection: Optional[Collection]
) -> None:
    """
    For producer tools, save their resolved topic variable values to the kafka_topics document
    in MongoDB CM so consumer tools can read them later.
    """
    if collection is None:
        print(f"Warning: MongoDB CM unreachable. Producer topics for '{tool_name}' will not be persisted.")
        return

    producer_map, _ = _load_producer_consumer_maps()
    topic_vars = producer_map.get(tool_name, [])

    if not topic_vars:
        return

    producer_topic_updates = {
        var: resolved_env[var]
        for var in topic_vars
        if var in resolved_env
    }

    if producer_topic_updates:
        update_kafka_topics_in_mongo(collection, producer_topic_updates)


def build_config_id(endpoint: str, tool_name: str, resolved_env: Dict[str, str]) -> str:
    """
    Generate a deterministic MD5 hash ID from endpoint, tool_name and resolved env dict.
    """
    raw = json.dumps(
        {"endpoint": endpoint, "tool_name": tool_name, "resolved_env": resolved_env},
        sort_keys=True
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_selected_from_tool_name(tool_name: str) -> "OrderedDict[str, List[str]]":
    """
    Build the OrderedDict[module -> tools] structure expected by start_containers.py
    from a single toolName string as received via the API query parameter.
    """
    selected: OrderedDict[str, List[str]] = OrderedDict()

    if tool_name not in TOOL_NAME_TO_MODULE:
        return selected

    module, tool_in_registry = TOOL_NAME_TO_MODULE[tool_name]
    selected[module] = [tool_in_registry]

    return selected


def call_start_containers(
    selected: "OrderedDict[str, List[str]]",
    env_overrides: Dict[str, str]
) -> Tuple[bool, str]:
    """
    Import and call launch() from start_containers.py with resolved selected modules and env overrides.
    Returns (success, error_message).
    """
    spec = importlib.util.spec_from_file_location("start_containers", str(LAUNCHER_PATH))

    if spec is None or spec.loader is None:
        return False, f"Could not locate start_containers.py at {LAUNCHER_PATH}"

    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        return False, f"Error loading start_containers.py: {e}"

    try:
        module.launch(selected=selected, env_overrides=env_overrides)
        return True, ""
    except Exception as e:
        return False, f"Error during launch: {e}"


def process_deploy_request(
    tool_name: str,
    request: DeployRequest,
    endpoint: str,
    allowed_tool_names: List[str]
) -> Dict[str, Any]:
    """
    Main logic handler for all deploy endpoints.
    1. Validates tool and parses config via Pydantic (fills defaults).
    2. If producer: persists its topic values to MongoDB CM kafka_topics document.
    3. If consumer: reads real topic values from MongoDB CM and injects them into env_overrides.
    4. Saves deployment to MongoDB CM.
    5. Calls start_containers.launch().
    """
    if tool_name not in allowed_tool_names:
        return {
            "status": "error",
            "message": (
                f"Tool '{tool_name}' is not valid for endpoint '{endpoint}'. "
                f"Allowed tools: {allowed_tool_names}"
            )
        }

    is_valid, error_msg, resolved_env = validate_and_parse_config(
        tool_name=tool_name,
        incoming_config=request.configuration or {}
    )

    if not is_valid:
        return {"status": "error", "message": error_msg}

    collection = get_mongo_collection()

    # If this tool produces Kafka topics, persist them so consumers can find them later
    persist_producer_topics(tool_name, resolved_env, collection)

    # If this tool consumes Kafka topics, inject the real topic values from MongoDB CM
    resolved_env = resolve_consumer_topics(tool_name, resolved_env, collection)

    config_id = build_config_id(endpoint, tool_name, resolved_env)

    if collection is not None:
        save_deployment_to_mongo(
            collection=collection,
            config_id=config_id,
            endpoint=endpoint,
            tool_name=tool_name,
            resolved_env=resolved_env
        )

    selected = build_selected_from_tool_name(tool_name)

    success, error_msg = call_start_containers(
        selected=selected,
        env_overrides=resolved_env
    )

    if not success:
        return {"status": "error", "message": error_msg}

    return {
        "status":           "success",
        "config_id":        config_id,
        "message":          f"Deployment started successfully via endpoint '{endpoint}'.",
        "deployed_tool":    tool_name,
        "kafka_bootstrap":  resolved_env.get("KAFKA_BOOTSTRAP", "kafka_robust6g-node1.lan:9094"),
    }


def process_update_configuration(
    tool_name: str,
    request: UpdateConfigurationRequest
) -> Dict[str, Any]:
    """
    Logic handler for updateConfiguration endpoint.
    Retrieves the existing deployment by config_id, merges new values, applies topic resolution,
    and redeploys.
    """
    collection = get_mongo_collection()

    if collection is None:
        return {
            "status":  "error",
            "message": "MongoDB CM is unavailable. Cannot retrieve existing configuration."
        }

    existing = get_deployment_from_mongo(collection, request.config_id)

    if existing is None:
        return {
            "status":  "error",
            "message": f"No deployment found with config_id '{request.config_id}'."
        }

    base_env: Dict[str, str] = dict(existing.get("resolved_env", {}))
    endpoint: str = existing.get("endpoint", "unknown")
    stored_tool_name: str = existing.get("tool_name", tool_name)

    is_valid, error_msg, resolved_env = validate_and_parse_config(
        tool_name=tool_name,
        incoming_config=request.configuration or {}
    )

    if not is_valid:
        return {"status": "error", "message": error_msg}

    base_env.update(resolved_env)

    # Re-apply producer/consumer topic logic on update as well
    persist_producer_topics(tool_name, base_env, collection)
    base_env = resolve_consumer_topics(tool_name, base_env, collection)

    new_config_id = build_config_id(endpoint + "_updated", tool_name, base_env)

    save_deployment_to_mongo(
        collection=collection,
        config_id=new_config_id,
        endpoint=endpoint,
        tool_name=tool_name,
        resolved_env=base_env
    )

    selected = build_selected_from_tool_name(stored_tool_name)

    success, error_msg = call_start_containers(
        selected=selected,
        env_overrides=base_env
    )

    if not success:
        return {"status": "error", "message": error_msg}

    return {
        "status":           "success",
        "old_config_id":    request.config_id,
        "new_config_id":    new_config_id,
        "message":          "Configuration updated and redeployment started.",
        "updated_tool":     tool_name,
    }


def get_configuration_options(tool_name: str) -> Dict[str, Any]:
    """
    Return all configurable environment variables for a given tool with their default values.
    Reads defaults directly from the Pydantic model fields by instantiating it with no arguments.
    """
    if tool_name not in TOOL_CONFIG_MODELS:
        return {
            "status":  "error",
            "message": f"Unknown tool '{tool_name}'. Valid tools: {list(TOOL_CONFIG_MODELS.keys())}"
        }

    config_model_class = TOOL_CONFIG_MODELS[tool_name]
    default_instance = config_model_class()
    defaults_dict = default_instance.model_dump()

    variables: List[Dict[str, str]] = []
    for var_name, default_value in defaults_dict.items():
        variables.append({
            "name":          var_name,
            "default_value": str(default_value),
        })

    return {
        "status":                   "success",
        "toolName":                 tool_name,
        "configurable_variables":   variables,
    }


def get_configuration_by_id(config_id: str) -> Dict[str, Any]:
    """
    Retrieve and return a stored deployment configuration from MongoDB CM by its config_id.
    """
    collection = get_mongo_collection()

    if collection is None:
        return {
            "status":  "error",
            "message": "MongoDB CM is unavailable."
        }

    document = get_deployment_from_mongo(collection, config_id)

    if document is None:
        return {
            "status":  "error",
            "message": f"No configuration found with config_id '{config_id}'."
        }

    document.pop("_id", None)

    return {
        "status":    "success",
        "config_id": config_id,
        "data":      document,
    }


def get_kafka_topics_state() -> Dict[str, Any]:
    """
    Return the current kafka_topics state document from MongoDB CM.
    Useful for debugging and for the API to expose the current topic map.
    """
    collection = get_mongo_collection()

    if collection is None:
        return {
            "status":  "error",
            "message": "MongoDB CM is unavailable."
        }

    topics = get_kafka_topics_from_mongo(collection)

    if not topics:
        return {
            "status":  "not_found",
            "message": "No kafka_topics document found. Deploy at least one producer tool first.",
            "topics":  {}
        }

    return {
        "status": "success",
        "topics": topics,
    }
