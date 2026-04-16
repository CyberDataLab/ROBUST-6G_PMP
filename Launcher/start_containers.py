#!/usr/bin/env python3

import os
import subprocess
import platform
import sys
import secrets
import string
from pathlib import Path
import argparse
import socket

from collections import OrderedDict
from typing import Dict, Iterable, List, Tuple, Optional

MODULE_COMPOSE_FILES: Dict[str, List[str]] = {
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

class cmd_parser:
    """
    Parse CLI arguments to select docker-compose modules (files/stacks) and
    their service profiles (tools).

    Behaviors:
      - "all" positional (e.g., "python3 main.py all") -> all modules, all tools
      - No args -> all modules, all tools
      - Repeated pairs: "-m <module> -t <tools>"; "tools" can be:
           * "all" (expands to every tool in that module)
           * a comma/space-separated list (e.g., "telegraf, fluentd")
      - Returns:
           * selected: OrderedDict[str, List[str]]  (module -> list of tools)
           * compose profiles: List[str]            (e.g., ["collection_module.telegraf", ...])
    """

    # Dictionary that associates a module with its service.
    MODULE_REGISTRY: Dict[str, List[str]] = {
        "alert_module":         ["alert_module"],
        "communication_module": ["kafka", "filebeat"],
        "collection_module":    ["fluentd", "telegraf", "tshark", "falco", "info"],
        "flow_module":          ["flow_module"],
        "db_module":            ["mongodb", "redis"],
        "aggregation_module":   ["prometheus", "opensearch"],
        "thingsboard_module":   ["alarm_collector"],
    }

    def __init__(self) -> None:
        self._parser = self._make_parser()

    def parse(self, argv: Optional[List[str]] = None) -> Tuple[argparse.Namespace, "OrderedDict[str, List[str]]"]:
        """
        Parse argv and return (args, selected).
        "selected" is an OrderedDict mapping module -> list of tools.
        """
        args = self._parser.parse_args(argv)

        # Case A: explicit global 'all' positional
        if args.global_all == "all":
            selected = self._select_all()
            return args, selected

        # Case B: no -m/-t provided -> default to all
        if not args.modules and not args.tools:
            selected = self._select_all()
            return args, selected

        # Case C: paired -m/-t mode
        self._validate_pair_mode(args)
        selected = self._build_selected_from_pairs(args.modules, args.tools)
        return args, selected

    def build_compose_profiles(self, selected: "OrderedDict[str, List[str]]") -> List[str]:
        """
        Build docker compose profile list like:
            module.tool
        (one entry per selected tool)
        """
        profiles: List[str] = []
        for module, tools in selected.items():
            for tool in tools:
                profiles.append(f"{module}.{tool}")
        return profiles


    def _make_parser(self) -> argparse.ArgumentParser:
        """
        Create and return an argparse.ArgumentParser configured with the script's CLI options.

        The parser supports:
        - an optional positional "all" to select everything,
        - repeated -m/--module and -t/--tools pairs,
        - an optional --debug passthrough.
        """
        p = argparse.ArgumentParser(
            prog="start_containers.py",
            description="Select docker-compose modules (files) and their service profiles (tools)."
        )
        # Positional 'all' (optional). Example: `python3 main.py all`
        p.add_argument("global_all", nargs="?", choices=["all"], default=None,
                       help="Enable all tools of all modules.")

        # Repeated pairs: -m <module> ... -t <tools> ...
        p.add_argument("-m", "--module", dest="modules", action="append",
                       metavar="MODULE",
                       help=f"Module name. Choices: {', '.join(self.MODULE_REGISTRY.keys())}. "
                            "Can be repeated.")
        p.add_argument("-t", "--tools", dest="tools", action="append",
                       metavar="TOOLS",
                       help="Tools for the preceding -m. Use 'all' or a comma/space-separated list "
                            "(e.g., 'telegraf, fluentd'). Can be repeated.")

        # Optional debug flag passthrough
        p.add_argument("--debug", default=None,
                       help="Debug flags to forward (e.g., 'cgrp,topic,fetch,protocol').")
        return p

    def _validate_pair_mode(self, args: argparse.Namespace) -> None:
        """
        Validate that modules and tools were provided in matching pairs and that
        module names exist in MODULE_REGISTRY. On error, call parser.error() to
        display a helpful message and exit.
        """
        if not args.modules or not args.tools:
            self._parser.error("You must provide matching -m/--module and -t/--tools pairs.")
        if len(args.modules) != len(args.tools):
            self._parser.error("The number of -m and -t occurrences must match (paired by position).")

        unknown = [m for m in args.modules if m not in self.MODULE_REGISTRY]
        if unknown:
            choices = ", ".join(self.MODULE_REGISTRY.keys())
            self._parser.error(f"Unknown module(s): {', '.join(unknown)}. Valid modules: {choices}.")

    def _select_all(self) -> "OrderedDict[str, List[str]]":
        """
        Return an OrderedDict mapping every registered module to a copy of its
        list of tools (i.e., select all tools for all modules).
        """
        selected: "OrderedDict[str, List[str]]" = OrderedDict()
        for m, tools in self.MODULE_REGISTRY.items():
            selected[m] = list(tools)
        return selected

    def _split_tools(self, s: str) -> List[str]:
        """
        Split a tools specification string into individual tokens.

        Behavior:
        - If the string is 'all' (case-insensitive), return ['all'].
        - Otherwise accept commas and/or whitespace as separators and return a
          list of non-empty tokens in input order.
        """
        s = s.strip()
        if s.lower() == "all":
            return ["all"]
        parts = [t.strip() for t in s.replace(",", " ").split()]
        return [t for t in parts if t]

    def _expand_tools(self, module: str, tool_tokens: List[str]) -> List[str]:
        """
        Expand and validate tool tokens for a given module.

        - If the single token is 'all', expand to all registered tools for that module.
        - Otherwise verify each token exists for the module; on unknown tokens call
          parser.error() with a descriptive message.
        - Preserve the input order and remove duplicates.
        """
        if len(tool_tokens) == 1 and tool_tokens[0].lower() == "all":
            return list(self.MODULE_REGISTRY[module])

        valid = set(self.MODULE_REGISTRY[module])
        unknown = [t for t in tool_tokens if t not in valid]
        if unknown:
            choices = ", ".join(self.MODULE_REGISTRY[module])
            self._parser.error(
                f"Unknown tool(s) for {module}: {', '.join(unknown)}. "
                f"Valid tools: {choices}."
            )
        seen = set()
        ordered: List[str] = []
        for t in tool_tokens:
            if t not in seen:
                seen.add(t)
                ordered.append(t)
        return ordered

    def _build_selected_from_pairs(self, modules: List[str], tools: List[str]) -> "OrderedDict[str, List[str]]":
        """
        Build and return an OrderedDict mapping each provided module to its
        expanded list of tools by zipping the modules and tools lists and
        applying token splitting and expansion.
        """
        selected: "OrderedDict[str, List[str]]" = OrderedDict()
        for m, t in zip(modules, tools):
            tokens = self._split_tools(t)
            expanded = self._expand_tools(m, tokens)
            selected[m] = expanded
        return selected


def detect_os():
    """
    Detect the host operating system and return a network mode string.
    Returns:
    - 'host' for Linux
    - 'bridge' for Windows or macOS (darwin)
    - 'error' for unknown systems
    """
    system = platform.system().lower()
    print(f"Detected OS: {system}")
    if system == "linux":
        return "host"
    elif system == "windows" or system == "darwin":
        return "bridge"
    else:
        return "error"

def generate_secure_password(length=20):
    alphabet = string.ascii_letters + string.digits + "!@%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for i in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#%^&*" for c in password)):
            return password

def get_existing_password(env_path: Path, password_tool: str) -> Optional[str]:
    if not env_path.exists():
        return None
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(password_tool):
                    return line.strip().split("=", 1)[1]
    except Exception:
        return None
    return None

def get_host_ip():
    """
    Get the current LAN IP address of the machine.
    This avoids using "127.0.0.1"  ensuring that 
    services talk to a real network interface.
    """
    try:
        # No data is actually sent.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # Fallback only if absolutely no network is available
        return "127.0.0.1"

def collect_env_vars(
    selected: "OrderedDict[str, List[str]]",
    tool_env_vars: Dict[str, List[str]],
    always_env_vars: Optional[List[str]] = None
) -> List[str]:
    """
    Devuelve una lista ordenada (sin duplicados) de env vars requeridas por
    las tools activas en `selected`, más las variables comunes que siempre
    deben existir.
    """
    seen = set()
    out: List[str] = []

    if always_env_vars:
        for env_key in always_env_vars:
            if env_key not in seen:
                seen.add(env_key)
                out.append(env_key)

    for modules, tools in selected.items():
        for tool in tools:
            for env_key in tool_env_vars.get(tool, []):
                if env_key not in seen:
                    seen.add(env_key)
                    out.append(env_key)

    return out


def write_dotenv(
    env_keys: Iterable[str],
    path: str | Path,
    defaults: Optional[Dict[str, str]] = None,
    header: str = ""
) -> Path:
    """
    Escribe un fichero .env con las claves en `env_keys`.
    Si `defaults` tiene valor para la clave, se usa; si no, se deja vacío.
    """
    env_path = Path(path)

    lines: List[str] = []
    if header:
        lines.append(header.rstrip("\n"))

    for key in env_keys:
        raw_value = "" if defaults is None else defaults.get(key, "")
        value = str(raw_value)

        if any(c.isspace() for c in value) or any(c in value for c in ['"', "'"]):
            value = value.replace('"', '\\"')
            lines.append(f'{key}="{value}"')
        else:
            lines.append(f"{key}={value}")

    if env_path.exists():
        try:
           os.remove(env_path)
           print(f"File {env_path} removed")
        except PermissionError:
            print(f"Insuficient permissions to remove file: {env_path}")
        except Exception as e:
            print(f"Error removing file {env_path}: {e}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path

def build_selected_compose_files(
    selected: "OrderedDict[str, List[str]]",
    base_dir: Path,
    module_compose_files: Dict[str, List[str]]
) -> List[str]:
    """
    Build an ordered, de-duplicated list of docker compose files for the selected modules.
    """

    seen = set()
    compose_files: List[str] = []

    for module in selected.keys():
        for rel_path in module_compose_files.get(module, []):
            abs_path = str((base_dir / rel_path).resolve())
            if abs_path not in seen:
                seen.add(abs_path)
                compose_files.append(abs_path)

    return compose_files


def main():
    try:
        LFD = Path(__file__).resolve().parent 
        mid_py = LFD / "machine_id" / "machine_id.py"
        mid = subprocess.check_output(
            [sys.executable, str(mid_py)],
            text=True
        ).strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing machine_id.py: {e}")
        return

    network_mode = detect_os()
    container_timezone="UTC"
    parser = cmd_parser()
    args, selected = parser.parse()
    # If a collection_module has been activated, then device_info is also included
    if "collection_module" in selected and "info" not in selected["collection_module"]:
        selected['collection_module'].append("info")

    compose_profiles_list = parser.build_compose_profiles(selected)
    compose_profiles = ",".join(compose_profiles_list)
    print("Selected:", selected)
    print("COMPOSE_PROFILES:", compose_profiles_list)
    if args.debug:
        print("Debug flags:", args.debug)

    PFD = Path(__file__).resolve().parent.parent 
    env_file_path = LFD / ".env"

    # Kafka topics
    tshark_base_topic = "tshark_traces"
    fluentd_syslog_base_topic = "syslog_logs"
    fluentd_systemd_base_topic = "systemd_logs"
    falco_base_topic = "falco_events"
    telegraf_base_topic = "telegraf_metrics"
    cic_kafka_base_topic_out = "cic_flow"
    snort_kafka_topic_out = "snort_alerts"
    # Telegraf
    enable_telegraf= "1"
    telegraf_to_prometheus_port= "9273"
    telegraf_general_interval= "30s"
    #Tshark
    tshark_size_limit_rotation=str(30 * 1024 * 1024) #30MiB
    # Fluentd
    enable_fluentd= "1"
    fluentd_to_prometheus_port= "24231"
    fluentd_internal_port= "24220"
    fluentd_file_size_limit=str(20 * 1024 * 1024) #20MiB
    # Falco
    enable_falco= "1"
    falco_skip_driver_loader=1
    falco_exporter_port="9376"
    # Info
    device_info_port="9999"
    # Kafka
    kafka_lan_hostname= "kafka_robust6g-node1.lan"
    kafka_port_external_lan= "9094"
    kafka_bootstrap= kafka_lan_hostname + ":" + kafka_port_external_lan
    kafka_port_internal= "29092"
    kafka_log_retention_ms= "86400000"
    kafka_log_retention_bytes= "1073741824"
    kafka_log_cleanup_policy= "delete"
    kafka_log_segment_bytes= "268435456"
    kafka_log_roll_ms= "3600000"
    # Filebeat
    filebeat_bulk_max_size= "4096"
    filebeat_compresion= "lz4"
    # Prometheus
    prometheus_port= "9090"
    discovery_agent_scan_port = device_info_port
    discovery_agent_scan_timeout= "0.2"
    discovery_agent_refresh_interval= "30"
    discovery_agent_port= "8100"
    # opensearch
    opensearch_password= get_existing_password(env_path=env_file_path,password_tool="OPENSEARCH_PASSWORD=")
    if not opensearch_password:
        opensearch_password = generate_secure_password()
    # In Host mode (Linux) -> Real LAN IP, NOT localhost.
    # In Bridge mode ->  internal docker OpenSearch service name.
    if network_mode == "host":
        opensearch_host = get_host_ip()
    else:
        opensearch_host = "opensearch-node"
        print(f"[+] Bridge Network detected. Using internal DNS: {opensearch_host}")
    opensearch_cluster_name= "robust6g-cluster"
    opensearch_node_name= "opensearch"
    opensearch_rest_api_port= "9200"
    opensearch_analyser_port= "9600"
    opensearch_dashboard_port= "5601"
    # mongodb
    mongo_initdb_root_username= "admin"   
    mongo_initdb_root_password= get_existing_password(env_path=env_file_path,password_tool="MONGO_INITDB_ROOT_PASSWORD=")
    if not mongo_initdb_root_password:
        mongo_initdb_root_password = generate_secure_password()
    mongo_port= "27017"
    mongo_uri= f"mongodb://{mongo_initdb_root_username}:{mongo_initdb_root_password}@mongodb:{mongo_port}/"
    # RedisDB
    redis_host= "redis_robust6g"
    redis_port= "6379"
    redis_user= "0"
    redis_password= "" 
    #User and password by default, but uncomment the following lines at the future to generate
    # a passwork and manage ACL Redis user/permissions
    '''
    redis_password= get_existing_password(env_path=env_file_path,password_tool="REDIS_PASSWORD=")
    if not redis_password:
        redis_password=generate_secure_password()
    '''
    redis_maxmemory_samples= "5"
    redis_io_threads= "4"
    redis_stream_node_max_bytes= "4096"
    redis_stream_node_max_entries= "100"
    redis_maxclients= "10000"
    ktrw_kafka_auto_offset_reset= "latest"
    ktrw_kafka_enable_auto_commit= "true"
    ktrw_kafka_group_id= "redis-streamer"
    ktrw_redis_max_stream_length= "1000"
    ktrw_redis_stream_ttl_seconds= "21600"
    ktrw_partition_assignment_strategy= "cooperative-sticky"
    ktrw_session_timeout_ms= "10000"
    ktrw_max_poll_interval_ms= "300000"
    ktrw_kafka_topic_refresh_interval= "30"
    ktrw_redis_cleanup_interval= "300"
    ktrw_redis_retention_hours= "2"
    ktrw_redis_emergency_retention_hours= "1"
    ktrw_redis_memory_threshold= "0.85"
    # Alert module
    snort_kafka_group_id= "alert-module"
    snort_kafka_topic_in= tshark_base_topic
    snort_alert_tap_iface= "tap0"
    snort_kafka_message_field= "_source"
    snort_consumer_kafka_auto_offset_reset= "earliest"
    snort_consumer_kafka_enable_auto_commit= "true"
    snort_consumer_kafka_partition_assignment_strategy= "cooperative-sticky"
    snort_consumer_kafka_enable_partition_eof= "true"
    snort_consumer_kafka_allow_auto_create_topics= "true"
    snort_consumer_fetch_min_bytes= "1048576"
    snort_consumer_fetch_wait_max_ms= "50"
    snort_consumer_queued_max_messages_kbytes= "262144"
    snort_consumer_max_poll_interval_ms= "900000"
    snort_consumer_session_timeout_ms= "10000"
    snort_producer_kafka_producer_linger_ms= "5"
    snort_producer_batch_num_messages= "10000"
    snort_producer_kafka_producer_batch_size= "32768"
    snort_producer_kafka_producer_compression= "zstd"
    #Flow Module
    flow_kafka_group="flow-module"
    flow_pcap_rotate_size_mb=str(100 * 1024) # 100 KiB
    flow_cic_rotate_size_mb=str(50 * 1024) # 50 KiB
    flow_rotate_time_sec="0.5" # Half a second
    flow_packet_queue_max="100000"
    flow_writer_flush_every="100" # Seconds
    flow_watchdog_stall_secs="120" # Inactivity Seconds

    flow_kafka_consumer_auto_offset_reset="earliest" # earliest/latest/none
    flow_kafka_consumer_enable_auto_commit="true"
    flow_kafka_consumer_partition_assignment_strategy="cooperative-sticky"
    flow_kafka_consumer_enable_partition_eof="true"
    flow_kafka_consumer_allow_auto_create_topics="true"
    flow_kafka_producer_linger_ms="5"
    flow_kafka_producer_batch_size=str(32* 1024) # 32 KiB
    flow_kafka_producer_compression="zstd" # zstd, lz4, gzip, snappy, none


    #NRTDR API
    nrtdr_api_port= "8001"
    if network_mode == "host":
        nrtdr_api_host= get_host_ip()
    else:
        nrtdr_api_host="nrtdr_api"
    nrtdr_ws_poll_interval= "0.5"
    nrtdr_ws_batch_size= "10"

    # Thingsboard alarm collector
    tb_username="tenant@thingsboard.org"
    tb_password="tenant"
    tb_use_https="false"

    # Variables que siempre deben ir al .env aunque no dependan de una tool concreta
    ALWAYS_ENV_VARS: List[str] = [
        "MACHINE_ID",
        "NETWORK_MODE",
        "PFD",
        "COMPOSE_PROFILES",
        "TZ",
        "KAFKA_BOOTSTRAP"
    ]

    # Herramienta -> nombres de variables que necesita
    TOOL_ENV_VARS: Dict[str, List[str]] = {
        # Data collection module
        "telegraf": [
            "ENABLE_TELEGRAF",
            "TELEGRAF_TO_PROMETHEUS_PORT",
            "TELEGRAF_BASE_TOPIC",
            "TELEGRAF_GENERAL_INTERVAL",
        ],
        "tshark": [
            "TSHARK_BASE_TOPIC",
            "TSHARK_SIZE_LIMIT_ROTATION",
        ],
        "fluentd": [
            "ENABLE_FLUENTD",
            "FLUENTD_TO_PROMETHEUS_PORT",
            "FLUENTD_INTERNAL_PORT",
            "FLUENTD_FILE_SIZE_LIMIT",
            "FLUENTD_SYSLOG_BASE_TOPIC",
            "FLUENTD_SYSTEMD_BASE_TOPIC",
        ],
        "falco": [
            "ENABLE_FALCO",
            "FALCO_BASE_TOPIC",
            "FALCO_SKIP_DRIVER_LOADER",
            "FALCO_EXPORTER_PORT"
        ],
        "info": [
            "DEVICE_INFO_PORT"
        ],

        # Communication bus
        "kafka": [
            "KAFKA_BOOTSTRAP",
            "KAFKA_LAN_HOSTNAME",
            "KAFKA_PORT_EXTERNAL_LAN",
            "KAFKA_PORT_INTERNAL",
            "KAFKA_LOG_RETENTION_MS",
            "KAFKA_LOG_RETENTION_BYTES",
            "KAFKA_LOG_CLEANUP_POLICY",
            "KAFKA_LOG_SEGMENT_BYTES",
            "KAFKA_LOG_ROLL_MS",
        ],
        "filebeat": [
            "FILEBEAT_BULK_MAX_SIZE",
            "FILEBEAT_COMPRESION",
        ],

        # Data Aggregation and Normalisation Module
        "prometheus": [
            "PROMETHEUS_PORT",
            "DISCOVERY_AGENT_SCAN_PORT",
            "DISCOVERY_AGENT_SCAN_TIMEOUT",
            "DISCOVERY_AGENT_REFRESH_INTERVAL",
            "DISCOVERY_AGENT_PORT",
        ],

        "opensearch": [
            "OPENSEARCH_PASSWORD",
            "OPENSEARCH_HOST",
            "OPENSEARCH_CLUSTER_NAME",
            "OPENSEARCH_NODE_NAME",
            "OPENSEARCH_REST_API_PORT",
            "OPENSEARCH_ANALYSER_PORT",
            "OPENSEARCH_DASHBOARD_PORT",
        ],

        # Data base module
        "mongodb": [
            "MONGO_INITDB_ROOT_USERNAME",
            "MONGO_INITDB_ROOT_PASSWORD",
            "MONGO_PORT",
            "MONGO_URI",
        ],
        "redis": [
            "REDIS_HOST",
            "REDIS_PORT",
            "REDIS_USER",
            "REDIS_PASSWORD",
            "REDIS_MAXMEMORY_SAMPLES",
            "REDIS_IO_THREADS",
            "REDIS_STREAM_NODE_MAX_BYTES",
            "REDIS_STREAM_NODE_MAX_ENTRIES",
            "REDIS_MAXCLIENTS",
            "KTRW_KAFKA_AUTO_OFFSET_RESET",
            "KTRW_KAFKA_ENABLE_AUTO_COMMIT",
            "KTRW_KAFKA_GROUP_ID",
            "KTRW_REDIS_MAX_STREAM_LENGTH",
            "KTRW_REDIS_STREAM_TTL_SECONDS",
            "KTRW_PARTITION_ASSIGNMENT_STRATEGY",
            "KTRW_SESSION_TIMEOUT_MS",
            "KTRW_MAX_POLL_INTERVAL_MS",
            "KTRW_KAFKA_TOPIC_REFRESH_INTERVAL",
            "KTRW_REDIS_CLEANUP_INTERVAL",
            "KTRW_REDIS_RETENTION_HOURS",
            "KTRW_REDIS_EMERGENCY_RETENTION_HOURS",
            "KTRW_REDIS_MEMORY_THRESHOLD",
        ],

        # Flow module
        "flow_module": [
            "CIC_KAFKA_BASE_TOPIC_OUT",
            "FLOW_KAFKA_GROUP",
            "FLOW_PCAP_ROTATE_SIZE_MB",
            "FLOW_CIC_ROTATE_SIZE_MB",
            "FLOW_ROTATE_TIME_SEC",
            "FLOW_PACKET_QUEUE_MAX",
            "FLOW_WRITER_FLUSH_EVERY",
            "FLOW_WATCHDOG_STALL_SECS",

            "FLOW_KAFKA_CONSUMER_AUTO_OFFSET_RESET",
            "FLOW_KAFKA_CONSUMER_ENABLE_AUTO_COMMIT",
            "FLOW_KAFKA_CONSUMER_PARTITION_ASSIGNMENT_STRATEGY",
            "FLOW_KAFKA_CONSUMER_ENABLE_PARTITION_EOF",
            "FLOW_KAFKA_CONSUMER_ALLOW_AUTO_CREATE_TOPICS",
            "FLOW_KAFKA_PRODUCER_LINGER_MS",
            "FLOW_KAFKA_PRODUCER_BATCH_SIZE",
            "FLOW_KAFKA_PRODUCER_COMPRESSION",

        ],

        # Alert and Notification Module
        "alert_module": [
            "SNORT_KAFKA_GROUP_ID",
            "SNORT_KAFKA_TOPIC_IN",
            "SNORT_KAFKA_TOPIC_OUT",
            "SNORT_ALERT_TAP_IFACE",
            "SNORT_KAFKA_MESSAGE_FIELD",
            "SNORT_CONSUMER_KAFKA_AUTO_OFFSET_RESET",
            "SNORT_CONSUMER_KAFKA_ENABLE_AUTO_COMMIT",
            "SNORT_CONSUMER_KAFKA_PARTITION_ASSIGNMENT_STRATEGY",
            "SNORT_CONSUMER_KAFKA_ENABLE_PARTITION_EOF",
            "SNORT_CONSUMER_KAFKA_ALLOW_AUTO_CREATE_TOPICS",
            "SNORT_CONSUMER_FETCH_MIN_BYTES",
            "SNORT_CONSUMER_FETCH_WAIT_MAX_MS",
            "SNORT_CONSUMER_QUEUED_MAX_MESSAGES_KBYTES",
            "SNORT_CONSUMER_MAX_POLL_INTERVAL_MS",
            "SNORT_CONSUMER_SESSION_TIMEOUT_MS",
            "SNORT_PRODUCER_KAFKA_PRODUCER_LINGER_MS",
            "SNORT_PRODUCER_BATCH_NUM_MESSAGES",
            "SNORT_PRODUCER_KAFKA_PRODUCER_BATCH_SIZE",
            "SNORT_PRODUCER_KAFKA_PRODUCER_COMPRESSION",
        ],

        # Near Real-time Data Retrieval API
        "nrtdr_api": [
            "NRTDR_API_PORT",
            "NRTDR_API_HOST",
            "NRTDR_WS_POLL_INTERVAL",
            "NRTDR_WS_BATCH_SIZE",
        ],

        # Thingsboard
        "alarm_collector": [
            "TB_USERNAME",
            "TB_PASSWORD",
            "TB_USE_HTTPS",
        ],
    }

    # Valores por defecto del .env
    DEFAULT_ENV: Dict[str, str] = {
        # Siempre
        "MACHINE_ID": mid,
        "NETWORK_MODE": network_mode,
        "PFD": str(PFD),
        "COMPOSE_PROFILES": compose_profiles,
        "TZ": container_timezone,

        # Kafka topics
        "TELEGRAF_BASE_TOPIC": telegraf_base_topic,
        "TSHARK_BASE_TOPIC": tshark_base_topic,
        "FLUENTD_SYSLOG_BASE_TOPIC": fluentd_syslog_base_topic,
        "FLUENTD_SYSTEMD_BASE_TOPIC": fluentd_systemd_base_topic,
        "FALCO_BASE_TOPIC": falco_base_topic,
        "CIC_KAFKA_BASE_TOPIC_OUT": cic_kafka_base_topic_out,
        "SNORT_KAFKA_TOPIC_OUT": snort_kafka_topic_out,

        # Telegraf
        "ENABLE_TELEGRAF": enable_telegraf,
        "TELEGRAF_TO_PROMETHEUS_PORT": telegraf_to_prometheus_port,
        "TELEGRAF_GENERAL_INTERVAL": telegraf_general_interval,
        
        #Tshark
        "TSHARK_SIZE_LIMIT_ROTATION": tshark_size_limit_rotation,

        # Fluentd
        "ENABLE_FLUENTD": enable_fluentd,
        "FLUENTD_TO_PROMETHEUS_PORT": fluentd_to_prometheus_port,
        "FLUENTD_INTERNAL_PORT": fluentd_internal_port,
        "FLUENTD_FILE_SIZE_LIMIT": fluentd_file_size_limit,

        # Falco
        "ENABLE_FALCO": enable_falco,
        "FALCO_SKIP_DRIVER_LOADER": falco_skip_driver_loader,
        "FALCO_EXPORTER_PORT": falco_exporter_port,
        #Info
        "DEVICE_INFO_PORT":device_info_port,

        # Kafka
        "KAFKA_BOOTSTRAP": kafka_bootstrap,
        "KAFKA_LAN_HOSTNAME": kafka_lan_hostname,
        "KAFKA_PORT_EXTERNAL_LAN": kafka_port_external_lan,
        "KAFKA_PORT_INTERNAL": kafka_port_internal,
        "KAFKA_LOG_RETENTION_MS": kafka_log_retention_ms,
        "KAFKA_LOG_RETENTION_BYTES": kafka_log_retention_bytes,
        "KAFKA_LOG_CLEANUP_POLICY": kafka_log_cleanup_policy,
        "KAFKA_LOG_SEGMENT_BYTES": kafka_log_segment_bytes,
        "KAFKA_LOG_ROLL_MS": kafka_log_roll_ms,

        # Filebeat
        "FILEBEAT_BULK_MAX_SIZE": filebeat_bulk_max_size,
        "FILEBEAT_COMPRESION": filebeat_compresion,

        # Prometheus
        "PROMETHEUS_PORT": prometheus_port,
        "DISCOVERY_AGENT_SCAN_PORT": discovery_agent_scan_port,
        "DISCOVERY_AGENT_SCAN_TIMEOUT": discovery_agent_scan_timeout,
        "DISCOVERY_AGENT_REFRESH_INTERVAL": discovery_agent_refresh_interval,
        "DISCOVERY_AGENT_PORT": discovery_agent_port,

        # OpenSearch
        "OPENSEARCH_PASSWORD": opensearch_password,
        "OPENSEARCH_HOST": opensearch_host,
        "OPENSEARCH_CLUSTER_NAME": opensearch_cluster_name,
        "OPENSEARCH_NODE_NAME": opensearch_node_name,
        "OPENSEARCH_REST_API_PORT": opensearch_rest_api_port,
        "OPENSEARCH_ANALYSER_PORT": opensearch_analyser_port,
        "OPENSEARCH_DASHBOARD_PORT": opensearch_dashboard_port,

        # MongoDB
        "MONGO_INITDB_ROOT_USERNAME": mongo_initdb_root_username,
        "MONGO_INITDB_ROOT_PASSWORD": mongo_initdb_root_password,
        "MONGO_PORT": mongo_port,
        "MONGO_URI": mongo_uri,

        # Redis
        "REDIS_HOST": redis_host,
        "REDIS_PORT": redis_port,
        "REDIS_USER": redis_user,
        "REDIS_PASSWORD": redis_password,
        "REDIS_MAXMEMORY_SAMPLES": redis_maxmemory_samples,
        "REDIS_IO_THREADS": redis_io_threads,
        "REDIS_STREAM_NODE_MAX_BYTES": redis_stream_node_max_bytes,
        "REDIS_STREAM_NODE_MAX_ENTRIES": redis_stream_node_max_entries,
        "REDIS_MAXCLIENTS": redis_maxclients,
        "KTRW_KAFKA_AUTO_OFFSET_RESET": ktrw_kafka_auto_offset_reset,
        "KTRW_KAFKA_ENABLE_AUTO_COMMIT": ktrw_kafka_enable_auto_commit,
        "KTRW_KAFKA_GROUP_ID": ktrw_kafka_group_id,
        "KTRW_REDIS_MAX_STREAM_LENGTH": ktrw_redis_max_stream_length,
        "KTRW_REDIS_STREAM_TTL_SECONDS": ktrw_redis_stream_ttl_seconds,
        "KTRW_PARTITION_ASSIGNMENT_STRATEGY": ktrw_partition_assignment_strategy,
        "KTRW_SESSION_TIMEOUT_MS": ktrw_session_timeout_ms,
        "KTRW_MAX_POLL_INTERVAL_MS": ktrw_max_poll_interval_ms,
        "KTRW_KAFKA_TOPIC_REFRESH_INTERVAL": ktrw_kafka_topic_refresh_interval,
        "KTRW_REDIS_CLEANUP_INTERVAL": ktrw_redis_cleanup_interval,
        "KTRW_REDIS_RETENTION_HOURS": ktrw_redis_retention_hours,
        "KTRW_REDIS_EMERGENCY_RETENTION_HOURS": ktrw_redis_emergency_retention_hours,
        "KTRW_REDIS_MEMORY_THRESHOLD": ktrw_redis_memory_threshold,

        # Alert module
        "SNORT_KAFKA_GROUP_ID": snort_kafka_group_id,
        "SNORT_KAFKA_TOPIC_IN": snort_kafka_topic_in,
        "SNORT_ALERT_TAP_IFACE": snort_alert_tap_iface,
        "SNORT_KAFKA_MESSAGE_FIELD": snort_kafka_message_field,
        "SNORT_CONSUMER_KAFKA_AUTO_OFFSET_RESET": snort_consumer_kafka_auto_offset_reset,
        "SNORT_CONSUMER_KAFKA_ENABLE_AUTO_COMMIT": snort_consumer_kafka_enable_auto_commit,
        "SNORT_CONSUMER_KAFKA_PARTITION_ASSIGNMENT_STRATEGY": snort_consumer_kafka_partition_assignment_strategy,
        "SNORT_CONSUMER_KAFKA_ENABLE_PARTITION_EOF": snort_consumer_kafka_enable_partition_eof,
        "SNORT_CONSUMER_KAFKA_ALLOW_AUTO_CREATE_TOPICS": snort_consumer_kafka_allow_auto_create_topics,
        "SNORT_CONSUMER_FETCH_MIN_BYTES": snort_consumer_fetch_min_bytes,
        "SNORT_CONSUMER_FETCH_WAIT_MAX_MS": snort_consumer_fetch_wait_max_ms,
        "SNORT_CONSUMER_QUEUED_MAX_MESSAGES_KBYTES": snort_consumer_queued_max_messages_kbytes,
        "SNORT_CONSUMER_MAX_POLL_INTERVAL_MS": snort_consumer_max_poll_interval_ms,
        "SNORT_CONSUMER_SESSION_TIMEOUT_MS": snort_consumer_session_timeout_ms,
        "SNORT_PRODUCER_KAFKA_PRODUCER_LINGER_MS": snort_producer_kafka_producer_linger_ms,
        "SNORT_PRODUCER_BATCH_NUM_MESSAGES": snort_producer_batch_num_messages,
        "SNORT_PRODUCER_KAFKA_PRODUCER_BATCH_SIZE": snort_producer_kafka_producer_batch_size,
        "SNORT_PRODUCER_KAFKA_PRODUCER_COMPRESSION": snort_producer_kafka_producer_compression,
        
        #Flow Module
        "FLOW_KAFKA_GROUP": flow_kafka_group,
        "FLOW_PCAP_ROTATE_SIZE_MB" : flow_pcap_rotate_size_mb,
        "FLOW_CIC_ROTATE_SIZE_MB" : flow_cic_rotate_size_mb,
        "FLOW_ROTATE_TIME_SEC" : flow_rotate_time_sec,
        "FLOW_PACKET_QUEUE_MAX" : flow_packet_queue_max,
        "FLOW_WRITER_FLUSH_EVERY" : flow_writer_flush_every,
        "FLOW_WATCHDOG_STALL_SECS" : flow_watchdog_stall_secs,
        "FLOW_KAFKA_CONSUMER_AUTO_OFFSET_RESET" : flow_kafka_consumer_auto_offset_reset,
        "FLOW_KAFKA_CONSUMER_ENABLE_AUTO_COMMIT" : flow_kafka_consumer_enable_auto_commit,
        "FLOW_KAFKA_CONSUMER_PARTITION_ASSIGNMENT_STRATEGY" : flow_kafka_consumer_partition_assignment_strategy,
        "FLOW_KAFKA_CONSUMER_ENABLE_PARTITION_EOF" : flow_kafka_consumer_enable_partition_eof,
        "FLOW_KAFKA_CONSUMER_ALLOW_AUTO_CREATE_TOPICS" : flow_kafka_consumer_allow_auto_create_topics,
        "FLOW_KAFKA_PRODUCER_LINGER_MS" : flow_kafka_producer_linger_ms,
        "FLOW_KAFKA_PRODUCER_BATCH_SIZE" : flow_kafka_producer_batch_size,
        "FLOW_KAFKA_PRODUCER_COMPRESSION" : flow_kafka_producer_compression,

        # NRTDR API
        "NRTDR_API_PORT": nrtdr_api_port,
        "NRTDR_API_HOST": nrtdr_api_host,
        "NRTDR_WS_POLL_INTERVAL": nrtdr_ws_poll_interval,
        "NRTDR_WS_BATCH_SIZE": nrtdr_ws_batch_size,

        # Thingsboard alarm collector
        "TB_USERNAME" : tb_username,
        "TB_PASSWORD" : tb_password,
        "TB_USE_HTTPS" : tb_use_https,

    }

    env_keys = collect_env_vars(selected=selected, tool_env_vars=TOOL_ENV_VARS, always_env_vars=ALWAYS_ENV_VARS)

    written_path = write_dotenv(env_keys=env_keys, path=env_file_path, defaults=DEFAULT_ENV, header="")



    selected_compose_files = build_selected_compose_files(
        selected=selected,
        base_dir=PFD,
        module_compose_files=MODULE_COMPOSE_FILES
    )

    if not selected_compose_files:
        print("No docker compose files resolved for the selected modules.")
        return

    print("Compose files:", selected_compose_files)

    compose_cmd = ["docker", "compose"]

    for compose_file in selected_compose_files:
        compose_cmd.extend(["-f", compose_file])

    compose_cmd.extend([
        "--project-directory", str(PFD),
        "--env-file", str(written_path),
        "up", "--build", "-d"
    ])

    try:
        subprocess.run(compose_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing docker-compose: {e}")
        return

if __name__ == "__main__":
    main()