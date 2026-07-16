#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from gui_backend_common import (
    API_PID_FILE,
    BASE_CONTAINERS,
    BOOTSTRAP_LOG_FILE,
    CONFIGURATION_MANAGER_LOG_FILE,
    CONFIGURATION_MANAGER_API_NAME,
    GUI_DIR,
    GUI_ENV_FILE,
    GUI_LOG_FILE,
    GUI_PID_FILE,
    GUI_PROCESS_NAME,
    HDR_API_CONTAINER_NAME,
    HDR_API_NAME,
    INTERNAL_LOGS_DIR,
    LAUNCHER_ENV_FILE,
    LAUNCHER_INIT_ENV_FILE,
    LAUNCHER_DIR,
    NRTDR_API_CONTAINER_NAME,
    NRTDR_API_NAME,
    RUNTIME_DIR,
    STATE_FILE,
    ensure_runtime_directories,
)

DEFAULT_API_PORT = 8000
DEFAULT_GUI_PORT = 3000
DEFAULT_LOGS_DIR = INTERNAL_LOGS_DIR
DEFAULT_GUI_INIT_MODE = "auto"
DEFAULT_EMAIL_DOMAIN = "robust-6g.eu"
DEFAULT_POSTGRES_HOST = "localhost"
DEFAULT_POSTGRES_PORT = "5432"
DEFAULT_POSTGRES_USER = "robust6g_admin"
DEFAULT_POSTGRES_PASSWORD = "robust6g_pass"
DEFAULT_POSTGRES_DB = "robust6g_dashboard"
DEFAULT_GUI_BASE_PROFILES = [
    "-m",
    "communication_module",
    "-t",
    "kafka,filebeat",
    "-m",
    "db_module",
    "-t",
    "mongodb,mongodb_cm,postgres_gui,redis,mimir",
    "-m",
    "aggregation_module",
    "-t",
    "prometheus", #FIXME Probar Opensearch
]
BASE_CONTAINER_EXPECTATIONS = {
    "kafka_robust6g": "healthy",
    "filebeat_robust6g": "healthy",
    "mongodb_robust6g": "healthy",
    "mongodb_cm_robust6g": "healthy",
    "postgres_gui_robust6g": "healthy",
    "redis_robust6g": "healthy",
    "redis_worker_robust6g": "healthy",
    "mimir_robust6g": "running",
    "prometheus_server_robust6g": "healthy",
}


class BootstrapError(RuntimeError):
    """Raised when the bootstrap flow cannot continue safely."""


class BootstrapLogger:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        print(line)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap the GUI backend stack: base containers, Configuration "
            "Manager API, NRTDR API, HDR API, and the dashboard GUI. Without "
            "flags it starts the base services, reuses or starts all three "
            "APIs, prepares the GUI in auto mode, and reuses or starts the "
            "dashboard."
        ),
        epilog=(
            "Examples:\n"
            "  python3 Launcher/bootstrap_gui_backend.py\n"
            "  python3 Launcher/bootstrap_gui_backend.py --gui-init-mode start-only\n"
            "  python3 Launcher/bootstrap_gui_backend.py --skip-base --skip-api\n"
            "  python3 Launcher/bootstrap_gui_backend.py --skip-nrtdr-api\n"
            "  python3 Launcher/bootstrap_gui_backend.py --skip-hdr-api\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--gui-port",
        type=int,
        default=DEFAULT_GUI_PORT,
        help="Port for the dashboard GUI (default: 3000).",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=DEFAULT_API_PORT,
        help="Port for the Configuration Manager API (default: 8000).",
    )
    parser.add_argument(
        "--logs-dir",
        default=str(DEFAULT_LOGS_DIR),
        help="Directory where bootstrap, API and GUI logs are stored.",
    )
    parser.add_argument(
        "--gui-init-mode",
        choices=["auto", "start-only", "reinit"],
        default=DEFAULT_GUI_INIT_MODE,
        help=(
            "GUI initialization mode: auto reuses existing setup, start-only "
            "skips install/migrate/seed, reinit forces initialization."
        ),
    )
    parser.add_argument(
        "--skip-base",
        action="store_true",
        help="Skip starting the base containers managed by start_containers.py.",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Skip starting or checking the Configuration Manager API.",
    )
    parser.add_argument(
        "--skip-nrtdr-api",
        action="store_true",
        help="Skip starting or checking the NRTDR API.",
    )
    parser.add_argument(
        "--skip-hdr-api",
        action="store_true",
        help="Skip starting or checking the HDR API.",
    )
    parser.add_argument(
        "--skip-gui",
        action="store_true",
        help="Skip preparing and starting the dashboard GUI.",
    )
    return parser.parse_args()


def read_simple_env(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def generate_secret() -> str:
    import secrets

    return secrets.token_urlsafe(32)


def is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(pid_path: Path) -> Optional[int]:
    if not pid_path.exists():
        return None

    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def write_pid(pid_path: Path, pid: int) -> None:
    pid_path.write_text(f"{pid}\n", encoding="utf-8")


def remove_pid_file(pid_path: Path) -> None:
    if pid_path.exists():
        pid_path.unlink()


def terminate_pid(pid: int, logger: BootstrapLogger, label: str) -> None:
    if not is_process_running(pid):
        return

    logger.log(f"Stopping stale {label} process with PID {pid}.")
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not is_process_running(pid):
            return
        time.sleep(0.5)

    logger.log(f"Force killing stale {label} process with PID {pid}.")
    os.kill(pid, signal.SIGKILL)


def ensure_command(command: str, logger: BootstrapLogger) -> None:
    if shutil.which(command):
        return
    raise BootstrapError(
        f"Required command '{command}' is not available in PATH. "
        "Please install it before running the bootstrap."
    )


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def http_request_json(
    url: str,
    timeout: float = 2.0,
) -> tuple[int, str, Optional[Any]]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            payload = None
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None
            return response.status, body, payload
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        return 0, str(exc), None


def is_our_configuration_manager_api(port: int) -> bool:
    status, _, payload = http_request_json(f"http://localhost:{port}/")
    if status != 200 or not isinstance(payload, dict):
        return False
    return payload.get("message") == "Configuration Manager API is running"


def is_our_nrtdr_api(port: int) -> bool:
    status, _, payload = http_request_json(f"http://localhost:{port}/")
    if status != 200 or not isinstance(payload, dict):
        return False
    return payload.get("name") == "PMP Near Real-Time Data Streaming API"


def is_our_hdr_api(port: int) -> bool:
    status, _, payload = http_request_json(f"http://localhost:{port}/")
    if status != 200 or not isinstance(payload, dict):
        return False
    return payload.get("name") == "PMP Historical Data Retrieval API"


def is_our_gui(port: int) -> bool:
    status, body, payload = http_request_json(
        f"http://localhost:{port}/api/auth/session",
        timeout=5.0,
    )
    if status != 200:
        return False

    # NextAuth returns literal `null` when the dashboard is up but no session
    # is established yet, which is still a valid ownership signal for port 3000.
    return payload is not None or body.strip() == "null"


def ensure_port_available_or_owned(
    port: int,
    logger: BootstrapLogger,
    service_name: str,
    validator,
) -> bool:
    if not is_port_open("127.0.0.1", port):
        return False

    if validator(port):
        logger.log(
            f"Port {port} is already serving the managed {service_name}; it will be reused.",
        )
        return True

    raise BootstrapError(
        f"Port {port} is already in use by a different service. "
        f"Please free the port before starting {service_name}."
    )


def run_command(
    command: Iterable[str],
    logger: BootstrapLogger,
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    logger.log(f"Running command: {' '.join(command)}")
    completed = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout.strip():
        logger.log(completed.stdout.rstrip())
    if completed.stderr.strip():
        logger.log(completed.stderr.rstrip())
    if completed.returncode != 0:
        raise BootstrapError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}"
        )
    return completed


def docker_container_status(container_name: str) -> str:
    completed = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
            container_name,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return "missing"
    return completed.stdout.strip() or "unknown"


def wait_for_base_containers(logger: BootstrapLogger, timeout_seconds: int = 180) -> None:
    deadline = time.time() + timeout_seconds
    pending = set(BASE_CONTAINER_EXPECTATIONS.keys())
    logger.log("Waiting for base containers to become ready.")

    while pending and time.time() < deadline:
        for container_name in list(pending):
            status = docker_container_status(container_name)
            expected = BASE_CONTAINER_EXPECTATIONS[container_name]
            if status == expected:
                logger.log(f"Container {container_name} is {status}.")
                pending.remove(container_name)
        if pending:
            time.sleep(2.0)

    if pending:
        statuses = {
            container_name: docker_container_status(container_name)
            for container_name in sorted(pending)
        }
        raise BootstrapError(
            f"Timed out waiting for base containers: {statuses}"
        )


def wait_for_http_service(
    url: str,
    validator,
    logger: BootstrapLogger,
    label: str,
    timeout_seconds: int = 120,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if validator():
            logger.log(f"{label} is ready at {url}.")
            return
        time.sleep(1.5)
    raise BootstrapError(f"Timed out waiting for {label} at {url}.")


def load_launcher_database_values() -> Dict[str, str]:
    values = read_simple_env(LAUNCHER_ENV_FILE)
    if not values:
        values = read_simple_env(LAUNCHER_INIT_ENV_FILE)

    return {
        "POSTGRES_GUI_USER": values.get("POSTGRES_GUI_USER", DEFAULT_POSTGRES_USER),
        "POSTGRES_GUI_PASSWORD": values.get(
            "POSTGRES_GUI_PASSWORD",
            DEFAULT_POSTGRES_PASSWORD,
        ),
        "POSTGRES_GUI_DB": values.get("POSTGRES_GUI_DB", DEFAULT_POSTGRES_DB),
        "POSTGRES_GUI_PORT": values.get("POSTGRES_GUI_PORT", DEFAULT_POSTGRES_PORT),
    }


def load_launcher_runtime_values() -> Dict[str, str]:
    values = read_simple_env(LAUNCHER_INIT_ENV_FILE)
    values.update(read_simple_env(LAUNCHER_ENV_FILE))
    return values


def build_gui_env(api_port: int, gui_port: int) -> Dict[str, str]:
    existing_env = read_simple_env(GUI_ENV_FILE)
    launcher_values = load_launcher_database_values()

    database_url = (
        "postgresql://"
        f"{launcher_values['POSTGRES_GUI_USER']}:"
        f"{launcher_values['POSTGRES_GUI_PASSWORD']}@"
        f"{DEFAULT_POSTGRES_HOST}:{launcher_values['POSTGRES_GUI_PORT']}/"
        f"{launcher_values['POSTGRES_GUI_DB']}?schema=public"
    )

    return {
        "DATABASE_URL": database_url,
        "NEXT_PUBLIC_API_URL": f"http://localhost:{gui_port}/api",
        "NEXTAUTH_SECRET": existing_env.get("NEXTAUTH_SECRET", generate_secret()),
        "NEXTAUTH_URL": f"http://localhost:{gui_port}",
        "EXTERNAL_API_BASE_URL": f"http://localhost:{api_port}",
        "EMAIL_DOMAIN": existing_env.get("EMAIL_DOMAIN", DEFAULT_EMAIL_DOMAIN),
        "JWT_SECRET": existing_env.get("JWT_SECRET", generate_secret()),
        "NODE_ENV": "development",
    }


def write_gui_env_file(values: Dict[str, str], logger: BootstrapLogger) -> None:
    lines = [f'{key}="{value}"' for key, value in values.items()]
    GUI_ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.log(f"GUI environment written to {GUI_ENV_FILE}.")


def query_postgres_seed_state(logger: BootstrapLogger) -> tuple[bool, bool]:
    values = load_launcher_database_values()
    organization_query = (
        'SELECT EXISTS (SELECT 1 FROM "Organization" WHERE slug = \'robust-6g\');'
    )
    admin_query = (
        'SELECT EXISTS (SELECT 1 FROM "User" WHERE email = \'admin@robust-6g.eu\');'
    )

    queries = {
        "organization": organization_query,
        "admin": admin_query,
    }
    results: Dict[str, bool] = {}

    for key, query in queries.items():
        completed = subprocess.run(
            [
                "docker",
                "exec",
                "postgres_gui_robust6g",
                "psql",
                "-U",
                values["POSTGRES_GUI_USER"],
                "-d",
                values["POSTGRES_GUI_DB"],
                "-tAc",
                query,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            logger.log(
                f"Seed state query for {key} failed; GUI seed will run. "
                f"Details: {completed.stderr.strip()}",
            )
            return False, False
        results[key] = completed.stdout.strip().lower() == "t"

    return results["organization"], results["admin"]


def prepare_gui_environment(
    mode: str,
    api_port: int,
    gui_port: int,
    logger: BootstrapLogger,
) -> None:
    write_gui_env_file(build_gui_env(api_port=api_port, gui_port=gui_port), logger)

    if mode == "start-only":
        if not (GUI_DIR / "node_modules").exists():
            raise BootstrapError(
                "GUI start-only mode requested, but node_modules is missing."
            )
        logger.log("GUI start-only mode selected; skipping install, Prisma and seed steps.")
        return

    if mode in {"auto", "reinit"} and not (GUI_DIR / "node_modules").exists():
        run_command(["pnpm", "install"], logger, cwd=GUI_DIR)

    run_command(["pnpm", "prisma", "generate"], logger, cwd=GUI_DIR)
    run_command(["pnpm", "prisma", "migrate", "deploy"], logger, cwd=GUI_DIR)

    if mode == "reinit":
        run_command(["pnpm", "prisma", "db", "seed"], logger, cwd=GUI_DIR)
        return

    organization_exists, admin_exists = query_postgres_seed_state(logger)
    if organization_exists and admin_exists:
        logger.log(
            "GUI database already contains the expected organization and admin; seed step skipped.",
        )
        return

    run_command(["pnpm", "prisma", "db", "seed"], logger, cwd=GUI_DIR)


def start_configuration_manager_api(
    api_port: int,
    logger: BootstrapLogger,
    logs_dir: Path,
) -> str:
    if ensure_port_available_or_owned(
        api_port,
        logger,
        CONFIGURATION_MANAGER_API_NAME,
        is_our_configuration_manager_api,
    ):
        return "reused"

    stale_pid = read_pid(API_PID_FILE)
    if stale_pid:
        terminate_pid(stale_pid, logger, CONFIGURATION_MANAGER_API_NAME)
        remove_pid_file(API_PID_FILE)

    uvicorn_path = shutil.which("uvicorn")
    if not uvicorn_path:
        raise BootstrapError("uvicorn is not available in PATH.")

    log_path = logs_dir / CONFIGURATION_MANAGER_LOG_FILE.name
    handle = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [
            uvicorn_path,
            "--app-dir",
            str(LAUNCHER_DIR.parent / "APIs" / "ConfigurationManager"),
            "configuration_manager_api:app",
            "--port",
            str(api_port),
            "--host",
            "0.0.0.0",
        ],
        cwd=str(LAUNCHER_DIR.parent),
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    write_pid(API_PID_FILE, process.pid)
    logger.log(f"Started Configuration Manager API with PID {process.pid}.")
    return "started"


def start_nrtdr_api(
    nrtdr_api_port: int,
    logger: BootstrapLogger,
) -> str:
    """Reuses or starts the managed NRTDR API container before falling back to compose launch."""
    if ensure_port_available_or_owned(
        nrtdr_api_port,
        logger,
        NRTDR_API_NAME,
        is_our_nrtdr_api,
    ):
        return "reused"

    container_status = docker_container_status(NRTDR_API_CONTAINER_NAME)
    if container_status in {"created", "exited"}:
        run_command(
            ["docker", "start", NRTDR_API_CONTAINER_NAME],
            logger,
            cwd=LAUNCHER_DIR.parent,
        )
        logger.log(
            f"Started existing NRTDR API container {NRTDR_API_CONTAINER_NAME} without rebuild.",
        )
        return "started"

    if container_status in {"running", "healthy"}:
        logger.log(
            f"NRTDR API container {NRTDR_API_CONTAINER_NAME} is already {container_status}; waiting for readiness.",
        )
        return "reused"

    command = [
        sys.executable,
        str(LAUNCHER_DIR / "start_containers.py"),
        "-m",
        "apis_module",
        "-t",
        "nrtdr_api",
    ]
    run_command(
        command,
        logger,
        cwd=LAUNCHER_DIR.parent,
    )
    logger.log(
        f"Ensured NRTDR API container {NRTDR_API_CONTAINER_NAME} is started on port {nrtdr_api_port}.",
    )
    return "started"


def start_hdr_api(
    hdr_api_port: int,
    logger: BootstrapLogger,
) -> str:
    """Reuses or starts the managed HDR API container before falling back to compose launch."""
    if ensure_port_available_or_owned(
        hdr_api_port,
        logger,
        HDR_API_NAME,
        is_our_hdr_api,
    ):
        return "reused"

    container_status = docker_container_status(HDR_API_CONTAINER_NAME)
    if container_status in {"created", "exited"}:
        run_command(
            ["docker", "start", HDR_API_CONTAINER_NAME],
            logger,
            cwd=LAUNCHER_DIR.parent,
        )
        logger.log(
            f"Started existing HDR API container {HDR_API_CONTAINER_NAME} without rebuild.",
        )
        return "started"

    if container_status in {"running", "healthy"}:
        logger.log(
            f"HDR API container {HDR_API_CONTAINER_NAME} is already {container_status}; waiting for readiness.",
        )
        return "reused"

    command = [
        sys.executable,
        str(LAUNCHER_DIR / "start_containers.py"),
        "-m",
        "apis_module",
        "-t",
        "hdr_api",
    ]
    run_command(
        command,
        logger,
        cwd=LAUNCHER_DIR.parent,
    )
    logger.log(
        f"Ensured HDR API container {HDR_API_CONTAINER_NAME} is started on port {hdr_api_port}.",
    )
    return "started"


def start_gui(gui_port: int, logger: BootstrapLogger, logs_dir: Path) -> str:
    if ensure_port_available_or_owned(gui_port, logger, GUI_PROCESS_NAME, is_our_gui):
        return "reused"

    stale_pid = read_pid(GUI_PID_FILE)
    if stale_pid:
        terminate_pid(stale_pid, logger, GUI_PROCESS_NAME)
        remove_pid_file(GUI_PID_FILE)

    log_path = logs_dir / GUI_LOG_FILE.name
    handle = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        ["pnpm", "exec", "next", "dev", "-p", str(gui_port)],
        cwd=str(GUI_DIR),
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    write_pid(GUI_PID_FILE, process.pid)
    logger.log(f"Started dashboard GUI with PID {process.pid}.")
    return "started"


def write_state_file(
    *,
    api_port: int,
    nrtdr_api_port: int,
    hdr_api_port: int,
    gui_port: int,
    logs_dir: Path,
    logger: BootstrapLogger,
    api_status: str,
    nrtdr_api_status: str,
    hdr_api_status: str,
    gui_status: str,
) -> None:
    state = {
        "updated_at": datetime.now().isoformat(),
        "api_port": api_port,
        "nrtdr_api_port": nrtdr_api_port,
        "hdr_api_port": hdr_api_port,
        "gui_port": gui_port,
        "logs_dir": str(logs_dir),
        "bootstrap_log": str(logs_dir / BOOTSTRAP_LOG_FILE.name),
        "api_log": str(logs_dir / CONFIGURATION_MANAGER_LOG_FILE.name),
        "nrtdr_api_container": NRTDR_API_CONTAINER_NAME,
        "hdr_api_container": HDR_API_CONTAINER_NAME,
        "gui_log": str(logs_dir / GUI_LOG_FILE.name),
        "api_pid_file": str(API_PID_FILE),
        "gui_pid_file": str(GUI_PID_FILE),
        "api_status": api_status,
        "nrtdr_api_status": nrtdr_api_status,
        "hdr_api_status": hdr_api_status,
        "gui_status": gui_status,
        "base_containers": BASE_CONTAINERS,
    }
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    logger.log(f"Runtime state written to {STATE_FILE}.")


def start_base_services(logger: BootstrapLogger) -> None:
    command = [
        sys.executable,
        str(LAUNCHER_DIR / "start_containers.py"),
        *DEFAULT_GUI_BASE_PROFILES,
    ]
    run_command(command, logger, cwd=LAUNCHER_DIR.parent)


def main() -> int:
    args = parse_args()
    logs_dir = ensure_runtime_directories(Path(args.logs_dir).resolve())
    logger = BootstrapLogger(logs_dir / BOOTSTRAP_LOG_FILE.name)

    try:
        ensure_command("docker", logger)
        if not args.skip_gui:
            ensure_command("pnpm", logger)
        if not args.skip_api and not shutil.which("uvicorn"):
            raise BootstrapError("uvicorn is not available in PATH.")

        api_status = "skipped"
        nrtdr_api_status = "skipped"
        hdr_api_status = "skipped"
        gui_status = "skipped"
        launcher_values = load_launcher_runtime_values()
        nrtdr_api_port = int(launcher_values.get("NRTDR_API_PORT", "8001"))
        hdr_api_port = int(launcher_values.get("HDR_API_PORT", "8002"))

        if not args.skip_base:
            start_base_services(logger)
            wait_for_base_containers(logger)
        else:
            logger.log("Skipping base container startup as requested.")

        if not args.skip_api:
            api_status = start_configuration_manager_api(args.api_port, logger, logs_dir)
            wait_for_http_service(
                url=f"http://localhost:{args.api_port}/",
                validator=lambda: is_our_configuration_manager_api(args.api_port),
                logger=logger,
                label="Configuration Manager API",
            )
        else:
            logger.log("Skipping Configuration Manager API startup as requested.")

        if not args.skip_nrtdr_api:
            nrtdr_api_status = start_nrtdr_api(nrtdr_api_port, logger)
            wait_for_http_service(
                url=f"http://localhost:{nrtdr_api_port}/",
                validator=lambda: is_our_nrtdr_api(nrtdr_api_port),
                logger=logger,
                label="NRTDR API",
            )
        else:
            logger.log("Skipping NRTDR API startup as requested.")

        if not args.skip_hdr_api:
            hdr_api_status = start_hdr_api(hdr_api_port, logger)
            wait_for_http_service(
                url=f"http://localhost:{hdr_api_port}/",
                validator=lambda: is_our_hdr_api(hdr_api_port),
                logger=logger,
                label="HDR API",
            )
        else:
            logger.log("Skipping HDR API startup as requested.")

        if not args.skip_gui:
            gui_is_running = ensure_port_available_or_owned(
                args.gui_port,
                logger,
                GUI_PROCESS_NAME,
                is_our_gui,
            )
            if not gui_is_running:
                prepare_gui_environment(
                    mode=args.gui_init_mode,
                    api_port=args.api_port,
                    gui_port=args.gui_port,
                    logger=logger,
                )
            else:
                logger.log(
                    f"Dashboard GUI already responds on port {args.gui_port}; environment preparation skipped.",
                )
            gui_status = start_gui(args.gui_port, logger, logs_dir)
            wait_for_http_service(
                url=f"http://localhost:{args.gui_port}/api/auth/session",
                validator=lambda: is_our_gui(args.gui_port),
                logger=logger,
                label="dashboard GUI",
            )
        else:
            logger.log("Skipping dashboard GUI startup as requested.")

        write_state_file(
            api_port=args.api_port,
            nrtdr_api_port=nrtdr_api_port,
            hdr_api_port=hdr_api_port,
            gui_port=args.gui_port,
            logs_dir=logs_dir,
            logger=logger,
            api_status=api_status,
            nrtdr_api_status=nrtdr_api_status,
            hdr_api_status=hdr_api_status,
            gui_status=gui_status,
        )

        logger.log("Bootstrap completed successfully.")
        logger.log(f"Dashboard URL: http://localhost:{args.gui_port}")
        logger.log(f"Configuration Manager API URL: http://localhost:{args.api_port}")
        logger.log(f"NRTDR API URL: http://localhost:{nrtdr_api_port}")
        logger.log(f"HDR API URL: http://localhost:{hdr_api_port}")
        return 0
    except BootstrapError as exc:
        logger.log(f"Bootstrap failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
