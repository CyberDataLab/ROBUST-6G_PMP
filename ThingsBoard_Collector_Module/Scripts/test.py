#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import sys
import time
from typing import Any, Dict, Optional, Tuple

import requests


def now_ms() -> int:
    return int(time.time() * 1000)


def is_json_response(resp: requests.Response) -> bool:
    ctype = (resp.headers.get("Content-Type") or "").lower()
    return "application/json" in ctype or "json" in ctype


def try_parse_json(text: str) -> Tuple[bool, Optional[Any]]:
    try:
        return True, json.loads(text)
    except Exception:
        return False, None


def print_section(title: str) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def print_request(method: str, url: str, payload: Optional[Dict[str, Any]]) -> None:
    print(f">>> {method} {url}")
    if payload is not None:
        print(">>> Payload:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def print_response(resp: requests.Response, elapsed_ms: int) -> None:
    print(f"<<< HTTP {resp.status_code} ({elapsed_ms} ms)")
    # 1) Raw (as-is)
    print("<<< Raw response:")
    print(resp.text)

    # 2) Pretty JSON (if applicable / if it can be parsed)
    ok, obj = try_parse_json(resp.text)
    if ok:
        print("<<< Parsed JSON (pretty):")
        print(json.dumps(obj, ensure_ascii=False, indent=2))


def http_call(
    session: requests.Session,
    base_url: str,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout_s: float = 15.0,
) -> requests.Response:
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = {"Content-Type": "application/json"}

    print_request(method, url, payload)

    start = now_ms()
    try:
        if method.upper() == "GET":
            resp = session.get(url, timeout=timeout_s)
        elif method.upper() == "POST":
            resp = session.post(url, headers=headers, json=payload, timeout=timeout_s)
        else:
            raise ValueError(f"Unsupported method: {method}")
    except requests.RequestException as e:
        print(f"<<< Network/requests ERROR: {e}")
        raise

    elapsed = now_ms() - start
    print_response(resp, elapsed)
    return resp


def extract_devices_from_status(status_json: Any) -> Dict[str, Any]:
    """
    Expects something like:
    {
      "devices": { "<entityId>": {...}, ... },
      ...
    }
    """
    if isinstance(status_json, dict) and isinstance(status_json.get("devices"), dict):
        return status_json["devices"]
    return {}

def get_health_json(session: requests.Session, base_url: str, timeout_s: float) -> Optional[Dict[str, Any]]:
    resp = http_call(session, base_url, "GET", "/health", timeout_s=timeout_s)
    ok, obj = try_parse_json(resp.text)
    if ok and isinstance(obj, dict):
        return obj
    return None


def assert_no_orphans(health: Dict[str, Any]) -> None:
    orphan = int(health.get("orphan_monitor_threads", 0) or 0)
    if orphan > 0:
        raise RuntimeError(f"ORPHAN THREADS DETECTED: orphan_monitor_threads={orphan} health={health}")


def warn(msg: str) -> None:
    print(f"!! WARNING: {msg}")


def info(msg: str) -> None:
    print(f"-- {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test runner for the ConfigurationManagerThingsboard API"
    )
    parser.add_argument("--base-url", default="http://localhost:5000", help="API base URL")
    parser.add_argument("--thingsboard-ip", default="localhost", help="ThingsBoard IP/host")
    parser.add_argument("--thingsboard-port", type=int, default=8099, help="ThingsBoard port")
    parser.add_argument(
        "--entity-id",
        default="71c0e3e0-a8e1-11f0-a091-2d2de22ced6c",
        help="Valid EntityId (good device)",
    )
    parser.add_argument(
        "--bad-entity-id",
        default="71c0e3e0-a8e1-11f0-a091-000000000000",
        help="Non-existent EntityId (for error testing)",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="Timeout per request (seconds)")
    parser.add_argument(
        "--health",
        action="store_true",
        help="If specified, also does GET /health at the start (optional).",
    )

    args = parser.parse_args()

    base_url = args.base_url
    tb_ip = args.thingsboard_ip
    tb_port = args.thingsboard_port
    hvac_id = args.entity_id
    presence_id = "7c7c1520-a8e1-11f0-a091-2d2de22ced6c"
    temperature_id = "76f8f320-a8e1-11f0-a091-2d2de22ced6c"
    bad_id = args.bad_entity_id
    list_good_id = [hvac_id, presence_id, temperature_id]
    sleep_seconds = 60

    session = requests.Session()

    try:
        # (Optional) Health check
        if args.health:
            print_section("0) GET /health (optional)")
            http_call(session, base_url, "GET", "/health", timeout_s=args.timeout)

        # 1) Monitor 1 device
        print_section("1) POST /ConfigurationManagerThingsboard/collectDataFromThingsboard (single)")
        payload_single = {
            "thingsboardsIP": tb_ip,
            "thingsboardPort": tb_port,
            "entityId": hvac_id,
            "entityType": "DEVICE",
        }
        http_call(
            session,
            base_url,
            "POST",
            "/ConfigurationManagerThingsboard/collectDataFromThingsboard",
            payload_single,
            timeout_s=args.timeout,
        )
        print_section("Pause so the device can collect some information " + str(sleep_seconds) + " (seconds), please remove and generate a new one alarm")
        time.sleep(sleep_seconds)
        
        # 2) Check monitoringStatus
        print_section("2) GET /ConfigurationManagerThingsboard/monitoringStatus (check after start)")
        resp = http_call(
            session,
            base_url,
            "GET",
            "/ConfigurationManagerThingsboard/monitoringStatus",
            timeout_s=args.timeout,
        )
        ok, status_json = try_parse_json(resp.text)
        if ok:
            devices = extract_devices_from_status(status_json)
            if hvac_id in devices:
                info(f"OK: The device {hvac_id} appears in monitoringStatus.")
            else:
                warn(f"The device {hvac_id} does NOT appear in monitoringStatus (check response).")
        else:
            warn("Could not parse monitoringStatus as JSON; no checks performed.")

        # 3) Repeat monitoring of the same device
        print_section("3) POST /collectDataFromThingsboard (same device again)")
        http_call(
            session,
            base_url,
            "POST",
            "/ConfigurationManagerThingsboard/collectDataFromThingsboard",
            payload_single,
            timeout_s=args.timeout,
        )

        # 4) Stop monitoring that device
        print_section("4) POST /ConfigurationManagerThingsboard/stopMonitoring (single)")
        payload_stop_single = {"entityId": hvac_id}
        http_call(
            session,
            base_url,
            "POST",
            "/ConfigurationManagerThingsboard/stopMonitoring",
            payload_stop_single,
            timeout_s=args.timeout,
        )

        health = get_health_json(session, base_url, args.timeout)
        if health:
            assert_no_orphans(health)

        # 5) Monitor list: [good_id, bad_id]
        print_section("5) POST /collectDataFromThingsboard (multiple: good + non-existent)")
        payload_multi = {
            "thingsboardsIP": tb_ip,
            "thingsboardPort": tb_port,
            "entityIds": [list_good_id[0], list_good_id[1], list_good_id[2], bad_id],
            "entityType": "DEVICE",
        }
        http_call(
            session,
            base_url,
            "POST",
            "/ConfigurationManagerThingsboard/collectDataFromThingsboard",
            payload_multi,
            timeout_s=args.timeout,
        )

        # 6) GET monitoringStatus to see what is active
        print_section("6) GET /ConfigurationManagerThingsboard/monitoringStatus (check after multi)")
        resp = http_call(
            session,
            base_url,
            "GET",
            "/ConfigurationManagerThingsboard/monitoringStatus",
            timeout_s=args.timeout,
        )
        ok, status_json = try_parse_json(resp.text)
        if ok:
            devices = extract_devices_from_status(status_json)
            if hvac_id in devices:
                info(f"OK: The good device {hvac_id} is active.")
            else:
                warn(f"The good device {hvac_id} is NOT active (check response).")

            if bad_id in devices:
                warn(f"The non-existent device {bad_id} appears as active (that would be odd).")
            else:
                info(f"INFO: The non-existent device {bad_id} does NOT appear as active (expected).")
        else:
            warn("Could not parse monitoringStatus as JSON; no checks performed.")

        # 7) Monitor list: good ids
        print_section("7) POST /collectDataFromThingsboard (multiple: good)")
        payload_multi = {
            "thingsboardsIP": tb_ip,
            "thingsboardPort": tb_port,
            "entityIds": list_good_id,
            "entityType": "DEVICE",
        }
        http_call(
            session,
            base_url,
            "POST",
            "/ConfigurationManagerThingsboard/collectDataFromThingsboard",
            payload_multi,
            timeout_s=args.timeout,
        )
        print_section("Pause so the device can collect some information " + str(sleep_seconds) + " (seconds), please remove and generate a new one alarm")
        time.sleep(sleep_seconds)

        # 8) GET monitoringStatus to see what is active
        print_section("8) GET /ConfigurationManagerThingsboard/monitoringStatus (check after multi)")
        resp = http_call(
            session,
            base_url,
            "GET",
            "/ConfigurationManagerThingsboard/monitoringStatus",
            timeout_s=args.timeout,
        )
        ok, status_json = try_parse_json(resp.text)
        if ok:
            devices = extract_devices_from_status(status_json)
            for device in devices:
                if device in (hvac_id, presence_id, temperature_id):
                    info(f"OK: The good device {device} is active.")
                else:
                    warn(f"The good device {device} is NOT active (check response).")

            if bad_id in devices:
                warn(f"The non-existent device {bad_id} appears as active (that would be odd).")
            else:
                info(f"INFO: The non-existent device {bad_id} does NOT appear as active (expected).")
        else:
            warn("Could not parse monitoringStatus as JSON; no checks performed.")


        # 9) stopAllMonitoring
        print_section("9) POST /ConfigurationManagerThingsboard/stopAllMonitoring (confirm=true)")
        payload_stop_all = {"confirm": True}
        http_call(
            session,
            base_url,
            "POST",
            "/ConfigurationManagerThingsboard/stopAllMonitoring",
            payload_stop_all,
            timeout_s=args.timeout,
        )

        #9b) Last check
        print_section("9b) Check /health until monitor_threads_alive == 0 and no orphans")
        deadline = time.time() + 20  # segundos
        last_health = None
        while time.time() < deadline:
            h = get_health_json(session, base_url, args.timeout)
            last_health = h
            if not h:
                time.sleep(1)
                continue
            if int(h.get("orphan_monitor_threads", 0) or 0) == 0 and int(h.get("monitor_threads_alive", 0) or 0) == 0:
                info("OK: No monitor threads alive and no orphan threads.")
                break
            time.sleep(1)

        if last_health:
            assert_no_orphans(last_health)
            if int(last_health.get("monitor_threads_alive", 0) or 0) != 0:
                warn(f"Monitor threads still alive after stopAll: {last_health}")



                print_section("END")
                return 0

    except Exception as e:
        print_section("ABORTED DUE TO ERROR")
        print(str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
