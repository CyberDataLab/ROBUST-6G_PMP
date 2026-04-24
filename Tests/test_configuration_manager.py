"""
test_configuration_manager.py

Integration tests for the Configuration Manager API endpoints.
Uses the 'requests' library to call the running API.

API v3 changes covered by this test file:
- toolName is sent as a query parameter in deploy/update endpoints.
- Deploy/update JSON bodies contain only configuration overrides.
- Each deploy request deploys exactly one tool.

Run the API first, then execute this file.

Usage:
    python test_configuration_manager.py
    python test_configuration_manager.py --base-url http://localhost:9000
"""

import argparse
import json
import sys
from typing import Any, Dict, Optional

import requests


passed = 0
failed = 0


def print_section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def assert_test(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅  PASS | {name}")
    else:
        failed += 1
        print(f"  ❌  FAIL | {name}")
        if detail:
            print(f"           Detail: {detail}")


def call(
    session: requests.Session,
    base_url: str,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
) -> requests.Response:
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    print(f"\n  --> {method} {url}")
    if params:
        print(f"      Query params: {json.dumps(params, indent=6)}")
    if payload is not None:
        print(f"      Body: {json.dumps(payload, indent=6)}")

    method_upper = method.upper()
    if method_upper == "GET":
        response = session.get(url, params=params, timeout=timeout)
    elif method_upper == "POST":
        response = session.post(url, params=params, json=payload, timeout=timeout)
    elif method_upper == "PUT":
        response = session.put(url, params=params, json=payload, timeout=timeout)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    print(f"  <-- HTTP {response.status_code}")
    try:
        print(f"      Response: {json.dumps(response.json(), indent=6)}")
    except Exception:
        print(f"      Response (raw): {response.text[:300]}")

    return response


def test_health(session: requests.Session, base_url: str) -> None:
    print_section("1. Health check - GET /")
    resp = call(session, base_url, "GET", "/")
    assert_test("Root returns 200", resp.status_code == 200)
    data = resp.json()
    assert_test("Response contains 'message'", "message" in data)


def test_get_configuration_options(session: requests.Session, base_url: str) -> None:
    print_section("2. GET /ConfigurationManager/getConfigurationOptions")

    resp = call(
        session,
        base_url,
        "GET",
        "/ConfigurationManager/getConfigurationOptions",
        params={"toolName": "tshark"},
    )
    assert_test("tshark options returns 200", resp.status_code == 200)
    data = resp.json()
    assert_test("Response contains configurable_variables", "configurable_variables" in data)
    assert_test("configurable_variables is a list", isinstance(data.get("configurable_variables"), list))
    assert_test("tshark has at least one variable", len(data.get("configurable_variables", [])) > 0)

    var_names = [v["name"] for v in data.get("configurable_variables", [])]
    assert_test("TSHARK_BASE_TOPIC is in tshark options", "TSHARK_BASE_TOPIC" in var_names)

    resp = call(
        session,
        base_url,
        "GET",
        "/ConfigurationManager/getConfigurationOptions",
        params={"toolName": "snort3"},
    )
    assert_test("snort3 options returns 200", resp.status_code == 200)

    resp = call(
        session,
        base_url,
        "GET",
        "/ConfigurationManager/getConfigurationOptions",
        params={"toolName": "flow_module"},
    )
    assert_test("flow_module options returns 200", resp.status_code == 200)

    resp = call(
        session,
        base_url,
        "GET",
        "/ConfigurationManager/getConfigurationOptions",
        params={"toolName": "nonexistent_tool"},
    )
    assert_test("Unknown tool returns 404", resp.status_code == 404)

    resp = call(session, base_url, "GET", "/ConfigurationManager/getConfigurationOptions")
    assert_test("Missing toolName query param returns 422", resp.status_code == 422)


def test_deploy_network_tool(session: requests.Session, base_url: str) -> Optional[str]:
    print_section("3. POST /ConfigurationManager/DeployNetworkTool")

    config_id = None

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        params={"toolName": "tshark"},
        payload={"configuration": {}},
    )
    assert_test("tshark with empty config returns 200", resp.status_code == 200)
    data = resp.json()
    assert_test("Response contains config_id", "config_id" in data)
    assert_test("Response deployed_tool is tshark", data.get("deployed_tool") == "tshark")
    if "config_id" in data:
        config_id = data["config_id"]
        print(f"\n      config_id obtained: {config_id}")

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        params={"toolName": "tshark"},
        payload={"configuration": {"TSHARK_BASE_TOPIC": "my_custom_topic"}},
    )
    assert_test("tshark with partial config returns 200", resp.status_code == 200)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        params={"toolName": "flow_module"},
        payload={"configuration": {}},
    )
    assert_test("flow_module with empty config returns 200", resp.status_code == 200)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        params={"toolName": "telegraf"},
        payload={"configuration": {}},
    )
    assert_test("telegraf in DeployNetworkTool returns 400", resp.status_code == 400)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        payload={"configuration": {}},
    )
    assert_test("Missing toolName query param returns 422", resp.status_code == 422)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        params={"toolName": "tshark"},
        payload={"configuration": {"TOTALLY_WRONG_VAR": "value"}},
    )
    assert_test("Unknown variable for tshark returns 400 or 422", resp.status_code in (400, 422))

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        params={"toolName": "tshark"},
        payload={"toolName": "tshark", "configuration": {}},
    )
    assert_test(
        "Legacy body with toolName is rejected or ignored safely",
        resp.status_code in (200, 422),
        "If this returns 200, Pydantic is ignoring extra body fields. Use Query param as source of truth.",
    )

    return config_id


def test_deploy_infrastructure_tool(session: requests.Session, base_url: str) -> None:
    print_section("4. POST /ConfigurationManager/DeployInfrastructureTool")

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployInfrastructureTool",
        params={"toolName": "telegraf"},
        payload={"configuration": {"TELEGRAF_GENERAL_INTERVAL": "60s"}},
    )
    assert_test("telegraf with partial config returns 200", resp.status_code == 200)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployInfrastructureTool",
        params={"toolName": "telegraf"},
        payload={"configuration": {}},
    )
    assert_test("telegraf with empty config returns 200", resp.status_code == 200)


def test_deploy_service_tool(session: requests.Session, base_url: str) -> None:
    print_section("5. POST /ConfigurationManager/DeployServiceTool")

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployServiceTool",
        params={"toolName": "fluentd"},
        payload={"configuration": {}},
    )
    assert_test("fluentd with defaults returns 200", resp.status_code == 200)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployServiceTool",
        params={"toolName": "falco"},
        payload={"configuration": {}},
    )
    assert_test("falco with defaults returns 200", resp.status_code == 200)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployServiceTool",
        params={"toolName": "falco"},
        payload={"configuration": {"FALCO_EXPORTER_PORT": "9377"}},
    )
    assert_test("falco with one override returns 200", resp.status_code == 200)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployServiceTool",
        params={"toolName": "snort3"},
        payload={"configuration": {}},
    )
    assert_test("snort3 in DeployServiceTool returns 400", resp.status_code == 400)


def test_deploy_security_tool(session: requests.Session, base_url: str) -> None:
    print_section("6. POST /ConfigurationManager/DeploySecurityTool")

    # Snort3 processes traffic from the traces generated by tshark. That is why tshark is deployed first via DeployNetworkTool.
    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        params={"toolName": "tshark"},
        payload={"configuration": {"TSHARK_BASE_TOPIC": "tshark_traces"}},
    )
    assert_test("tshark dependency for snort3 returns 200", resp.status_code == 200)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeploySecurityTool",
        params={"toolName": "snort3"},
        payload={"configuration": {"SNORT_KAFKA_TOPIC_OUT": "my_alerts"}},
    )
    assert_test("snort3 with partial config returns 200", resp.status_code == 200)

    # Restauramos topic de salida por defecto en una segunda prueba
    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeploySecurityTool",
        params={"toolName": "snort3"},
        payload={"configuration": {}},
    )
    assert_test("snort3 with empty config returns 200", resp.status_code == 200)


def test_get_configuration(session: requests.Session, base_url: str, config_id: Optional[str]) -> None:
    print_section("7. GET /ConfigurationManager/getConfiguration")

    if config_id is None:
        print("  ⚠️  Skipping: no config_id available from previous deploy test.")
        return

    resp = call(
        session,
        base_url,
        "GET",
        "/ConfigurationManager/getConfiguration",
        params={"config_id": config_id},
    )
    assert_test("getConfiguration with valid id returns 200", resp.status_code == 200)
    data = resp.json()
    assert_test("Response contains data field", "data" in data)
    assert_test("data contains tools field", "tools" in data.get("data", {}))

    resp = call(
        session,
        base_url,
        "GET",
        "/ConfigurationManager/getConfiguration",
        params={"config_id": "nonexistentid12345"},
    )
    assert_test("getConfiguration with unknown id returns 404", resp.status_code == 404)


def test_update_configuration(
    session: requests.Session,
    base_url: str,
    config_id: Optional[str],
) -> None:
    print_section("8. PUT /ConfigurationManager/updateConfiguration")

    if config_id is None:
        print("  ⚠️  Skipping: no config_id available from previous deploy test.")
        return

    payload = {
        "config_id": config_id,
        "configuration": {"TSHARK_BASE_TOPIC": "updated_topic"},
    }
    resp = call(
        session,
        base_url,
        "PUT",
        "/ConfigurationManager/updateConfiguration",
        params={"toolName": "tshark"},
        payload=payload,
    )
    assert_test("updateConfiguration returns 200", resp.status_code == 200)
    data = resp.json()
    assert_test("Response contains new_config_id", "new_config_id" in data)
    assert_test("old_config_id matches what we sent", data.get("old_config_id") == config_id)

    payload_bad = {
        "config_id": "doesnotexist000",
        "configuration": {},
    }
    resp = call(
        session,
        base_url,
        "PUT",
        "/ConfigurationManager/updateConfiguration",
        params={"toolName": "tshark"},
        payload=payload_bad,
    )
    assert_test("updateConfiguration with unknown id returns 400", resp.status_code == 400)

    resp = call(
        session,
        base_url,
        "PUT",
        "/ConfigurationManager/updateConfiguration",
        payload={"config_id": config_id, "configuration": {}},
    )
    assert_test("updateConfiguration missing toolName returns 422", resp.status_code == 422)


def main() -> None:
    parser = argparse.ArgumentParser(description="Integration tests for the Configuration Manager API")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the running API (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    base_url = args.base_url
    session = requests.Session()

    print(f"\n🧪 Running tests against: {base_url}\n")

    test_health(session, base_url)
    test_get_configuration_options(session, base_url)
    config_id = test_deploy_network_tool(session, base_url)
    test_deploy_infrastructure_tool(session, base_url)
    test_deploy_service_tool(session, base_url)
    test_deploy_security_tool(session, base_url)
    test_get_configuration(session, base_url, config_id)
    test_update_configuration(session, base_url, config_id)

    print_section("SUMMARY")
    total = passed + failed
    print(f"  Total:  {total}")
    print(f"  Passed: {passed} ✅")
    print(f"  Failed: {failed} ❌")
    print()

    if failed > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()