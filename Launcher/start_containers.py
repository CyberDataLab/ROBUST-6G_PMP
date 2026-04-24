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
from urllib.parse import quote_plus

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
    """

    MODULE_REGISTRY: Dict[str, List[str]] = {
        "alert_module":         ["alert_module"],
        "communication_module": ["kafka", "filebeat"],
        "collection_module":    ["fluentd", "telegraf", "tshark", "falco", "info"],
        "flow_module":          ["flow_module"],
        "db_module":            ["mongodb", "mongodb_cm", "redis"],
        "aggregation_module":   ["prometheus", "opensearch"],
        "thingsboard_module":   ["alarm_collector"],
    }

    def __init__(self) -> None:
        self._parser = self._make_parser()

    def parse(self, argv: Optional[List[str]] = None) -> Tuple[argparse.Namespace, "OrderedDict[str, List[str]]"]:
        """
        Parse argv and return (args, selected) where selected maps module -> list of tools.
        """
        args = self._parser.parse_args(argv)

        if args.global_all == "all":
            selected = self._select_all()
            return args, selected

        if not args.modules and not args.tools:
            selected = self._select_all()
            return args, selected

        self._validate_pair_mode(args)
        selected = self._build_selected_from_pairs(args.modules, args.tools)
        return args, selected

    def build_compose_profiles(self, selected: "OrderedDict[str, List[str]]") -> List[str]:
        """
        Build docker compose profile list as module.tool strings.
        """
        profiles: List[str] = []
        for module, tools in selected.items():
            for tool in tools:
                profiles.append(f"{module}.{tool}")
        return profiles

    def _make_parser(self) -> argparse.ArgumentParser:
        """
        Create and return the argument parser with all CLI options.
        """
        p = argparse.ArgumentParser(
            prog="start_containers.py",
            description="Select docker-compose modules (files) and their service profiles (tools)."
        )
        p.add_argument("global_all", nargs="?", choices=["all"], default=None,
                       help="Enable all tools of all modules.")
        p.add_argument("-m", "--module", dest="modules", action="append",
                       metavar="MODULE",
                       help=f"Module name. Choices: {', '.join(self.MODULE_REGISTRY.keys())}. "
                            "Can be repeated.")
        p.add_argument("-t", "--tools", dest="tools", action="append",
                       metavar="TOOLS",
                       help="Tools for the preceding -m. Use 'all' or a comma/space-separated list. "
                            "Can be repeated.")
        p.add_argument("--debug", default=None,
                       help="Debug flags to forward.")
        p.add_argument("--env-overrides", default=None,
                       help="Path to a JSON file with env var overrides (used by the Configuration Manager API).")
        return p

    def _validate_pair_mode(self, args: argparse.Namespace) -> None:
        """
        Validate that modules and tools were provided in matching pairs.
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
        Return an OrderedDict mapping every module to all its tools.
        """
        selected: "OrderedDict[str, List[str]]" = OrderedDict()
        for m, tools in self.MODULE_REGISTRY.items():
            selected[m] = list(tools)
        return selected

    def _split_tools(self, s: str) -> List[str]:
        """
        Split a tools specification string into individual tokens, accepting comma or space separators.
        """
        s = s.strip()
        if s.lower() == "all":
            return ["all"]
        parts = [t.strip() for t in s.replace(",", " ").split()]
        return [t for t in parts if t]

    def _expand_tools(self, module: str, tool_tokens: List[str]) -> List[str]:
        """
        Expand and validate tool tokens for a given module, returning deduplicated ordered list.
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
        Build an OrderedDict mapping each module to its expanded list of tools from CLI pairs.
        """
        selected: "OrderedDict[str, List[str]]" = OrderedDict()
        for m, t in zip(modules, tools):
            tokens = self._split_tools(t)
            expanded = self._expand_tools(m, tokens)
            selected[m] = expanded
        return selected


def detect_os() -> str:
    """
    Detect the host operating system and return a network mode string (host/bridge/error).
    """
    system = platform.system().lower()
    print(f"Detected OS: {system}")
    if system == "linux":
        return "host"
    elif system == "windows" or system == "darwin":
        return "bridge"
    else:
        return "error"


def generate_secure_password(length: int = 20) -> str:
    """
    Generate a cryptographically secure random password with mixed character types.
    """
    alphabet = string.ascii_letters + string.digits + "!@%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for i in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#%^&*" for c in password)):
            return password


def get_existing_password(env_path: Path, password_tool: str) -> Optional[str]:
    """
    Read an existing password from the .env file to avoid regenerating it on each run.
    """
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


def get_host_ip() -> str:
    """
    Get the current LAN IP address of the machine by opening a UDP socket without sending data.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def collect_env_vars(
    selected: "OrderedDict[str, List[str]]",
    tool_env_vars: Dict[str, List[str]],
    always_env_vars: Optional[List[str]] = None
) -> List[str]:
    """
    Return an ordered deduplicated list of env var names required by the active tools plus always-required vars.
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
    path: "str | Path",
    defaults: Optional[Dict[str, str]] = None,
    header: str = ""
) -> Path:
    """
    Write a .env file with the provided keys, using defaults dict for values when available.
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
            print(f"Insufficient permissions to remove file: {env_path}")
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
    Build an ordered deduplicated list of absolute docker compose file paths for the selected modules.
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


def build_default_env(
    mid: str,
    network_mode: str,
    PFD: Path,
    compose_profiles: str,
    env_file_path: Path
) -> Dict[str, str]:
    """
    Build and return the complete DEFAULT_ENV dictionary with all variable defaults.
    This function is imported by configuration_manager_logic.py to avoid duplicating defaults.
    env_file_path is used to read previously generated passwords so they are not regenerated.
    """
    container_timezone = "UTC"

    # Kafka topics
    tshark_base_topic           = "tshark_traces"
    fluentd_syslog_base_topic   = "syslog_logs"
    fluentd_systemd_base_topic  = "systemd_logs"
    falco_base_topic            = "falco_events"
    telegraf_base_topic         = "telegraf_metrics"
    cic_kafka_base_topic_out    = "cic_flow"
    snort_kafka_topic_out       = "snort_alerts"

    # Telegraf
    enable_telegraf             = "1"
    telegraf_to_prometheus_port = "9273"
    telegraf_general_interval   = "30s"

    # Tshark (30 MiB pre-calculated)
    tshark_size_limit_rotation  = "31457280"

    # Fluentd (20 MiB pre-calculated)
    enable_fluentd              = "1"
    fluentd_to_prometheus_port  = "24231"
    fluentd_internal_port       = "24220"
    fluentd_file_size_limit     = "20971520"

    # Falco
    enable_falco                = "1"
    falco_skip_driver_loader    = "1"
    falco_exporter_port         = "9376"

    # Info
    device_info_port            = "9999"

    # Kafka
    kafka_lan_hostname          = "kafka_robust6g-node1.lan"
    kafka_port_external_lan     = "9094"
    kafka_bootstrap             = kafka_lan_hostname + ":" + kafka_port_external_lan
    kafka_port_internal         = "29092"
    kafka_log_retention_ms      = "86400000"
    kafka_log_retention_bytes   = "1073741824"
    kafka_log_cleanup_policy    = "delete"
    kafka_log_segment_bytes     = "268435456"
    kafka_log_roll_ms           = "3600000"

    # Filebeat
    filebeat_bulk_max_size      = "4096"
    filebeat_compresion         = "lz4"

    # Prometheus
    prometheus_port                    = "9090"
    discovery_agent_scan_port          = device_info_port
    discovery_agent_scan_timeout       = "0.2"
    discovery_agent_refresh_interval   = "30"
    discovery_agent_port               = "8100"

    # OpenSearch
    opensearch_password = get_existing_password(env_path=env_file_path, password_tool="OPENSEARCH_PASSWORD=")
    if not opensearch_password:
        opensearch_password = generate_secure_password()
    if network_mode == "host":
        opensearch_host = get_host_ip()
    else:
        opensearch_host = "opensearch-node"
    opensearch_cluster_name     = "robust6g-cluster"
    opensearch_node_name        = "opensearch"
    opensearch_rest_api_port    = "9200"
    opensearch_analyser_port    = "9600"
    opensearch_dashboard_port   = "5601"

    # MongoDB main instance
    mongo_initdb_root_username = "admin"
    mongo_initdb_root_password = get_existing_password(env_path=env_file_path, password_tool="MONGO_INITDB_ROOT_PASSWORD=")
    if not mongo_initdb_root_password:
        mongo_initdb_root_password = generate_secure_password()
    mongo_port = "27017"
    mongo_uri = (
        f"mongodb://{mongo_initdb_root_username}:"
        f"{quote_plus(mongo_initdb_root_password)}"
        f"@mongodb:{mongo_port}/?authSource=admin"
    )

    # MongoDB Configuration Manager instance
    mongo_cm_initdb_root_username = "admin"
    mongo_cm_initdb_root_password = get_existing_password(env_path=env_file_path, password_tool="MONGO_CM_INITDB_ROOT_PASSWORD=")
    if not mongo_cm_initdb_root_password:
        mongo_cm_initdb_root_password = generate_secure_password()
    mongo_cm_port = "27018"
    mongo_cm_uri_docker = (
        f"mongodb://{mongo_cm_initdb_root_username}:"
        f"{quote_plus(mongo_cm_initdb_root_password)}"
        f"@mongodb_cm:27017/?authSource=admin"
    )
    mongo_cm_uri_host = (
        f"mongodb://{mongo_cm_initdb_root_username}:"
        f"{quote_plus(mongo_cm_initdb_root_password)}"
        f"@localhost:{mongo_cm_port}/?authSource=admin"
    )

    # Redis
    redis_host                           = "redis_robust6g"
    redis_port                           = "6379"
    redis_user                           = "0"
    redis_password                       = ""
    redis_maxmemory_samples              = "5"
    redis_io_threads                     = "4"
    redis_stream_node_max_bytes          = "4096"
    redis_stream_node_max_entries        = "100"
    redis_maxclients                     = "10000"
    ktrw_kafka_auto_offset_reset         = "latest"
    ktrw_kafka_enable_auto_commit        = "true"
    ktrw_kafka_group_id                  = "redis-streamer"
    ktrw_redis_max_stream_length         = "1000"
    ktrw_redis_stream_ttl_seconds        = "21600"
    ktrw_partition_assignment_strategy   = "cooperative-sticky"
    ktrw_session_timeout_ms              = "10000"
    ktrw_max_poll_interval_ms            = "300000"
    ktrw_kafka_topic_refresh_interval    = "30"
    ktrw_redis_cleanup_interval          = "300"
    ktrw_redis_retention_hours           = "2"
    ktrw_redis_emergency_retention_hours = "1"
    ktrw_redis_memory_threshold          = "0.85"

    # Alert module
    snort_kafka_group_id                               = "alert-module"
    snort_kafka_topic_in                               = tshark_base_topic
    snort_alert_tap_iface                              = "tap0"
    snort_kafka_message_field                          = "_source"
    snort_consumer_kafka_auto_offset_reset             = "earliest"
    snort_consumer_kafka_enable_auto_commit            = "true"
    snort_consumer_kafka_partition_assignment_strategy = "cooperative-sticky"
    snort_consumer_kafka_enable_partition_eof          = "true"
    snort_consumer_kafka_allow_auto_create_topics      = "true"
    snort_consumer_fetch_min_bytes                     = "1048576"
    snort_consumer_fetch_wait_max_ms                   = "50"
    snort_consumer_queued_max_messages_kbytes          = "262144"
    snort_consumer_max_poll_interval_ms                = "900000"
    snort_consumer_session_timeout_ms                  = "10000"
    snort_producer_kafka_producer_linger_ms            = "5"
    snort_producer_batch_num_messages                  = "10000"
    snort_producer_kafka_producer_batch_size           = "32768"
    snort_producer_kafka_producer_compression          = "zstd"

    # Flow module (102400 = 100 KiB, 51200 = 50 KiB)
    flow_kafka_group                                   = "flow-module"
    flow_pcap_rotate_size_mb                           = "102400"
    flow_cic_rotate_size_mb                            = "51200"
    flow_rotate_time_sec                               = "0.5"
    flow_packet_queue_max                              = "100000"
    flow_writer_flush_every                            = "100"
    flow_watchdog_stall_secs                           = "120"
    flow_kafka_consumer_auto_offset_reset              = "earliest"
    flow_kafka_consumer_enable_auto_commit             = "true"
    flow_kafka_consumer_partition_assignment_strategy  = "cooperative-sticky"
    flow_kafka_consumer_enable_partition_eof           = "true"
    flow_kafka_consumer_allow_auto_create_topics       = "true"
    flow_kafka_producer_linger_ms                      = "5"
    flow_kafka_producer_batch_size                     = "32768"
    flow_kafka_producer_compression                    = "zstd"

    # NRTDR API
    nrtdr_api_port         = "8001"
    if network_mode == "host":
        nrtdr_api_host     = get_host_ip()
    else:
        nrtdr_api_host     = "nrtdr_api"
    nrtdr_ws_poll_interval = "0.5"
    nrtdr_ws_batch_size    = "10"

    # Thingsboard alarm collector
    tb_username  = "tenant@thingsboard.org"
    tb_password  = "tenant"
    tb_use_https = "false"

    DEFAULT_ENV: Dict[str, str] = {
        # Always present - generated internally, not overridable via API
        "MACHINE_ID":       mid,
        "NETWORK_MODE":     network_mode,
        "PFD":              str(PFD),
        "COMPOSE_PROFILES": compose_profiles,
        "TZ":               container_timezone,

        # Kafka topics
        "TELEGRAF_BASE_TOPIC":          telegraf_base_topic,
        "TSHARK_BASE_TOPIC":            tshark_base_topic,
        "FLUENTD_SYSLOG_BASE_TOPIC":    fluentd_syslog_base_topic,
        "FLUENTD_SYSTEMD_BASE_TOPIC":   fluentd_systemd_base_topic,
        "FALCO_BASE_TOPIC":             falco_base_topic,
        "CIC_KAFKA_BASE_TOPIC_OUT":     cic_kafka_base_topic_out,
        "SNORT_KAFKA_TOPIC_OUT":        snort_kafka_topic_out,

        # Telegraf
        "ENABLE_TELEGRAF":              enable_telegraf,
        "TELEGRAF_TO_PROMETHEUS_PORT":  telegraf_to_prometheus_port,
        "TELEGRAF_GENERAL_INTERVAL":    telegraf_general_interval,

        # Tshark
        "TSHARK_SIZE_LIMIT_ROTATION":   tshark_size_limit_rotation,

        # Fluentd
        "ENABLE_FLUENTD":               enable_fluentd,
        "FLUENTD_TO_PROMETHEUS_PORT":   fluentd_to_prometheus_port,
        "FLUENTD_INTERNAL_PORT":        fluentd_internal_port,
        "FLUENTD_FILE_SIZE_LIMIT":      fluentd_file_size_limit,

        # Falco
        "ENABLE_FALCO":                 enable_falco,
        "FALCO_SKIP_DRIVER_LOADER":     falco_skip_driver_loader,
        "FALCO_EXPORTER_PORT":          falco_exporter_port,

        # Info
        "DEVICE_INFO_PORT":             device_info_port,

        # Kafka
        "KAFKA_BOOTSTRAP":              kafka_bootstrap,
        "KAFKA_LAN_HOSTNAME":           kafka_lan_hostname,
        "KAFKA_PORT_EXTERNAL_LAN":      kafka_port_external_lan,
        "KAFKA_PORT_INTERNAL":          kafka_port_internal,
        "KAFKA_LOG_RETENTION_MS":       kafka_log_retention_ms,
        "KAFKA_LOG_RETENTION_BYTES":    kafka_log_retention_bytes,
        "KAFKA_LOG_CLEANUP_POLICY":     kafka_log_cleanup_policy,
        "KAFKA_LOG_SEGMENT_BYTES":      kafka_log_segment_bytes,
        "KAFKA_LOG_ROLL_MS":            kafka_log_roll_ms,

        # Filebeat
        "FILEBEAT_BULK_MAX_SIZE":       filebeat_bulk_max_size,
        "FILEBEAT_COMPRESION":          filebeat_compresion,

        # Prometheus
        "PROMETHEUS_PORT":                    prometheus_port,
        "DISCOVERY_AGENT_SCAN_PORT":          discovery_agent_scan_port,
        "DISCOVERY_AGENT_SCAN_TIMEOUT":       discovery_agent_scan_timeout,
        "DISCOVERY_AGENT_REFRESH_INTERVAL":   discovery_agent_refresh_interval,
        "DISCOVERY_AGENT_PORT":               discovery_agent_port,

        # OpenSearch
        "OPENSEARCH_PASSWORD":          opensearch_password,
        "OPENSEARCH_HOST":              opensearch_host,
        "OPENSEARCH_CLUSTER_NAME":      opensearch_cluster_name,
        "OPENSEARCH_NODE_NAME":         opensearch_node_name,
        "OPENSEARCH_REST_API_PORT":     opensearch_rest_api_port,
        "OPENSEARCH_ANALYSER_PORT":     opensearch_analyser_port,
        "OPENSEARCH_DASHBOARD_PORT":    opensearch_dashboard_port,

        # MongoDB main instance
        "MONGO_INITDB_ROOT_USERNAME":   mongo_initdb_root_username,
        "MONGO_INITDB_ROOT_PASSWORD":   mongo_initdb_root_password,
        "MONGO_PORT":                   mongo_port,
        "MONGO_URI":                    mongo_uri,

        # MongoDB Configuration Manager instance
        "MONGO_CM_INITDB_ROOT_USERNAME": mongo_cm_initdb_root_username,
        "MONGO_CM_INITDB_ROOT_PASSWORD": mongo_cm_initdb_root_password,
        "MONGO_CM_PORT":                 mongo_cm_port,
        "MONGO_CM_URI":                  mongo_cm_uri_docker,
        "MONGO_CM_URI_DOCKER":           mongo_cm_uri_docker,
        "MONGO_CM_URI_HOST":             mongo_cm_uri_host,

        # Redis
        "REDIS_HOST":                           redis_host,
        "REDIS_PORT":                           redis_port,
        "REDIS_USER":                           redis_user,
        "REDIS_PASSWORD":                       redis_password,
        "REDIS_MAXMEMORY_SAMPLES":              redis_maxmemory_samples,
        "REDIS_IO_THREADS":                     redis_io_threads,
        "REDIS_STREAM_NODE_MAX_BYTES":          redis_stream_node_max_bytes,
        "REDIS_STREAM_NODE_MAX_ENTRIES":        redis_stream_node_max_entries,
        "REDIS_MAXCLIENTS":                     redis_maxclients,
        "KTRW_KAFKA_AUTO_OFFSET_RESET":         ktrw_kafka_auto_offset_reset,
        "KTRW_KAFKA_ENABLE_AUTO_COMMIT":        ktrw_kafka_enable_auto_commit,
        "KTRW_KAFKA_GROUP_ID":                  ktrw_kafka_group_id,
        "KTRW_REDIS_MAX_STREAM_LENGTH":         ktrw_redis_max_stream_length,
        "KTRW_REDIS_STREAM_TTL_SECONDS":        ktrw_redis_stream_ttl_seconds,
        "KTRW_PARTITION_ASSIGNMENT_STRATEGY":   ktrw_partition_assignment_strategy,
        "KTRW_SESSION_TIMEOUT_MS":              ktrw_session_timeout_ms,
        "KTRW_MAX_POLL_INTERVAL_MS":            ktrw_max_poll_interval_ms,
        "KTRW_KAFKA_TOPIC_REFRESH_INTERVAL":    ktrw_kafka_topic_refresh_interval,
        "KTRW_REDIS_CLEANUP_INTERVAL":          ktrw_redis_cleanup_interval,
        "KTRW_REDIS_RETENTION_HOURS":           ktrw_redis_retention_hours,
        "KTRW_REDIS_EMERGENCY_RETENTION_HOURS": ktrw_redis_emergency_retention_hours,
        "KTRW_REDIS_MEMORY_THRESHOLD":          ktrw_redis_memory_threshold,

        # Alert module
        "SNORT_KAFKA_GROUP_ID":                               snort_kafka_group_id,
        "SNORT_KAFKA_TOPIC_IN":                               snort_kafka_topic_in,
        "SNORT_ALERT_TAP_IFACE":                              snort_alert_tap_iface,
        "SNORT_KAFKA_MESSAGE_FIELD":                          snort_kafka_message_field,
        "SNORT_CONSUMER_KAFKA_AUTO_OFFSET_RESET":             snort_consumer_kafka_auto_offset_reset,
        "SNORT_CONSUMER_KAFKA_ENABLE_AUTO_COMMIT":            snort_consumer_kafka_enable_auto_commit,
        "SNORT_CONSUMER_KAFKA_PARTITION_ASSIGNMENT_STRATEGY": snort_consumer_kafka_partition_assignment_strategy,
        "SNORT_CONSUMER_KAFKA_ENABLE_PARTITION_EOF":          snort_consumer_kafka_enable_partition_eof,
        "SNORT_CONSUMER_KAFKA_ALLOW_AUTO_CREATE_TOPICS":      snort_consumer_kafka_allow_auto_create_topics,
        "SNORT_CONSUMER_FETCH_MIN_BYTES":                     snort_consumer_fetch_min_bytes,
        "SNORT_CONSUMER_FETCH_WAIT_MAX_MS":                   snort_consumer_fetch_wait_max_ms,
        "SNORT_CONSUMER_QUEUED_MAX_MESSAGES_KBYTES":          snort_consumer_queued_max_messages_kbytes,
        "SNORT_CONSUMER_MAX_POLL_INTERVAL_MS":                snort_consumer_max_poll_interval_ms,
        "SNORT_CONSUMER_SESSION_TIMEOUT_MS":                  snort_consumer_session_timeout_ms,
        "SNORT_PRODUCER_KAFKA_PRODUCER_LINGER_MS":            snort_producer_kafka_producer_linger_ms,
        "SNORT_PRODUCER_BATCH_NUM_MESSAGES":                  snort_producer_batch_num_messages,
        "SNORT_PRODUCER_KAFKA_PRODUCER_BATCH_SIZE":           snort_producer_kafka_producer_batch_size,
        "SNORT_PRODUCER_KAFKA_PRODUCER_COMPRESSION":          snort_producer_kafka_producer_compression,

        # Flow module
        "FLOW_KAFKA_GROUP":                                  flow_kafka_group,
        "FLOW_PCAP_ROTATE_SIZE_MB":                          flow_pcap_rotate_size_mb,
        "FLOW_CIC_ROTATE_SIZE_MB":                           flow_cic_rotate_size_mb,
        "FLOW_ROTATE_TIME_SEC":                              flow_rotate_time_sec,
        "FLOW_PACKET_QUEUE_MAX":                             flow_packet_queue_max,
        "FLOW_WRITER_FLUSH_EVERY":                           flow_writer_flush_every,
        "FLOW_WATCHDOG_STALL_SECS":                          flow_watchdog_stall_secs,
        "FLOW_KAFKA_CONSUMER_AUTO_OFFSET_RESET":             flow_kafka_consumer_auto_offset_reset,
        "FLOW_KAFKA_CONSUMER_ENABLE_AUTO_COMMIT":            flow_kafka_consumer_enable_auto_commit,
        "FLOW_KAFKA_CONSUMER_PARTITION_ASSIGNMENT_STRATEGY": flow_kafka_consumer_partition_assignment_strategy,
        "FLOW_KAFKA_CONSUMER_ENABLE_PARTITION_EOF":          flow_kafka_consumer_enable_partition_eof,
        "FLOW_KAFKA_CONSUMER_ALLOW_AUTO_CREATE_TOPICS":      flow_kafka_consumer_allow_auto_create_topics,
        "FLOW_KAFKA_PRODUCER_LINGER_MS":                     flow_kafka_producer_linger_ms,
        "FLOW_KAFKA_PRODUCER_BATCH_SIZE":                    flow_kafka_producer_batch_size,
        "FLOW_KAFKA_PRODUCER_COMPRESSION":                   flow_kafka_producer_compression,

        # NRTDR API
        "NRTDR_API_PORT":         nrtdr_api_port,
        "NRTDR_API_HOST":         nrtdr_api_host,
        "NRTDR_WS_POLL_INTERVAL": nrtdr_ws_poll_interval,
        "NRTDR_WS_BATCH_SIZE":    nrtdr_ws_batch_size,

        # Thingsboard alarm collector
        "TB_USERNAME":  tb_username,
        "TB_PASSWORD":  tb_password,
        "TB_USE_HTTPS": tb_use_https,
    }

    return DEFAULT_ENV


# Variables that always go into every .env regardless of selected tools.
# These are generated internally and cannot be overridden via the API.
ALWAYS_ENV_VARS: List[str] = [
    "MACHINE_ID",
    "NETWORK_MODE",
    "PFD",
    "COMPOSE_PROFILES",
    "TZ",
    "KAFKA_BOOTSTRAP",
    "KAFKA_LAN_HOSTNAME",   # needed by extra_hosts in many containers to resolve Kafka DNS
]

# Tool -> list of env var names it requires in the .env
TOOL_ENV_VARS: Dict[str, List[str]] = {
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
        "FALCO_EXPORTER_PORT",
    ],
    "info": [
        "DEVICE_INFO_PORT",
    ],
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
        # Logstash always deploys alongside opensearch and needs all producer topics
        "TELEGRAF_BASE_TOPIC",
        "TSHARK_BASE_TOPIC",
        "FLUENTD_SYSLOG_BASE_TOPIC",
        "FLUENTD_SYSTEMD_BASE_TOPIC",
        "FALCO_BASE_TOPIC",
    ],
    "mongodb": [
        "MONGO_INITDB_ROOT_USERNAME",
        "MONGO_INITDB_ROOT_PASSWORD",
        "MONGO_PORT",
        "MONGO_URI",
    ],
    "mongodb_cm": [
        "MONGO_CM_INITDB_ROOT_USERNAME",
        "MONGO_CM_INITDB_ROOT_PASSWORD",
        "MONGO_CM_PORT",
        "MONGO_CM_URI",
        "MONGO_CM_URI_DOCKER",
        "MONGO_CM_URI_HOST",
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
    "flow_module": [
        # Cross-dependency: flow_module consumes from tshark's topic.
        # The real value is resolved from MongoDB CM in configuration_manager_logic.py
        # before launch() is called. This entry ensures it is written to the .env
        # with whatever value arrives in env_overrides (real) or default (fallback).
        "TSHARK_BASE_TOPIC",
        "MONGO_URI",
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
    "alert_module": [
        # Cross-dependency: alert_module (snort3) consumes from tshark's topic.
        # Same resolution strategy as flow_module above.
        "TSHARK_BASE_TOPIC",
        "MONGO_URI",
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
    "nrtdr_api": [
        "NRTDR_API_PORT",
        "NRTDR_API_HOST",
        "NRTDR_WS_POLL_INTERVAL",
        "NRTDR_WS_BATCH_SIZE",
    ],
    "alarm_collector": [
        "TB_USERNAME",
        "TB_PASSWORD",
        "TB_USE_HTTPS",
    ],
}

# Topic variables that producer tools publish to Kafka.
# Used by configuration_manager_logic.py to update the kafka_topics document in MongoDB CM.
PRODUCER_TOPIC_VARS: Dict[str, List[str]] = {
    "tshark":       ["TSHARK_BASE_TOPIC"],
    "telegraf":     ["TELEGRAF_BASE_TOPIC"],
    "fluentd":      ["FLUENTD_SYSLOG_BASE_TOPIC", "FLUENTD_SYSTEMD_BASE_TOPIC"],
    "falco":        ["FALCO_BASE_TOPIC"],
    "flow_module":  ["CIC_KAFKA_BASE_TOPIC_OUT"],
    "snort3":       ["SNORT_KAFKA_TOPIC_OUT"],
}

# Topic variables that consumer tools need to read from Kafka.
# Used by configuration_manager_logic.py to inject the real topic values from MongoDB CM.
CONSUMER_TOPIC_VARS: Dict[str, List[str]] = {
    "flow_module":  ["TSHARK_BASE_TOPIC"],
    "snort3":       ["TSHARK_BASE_TOPIC"],
    "opensearch":   [
        "TELEGRAF_BASE_TOPIC",
        "TSHARK_BASE_TOPIC",
        "FLUENTD_SYSLOG_BASE_TOPIC",
        "FLUENTD_SYSTEMD_BASE_TOPIC",
        "FALCO_BASE_TOPIC",
    ],
}


def launch(
    selected: "OrderedDict[str, List[str]]",
    env_overrides: Optional[Dict[str, str]] = None
) -> None:
    """
    Core launch function: resolves env vars, writes .env, and runs docker compose up.
    Called both from CLI (main) and from configuration_manager_logic.py (API).
    env_overrides contains tool-specific variables already resolved (including real topic values).
    ALWAYS_ENV_VARS are never replaced by env_overrides.
    """
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
    PFD = Path(__file__).resolve().parent.parent
    init_env_file_path = Path(__file__).resolve().parent / ".init_pmp_env"
    env_file_path = Path(__file__).resolve().parent / ".env"

    # Add info tool automatically when collection_module is selected
    if "collection_module" in selected and "info" not in selected["collection_module"]:
        selected["collection_module"].append("info")

    compose_profiles_list = cmd_parser().build_compose_profiles(selected)
    compose_profiles = ",".join(compose_profiles_list)

    print("Selected:", selected)
    print("COMPOSE_PROFILES:", compose_profiles_list)

    # build_default_env reads existing passwords from init_env_file_path to avoid regenerating them
    default_env = build_default_env(
        mid=mid,
        network_mode=network_mode,
        PFD=PFD,
        compose_profiles=compose_profiles,
        env_file_path=init_env_file_path
    )

    # Apply overrides from API - ALWAYS_ENV_VARS are protected and never replaced
    if env_overrides:
        for key, value in env_overrides.items():
            if key not in ALWAYS_ENV_VARS:
                default_env[key] = str(value)

    env_keys = collect_env_vars(
        selected=selected,
        tool_env_vars=TOOL_ENV_VARS,
        always_env_vars=ALWAYS_ENV_VARS
    )

    # On first run (init_pmp_env does not exist yet) write the full env as the
    # persistent reference file so subsequent runs can read generated passwords.
    if not init_env_file_path.exists():
        write_dotenv(
            env_keys=list(default_env.keys()),
            path=init_env_file_path,
            defaults=default_env,
            header=""
        )
        print(f"Initial PMP env written to {init_env_file_path}")

        written_path = init_env_file_path
    else:
        written_path = write_dotenv(
            env_keys=env_keys,
            path=env_file_path,
            defaults=default_env,
            header=""
        )

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

    for profile in compose_profiles_list:
        compose_cmd.extend(["--profile", profile])

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
        raise RuntimeError(f"Error executing docker compose: {e}") from e


def main() -> None:
    """
    CLI entry point: parses arguments and calls launch().
    """
    import json

    parser_obj = cmd_parser()
    args, selected = parser_obj.parse()

    env_overrides = None
    if args.env_overrides:
        try:
            with open(args.env_overrides, "r", encoding="utf-8") as f:
                env_overrides = json.load(f)
        except Exception as e:
            print(f"Warning: could not load env overrides file: {e}")

    launch(selected=selected, env_overrides=env_overrides)


if __name__ == "__main__":
    main()
