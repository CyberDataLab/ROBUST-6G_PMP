#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path


LAUNCHER_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAUNCHER_DIR.parent
GUI_DIR = REPO_ROOT / "GUI" / "robust-6g-dashboard"
GUI_ENV_FILE = GUI_DIR / ".env"
LAUNCHER_ENV_FILE = LAUNCHER_DIR / ".env"
LAUNCHER_INIT_ENV_FILE = LAUNCHER_DIR / ".init_pmp_env"
INTERNAL_LOGS_DIR = REPO_ROOT / "Internal_logs"
RUNTIME_DIR = REPO_ROOT / ".runtime" / "bootstrap_gui_backend"

BOOTSTRAP_LOG_FILE = INTERNAL_LOGS_DIR / "bootstrap_gui_backend.log"
CONFIGURATION_MANAGER_LOG_FILE = INTERNAL_LOGS_DIR / "configuration_manager_api.log"
GUI_LOG_FILE = INTERNAL_LOGS_DIR / "gui_dashboard.log"

API_PID_FILE = RUNTIME_DIR / "configuration_manager_api.pid"
GUI_PID_FILE = RUNTIME_DIR / "gui_dashboard.pid"
STATE_FILE = RUNTIME_DIR / "state.json"

CONFIGURATION_MANAGER_API_NAME = "configuration_manager_api"
NRTDR_API_NAME = "nrtdr_api"
NRTDR_API_CONTAINER_NAME = "nrtdr_api_robust6g"
HDR_API_NAME = "hdr_api"
HDR_API_CONTAINER_NAME = "hdr_api_robust6g"
DT_API_NAME = "dt_api"
DT_API_CONTAINER_NAME = "dt_api_robust6g"
GUI_PROCESS_NAME = "gui_dashboard"

MODULE_COMPOSE_FILES = {
    "apis_module": [
        "APIs/rest_apis.yml",
    ],
    "communication_module": [
        "Communication_Bus/Docker/communication_bus_compose.yml",
    ],
    "alert_module": [
        "Alert_Module/Docker/alert_module_compose.yml",
    ],
    "collection_module": [
        "Data_Collection_Module/Docker/data_collection_module_compose.yml",
    ],
    "flow_module": [
        "Flow_Module/Docker/flow_module_compose.yml",
    ],
    "db_module": [
        "Databases_module/Docker/db_module_compose.yml",
    ],
    "aggregation_module": [
        "Aggregation_Normalisation_Module/Docker/aggregation_normalisation_compose.yml",
    ],
    "thingsboard_module": [
        "ThingsBoard_Collector_Module/Docker/thingsboard_collector_compose.yml",
    ],
}

BASE_CONTAINERS = [
    "kafka_robust6g",
    "filebeat_robust6g",
    "mongodb_robust6g",
    "mongodb_cm_robust6g",
    "postgres_gui_robust6g",
    "redis_robust6g",
    "redis_worker_robust6g",
    "mimir_robust6g",
    "prometheus_server_robust6g",
    "opensearch_node_robust6g",
]

API_TOOL_CONTAINERS = [
    "tshark_robust6g",
    "device_info_robust6g",
    "flow_module_robust6g",
    "telegraf_robust6g",
    "fluentd_robust6g",
    "falco_robust6g",
    "falco_exporter_robust6g",
    "alert_module_robust6g",
    "thingsboard_collector_robust6g",
]

ASSOCIATED_CONTAINERS = [
    "discovery_agent_robust6g", # This container is associated with Promtheus, but it is not an API tool itself
    "opensearch_dashboards_robust6g", # This container is associated with OpenSearch, but it is not an API tool itself
    "logstash_robust6g", # This container is associated with OpenSearch, but it is not an API tool itself
]


def ensure_runtime_directories(logs_dir: Path | None = None) -> Path:
    effective_logs_dir = logs_dir or INTERNAL_LOGS_DIR
    effective_logs_dir.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return effective_logs_dir
