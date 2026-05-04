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
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple

import requests


passed = 0
failed = 0

RULES_DIR = Path(__file__).resolve().parents[1] / "Alert_Module" / "Configuration_Files" / "Rules"
CUSTOM_RULES_TMP_PATH = RULES_DIR / "snort3_custom.tmp.rules"
CUSTOM_RULES_FINAL_PATH = RULES_DIR / "snort3_custom.rules"


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
    timeout: float = 120.0,
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


def test_deploy_network_tool(
    session: requests.Session,
    base_url: str,
    include_flow_module: bool = True,
) -> Tuple[Optional[str], Optional[str]]:
    print_section("3. POST /ConfigurationManager/DeployNetworkTool")

    config_id = None
    flow_config_id = None

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        params={"toolName": "tshark"},
        payload={"configuration": {"TSHARK_BASE_TOPIC": "initial_topic", "TSHARK_INTERFACE": "enp0s3"}},
    )
    assert_test("tshark with initial custom config returns 200", resp.status_code == 200)
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

    if include_flow_module:
        resp = call(
            session,
            base_url,
            "POST",
            "/ConfigurationManager/DeployNetworkTool",
            params={"toolName": "flow_module"},
            payload={"configuration": {}},
        )
        assert_test("flow_module with empty config returns 200", resp.status_code == 200)
        data = resp.json()
        if "config_id" in data:
            flow_config_id = data["config_id"]

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
        payload={
            "configuration": {},
            "rules": [
                "alert tcp any any -> any any (msg:\"invalid for tshark deploy\"; sid:10020; rev:1;)"
            ],
            "include_default_rules": True,
        },
    )
    assert_test("Non-snort3 deploy rejects rules contract fields", resp.status_code == 400)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeployNetworkTool",
        params={"toolName": "tshark"},
        payload={"toolName": "tshark", "configuration": {"TSHARK_INTERFACE": "enp0s3", "TSHARK_BASE_TOPIC": "another_topic"}}, #
    )
    assert_test(
        "Legacy body with toolName is rejected or ignored safely",
        resp.status_code in (200, 422),
        "If this returns 200, Pydantic is ignoring extra body fields. Use Query param as source of truth.",
    )

    if include_flow_module:
        resp = call(
            session,
            base_url,
            "POST",
            "/ConfigurationManager/DeployNetworkTool",
            params={"toolName": "flow_module"},
            payload={"configuration": {}},
        )
        assert_test("flow_module with empty config returns 200", resp.status_code == 200)
        data = resp.json()
        if "config_id" in data:
            flow_config_id = data["config_id"]

    return config_id, flow_config_id


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
        payload={
            "configuration": {"SNORT_KAFKA_TOPIC_OUT": "my_alerts"},
            "rules": [
                "alert tcp any any -> any any (msg:\"snort3 test rule\"; sid:1000001; rev:1;)"
            ],
            "include_default_rules": True,
        },
    )
    assert_test("snort3 with partial config returns 200", resp.status_code == 200)
    data = resp.json()
    snort_config_id = data.get("config_id")
    assert_test("snort3 deploy returns config_id", isinstance(snort_config_id, str) and len(snort_config_id) > 0)
    assert_test("snort3 custom tmp rules file is removed after successful validation", not CUSTOM_RULES_TMP_PATH.exists())
    assert_test("snort3 custom final rules file exists after deploy", CUSTOM_RULES_FINAL_PATH.exists())
    if CUSTOM_RULES_FINAL_PATH.exists():
        final_rules_content = CUSTOM_RULES_FINAL_PATH.read_text(encoding="utf-8")
        assert_test("snort3 final rules file contains deployed rule SID", "sid:1000001;" in final_rules_content)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeploySecurityTool",
        params={"toolName": "snort3"},
        payload={
            "rules": [
                "alert tcp any any -> any any (msg:\"snort3 invalid low sid\"; sid:999999; rev:1;)"
            ]
        },
    )
    assert_test("snort3 rejects custom SID below minimum", resp.status_code == 400)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeploySecurityTool",
        params={"toolName": "snort3"},
        payload={
            "rules": [
                "alert tcp any any -> any any (msg:\"snort3 colliding sid\"; sid:17904; rev:1;)"
            ]
        },
    )
    assert_test("snort3 rejects community SID collisions", resp.status_code == 400)

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeploySecurityTool",
        params={"toolName": "snort3"},
        payload={
            "rules": [
                "alert tcp any any -> any any (msg:\"snort3 duplicate sid one\"; sid:1000005; rev:1;)",
                "alert udp any any -> any any (msg:\"snort3 duplicate sid two\"; sid:1000005; rev:1;)"
            ]
        },
    )
    assert_test("snort3 rejects duplicate custom SIDs in the same deploy payload", resp.status_code == 400)

    if CUSTOM_RULES_FINAL_PATH.exists():
        final_rules_before_invalid = CUSTOM_RULES_FINAL_PATH.read_text(encoding="utf-8")
    else:
        final_rules_before_invalid = ""

    resp = call(
        session,
        base_url,
        "POST",
        "/ConfigurationManager/DeploySecurityTool",
        params={"toolName": "snort3"},
        payload={
            "rules": [
                "alert tcp any any -> any any (msg:\"snort3 invalid syntax\"; sid:1000004; rev:1;"
            ]
        },
    )
    assert_test("snort3 rejects invalid rule syntax through validator", resp.status_code == 400)
    assert_test(
        "snort3 validator failure removes tmp rules file",
        not CUSTOM_RULES_TMP_PATH.exists(),
    )
    if CUSTOM_RULES_FINAL_PATH.exists():
        final_rules_after_invalid = CUSTOM_RULES_FINAL_PATH.read_text(encoding="utf-8")
        assert_test(
            "snort3 validator failure does not overwrite final rules file",
            final_rules_after_invalid == final_rules_before_invalid,
        )

    if snort_config_id:
        resp = call(
            session,
            base_url,
            "GET",
            "/ConfigurationManager/getConfiguration",
            params={"config_id": snort_config_id},
        )
        assert_test("getConfiguration for snort3 returns 200", resp.status_code == 200)
        data = resp.json()
        rules_config = data.get("data", {}).get("rules_config", {})
        snort_resolved_env = data.get("data", {}).get("resolved_env", {})
        assert_test("snort3 getConfiguration returns rules_config", "rules_config" in data.get("data", {}))
        assert_test("snort3 include_default_rules is persisted", rules_config.get("include_default_rules") is True)
        assert_test("snort3 custom_rules are persisted", len(rules_config.get("custom_rules", [])) == 1)
        assert_test("snort3 custom_rule_sids are persisted", rules_config.get("custom_rule_sids") == ["1000001"])
        assert_test("snort3 getConfiguration hides SNORT_RULES_PATHS", "SNORT_RULES_PATHS" not in snort_resolved_env)

        resp = call(
            session,
            base_url,
            "PUT",
            "/ConfigurationManager/updateConfiguration",
            params={"toolName": "snort3"},
            payload={
                "config_id": snort_config_id,
                "rules_action": "add",
                "rules": [
                    "alert udp any any -> any any (msg:\"snort3 duplicate existing sid\"; sid:1000001; rev:1;)"
                ],
            },
        )
        assert_test("snort3 add rejects a SID that already exists in current custom rules", resp.status_code == 400)

        resp = call(
            session,
            base_url,
            "PUT",
            "/ConfigurationManager/updateConfiguration",
            params={"toolName": "snort3"},
            payload={
                "config_id": snort_config_id,
                "rules_action": "add",
                "rules": [
                    "alert udp any any -> any any (msg:\"snort3 add invalid include_default_rules\"; sid:1000006; rev:1;)"
                ],
                "include_default_rules": True,
            },
        )
        assert_test("snort3 add rejects include_default_rules in update", resp.status_code == 400)

        resp = call(
            session,
            base_url,
            "PUT",
            "/ConfigurationManager/updateConfiguration",
            params={"toolName": "snort3"},
            payload={
                "config_id": snort_config_id,
                "rules_action": "add",
                "rules": [
                    "alert udp any any -> any any (msg:\"snort3 add rule\"; sid:1000002; rev:1;)"
                ],
            },
        )
        assert_test("snort3 add rules returns 200", resp.status_code == 200)
        assert_test("snort3 tmp rules file is removed after successful add validation", not CUSTOM_RULES_TMP_PATH.exists())

        resp = call(
            session,
            base_url,
            "PUT",
            "/ConfigurationManager/updateConfiguration",
            params={"toolName": "snort3"},
            payload={
                "config_id": snort_config_id,
                "rules_action": "replace",
            },
        )
        assert_test("snort3 replace rejects requests without rules", resp.status_code == 400)

        resp = call(
            session,
            base_url,
            "PUT",
            "/ConfigurationManager/updateConfiguration",
            params={"toolName": "snort3"},
            payload={
                "config_id": snort_config_id,
                "rules_action": "replace",
                "rules": [
                    "alert icmp any any -> any any (msg:\"snort3 replace rule\"; sid:1000003; rev:1;)"
                ],
                "include_default_rules": False,
            },
        )
        assert_test("snort3 replace rules returns 200", resp.status_code == 200)
        assert_test("snort3 tmp rules file is removed after successful replace validation", not CUSTOM_RULES_TMP_PATH.exists())
        if CUSTOM_RULES_FINAL_PATH.exists():
            final_rules_content = CUSTOM_RULES_FINAL_PATH.read_text(encoding="utf-8")
            assert_test(
                "snort3 replace overwrites final rules file content",
                "sid:1000003;" in final_rules_content and "sid:1000002;" not in final_rules_content,
            )

        resp = call(
            session,
            base_url,
            "PUT",
            "/ConfigurationManager/updateConfiguration",
            params={"toolName": "snort3"},
            payload={
                "config_id": snort_config_id,
                "rules_action": "remove",
                "rule_sids": ["1999999"],
            },
        )
        assert_test("snort3 remove rejects non-existent custom rule SIDs", resp.status_code == 400)

        resp = call(
            session,
            base_url,
            "PUT",
            "/ConfigurationManager/updateConfiguration",
            params={"toolName": "snort3"},
            payload={
                "config_id": snort_config_id,
                "rules_action": "remove",
                "rule_sids": ["1000003"],
            },
        )
        assert_test("snort3 remove rules returns 200", resp.status_code == 200)
        assert_test("snort3 final rules file is deleted when no custom rules remain", not CUSTOM_RULES_FINAL_PATH.exists())
        assert_test("snort3 tmp rules file is deleted when no custom rules remain", not CUSTOM_RULES_TMP_PATH.exists())

        resp = call(
            session,
            base_url,
            "GET",
            "/ConfigurationManager/getConfiguration",
            params={"config_id": snort_config_id},
        )
        assert_test("getConfiguration after snort3 rules updates returns 200", resp.status_code == 200)
        data = resp.json()
        rules_config = data.get("data", {}).get("rules_config", {})
        assert_test("snort3 replace updated include_default_rules", rules_config.get("include_default_rules") is False)
        assert_test("snort3 remove leaves no custom rules", rules_config.get("custom_rules") == [])
        assert_test("snort3 remove leaves no custom_rule_sids", rules_config.get("custom_rule_sids") == [])
'''
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

'''
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
    assert_test("data contains resolved_env field", "resolved_env" in data.get("data", {}))
    assert_test("data contains revision field", "revision" in data.get("data", {}))
    assert_test("data contains current_version_hash field", "current_version_hash" in data.get("data", {}))

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
    flow_config_id: Optional[str],
) -> None:
    print_section("8. PUT /ConfigurationManager/updateConfiguration")

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
    assert_test("getConfiguration before update returns 200", resp.status_code == 200)
    data = resp.json()
    previous_revision = data.get("data", {}).get("revision")
    assert_test("Previous revision is present before update", isinstance(previous_revision, int))

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
    assert_test("Response keeps same config_id", data.get("config_id") == config_id)

    resp = call(
        session,
        base_url,
        "GET",
        "/ConfigurationManager/getConfiguration",
        params={"config_id": config_id},
    )
    assert_test("getConfiguration after update returns 200", resp.status_code == 200)
    data = resp.json()
    resolved_env = data.get("data", {}).get("resolved_env", {})
    revision = data.get("data", {}).get("revision")
    current_version_hash = data.get("data", {}).get("current_version_hash")
    assert_test("Updated topic is persisted", resolved_env.get("TSHARK_BASE_TOPIC") == "updated_topic")
    assert_test(
        "Non-updated fields are preserved",
        resolved_env.get("TSHARK_INTERFACE") == "enp0s3",
    )
    if isinstance(previous_revision, int):
        assert_test("Revision increments after update", revision == previous_revision + 1)
    else:
        assert_test("Revision increments after update", False, "Previous revision was not available as an integer.")
    assert_test("current_version_hash is present after update", isinstance(current_version_hash, str) and len(current_version_hash) > 0)

    if flow_config_id:
        resp = call(
            session,
            base_url,
            "PUT",
            "/ConfigurationManager/updateConfiguration",
            params={"toolName": "flow_module"},
            payload={
                "config_id": flow_config_id,
                "configuration": {"TSHARK_BASE_TOPIC": "updated_topic"},
            },
        )
        assert_test("flow_module update after tshark update returns 200", resp.status_code == 200)
        data = resp.json()
        assert_test("flow_module update keeps same config_id", data.get("config_id") == flow_config_id)

        resp = call(
            session,
            base_url,
            "GET",
            "/ConfigurationManager/getConfiguration",
            params={"config_id": flow_config_id},
        )
        assert_test("getConfiguration for updated flow_module returns 200", resp.status_code == 200)
        data = resp.json()
        flow_resolved_env = data.get("data", {}).get("resolved_env", {})
        assert_test(
            "Updated flow_module picks updated tshark topic",
            flow_resolved_env.get("TSHARK_BASE_TOPIC") == "updated_topic",
        )

    resp = call(
        session,
        base_url,
        "PUT",
        "/ConfigurationManager/updateConfiguration",
        params={"toolName": "tshark"},
        payload={
            "config_id": config_id,
            "rules_action": "add",
            "rules": [
                "alert tcp any any -> any any (msg:\"invalid for tshark\"; sid:10010; rev:1;)"
            ],
        },
    )
    assert_test("Non-snort3 tool rejects rules contract fields", resp.status_code == 400)

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
        params={"toolName": "snort3"},
        payload={"config_id": config_id, "configuration": {"SNORT_KAFKA_TOPIC_OUT": "oops"}},
    )
    assert_test("updateConfiguration with tool mismatch returns 400", resp.status_code == 400)

    resp = call(
        session,
        base_url,
        "PUT",
        "/ConfigurationManager/updateConfiguration",
        params={"toolName": "tshark"},
        payload={"config_id": config_id, "configuration": {}},
    )
    assert_test("updateConfiguration with empty configuration returns 400", resp.status_code == 400)

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
    parser.add_argument(
        "--with-flow-module",
        action="store_true",
        help="Also deploy and update flow_module during the test run.",
    )
    args = parser.parse_args()

    base_url = args.base_url
    session = requests.Session()

    print(f"\n🧪 Running tests against: {base_url}\n")

    #test_health(session, base_url)
    #test_get_configuration_options(session, base_url)
    #config_id, flow_config_id = test_deploy_network_tool(
    #    session,
    #    base_url,
    #    include_flow_module=args.with_flow_module,
    #)
    #test_deploy_infrastructure_tool(session, base_url)
    #test_deploy_service_tool(session, base_url)
    #test_get_configuration(session, base_url, config_id)
    #test_update_configuration(session, base_url, config_id, flow_config_id)
    test_deploy_security_tool(session, base_url)

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
