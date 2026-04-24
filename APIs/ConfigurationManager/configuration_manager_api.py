"""
configuration_manager_api.py  (v3)

FastAPI application for the Configuration Manager.
This file only handles HTTP routing and request/response formatting.
All business logic is delegated to configuration_manager_logic.py.

Changes from v2:
- toolName is now a query parameter in all deploy endpoints, not inside the JSON body.
- Each deploy endpoint accepts exactly one tool per request.
- The JSON body only contains the optional 'configuration' dict with env var overrides.

Launch with:
    uvicorn configuration_manager_api:app --host 0.0.0.0 --port 8000
Or with whole path:
    uvicorn --app-dir APIs/ConfigurationManager configuration_manager_api:app --port 8000 --host 0.0.0.0
Or directly with Python:
    python3 configuration_manager_api.py --port 9000 --reload

Example request:
    POST /ConfigurationManager/DeployNetworkTool?toolName=tshark
    Body: {"configuration": {"TSHARK_BASE_TOPIC": "my_topic"}}

    POST /ConfigurationManager/DeployNetworkTool?toolName=tshark
    Body: {}
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from configuration_manager_logic import (
    DeployRequest,
    UpdateConfigurationRequest,
    get_configuration_options,
    get_configuration_by_id,
    process_deploy_request,
    process_update_configuration,
)

app = FastAPI(
    title="Configuration Manager API",
    description=(
        "API for deploying and configuring PMP monitoring tools. "
        "Supports network, infrastructure, service and security tool deployment. "
        "toolName is passed as a query parameter; the JSON body carries only env var overrides."
    ),
    version="3.0.0",
)

# ---------------------------------------------------------------------------
# Valid tool names per endpoint
# ---------------------------------------------------------------------------
NETWORK_TOOLS        = ["tshark", "flow_module"]
INFRASTRUCTURE_TOOLS = ["telegraf"]
SERVICE_TOOLS        = ["fluentd", "falco"]
SECURITY_TOOLS       = ["snort3"]


@app.get("/")
async def root():
    """
    Health check endpoint. Returns API status and version.
    """
    return {
        "message":          "Configuration Manager API is running",
        "version":          "3.0.0",
        "kafka_bootstrap":  "kafka_robust6g-node1.lan:9094",
    }


@app.post("/ConfigurationManager/DeployNetworkTool")
async def deploy_network_tool(
    toolName: str = Query(..., description="Name of the network tool to deploy. Valid values: tshark, flow_module"),
    request: DeployRequest = None
):
    """
    Deploy a network monitoring tool (tshark or flow_module).

    - toolName: query parameter with the tool to deploy.
    - Body: optional JSON with env var overrides. Send {} or omit body to use all defaults.

    Examples:
        POST /ConfigurationManager/DeployNetworkTool?toolName=tshark
        Body: {}

        POST /ConfigurationManager/DeployNetworkTool?toolName=tshark
        Body: {"configuration": {"TSHARK_BASE_TOPIC": "my_topic"}}
    """
    if request is None:
        request = DeployRequest()

    result = process_deploy_request(
        tool_name=toolName,
        request=request,
        endpoint="DeployNetworkTool",
        allowed_tool_names=NETWORK_TOOLS
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return JSONResponse(status_code=200, content=result)


@app.post("/ConfigurationManager/DeployInfrastructureTool")
async def deploy_infrastructure_tool(
    toolName: str = Query(..., description="Name of the infrastructure tool to deploy. Valid values: telegraf"),
    request: DeployRequest = None
):
    """
    Deploy an infrastructure monitoring tool (telegraf).

    - toolName: query parameter with the tool to deploy.
    - Body: optional JSON with env var overrides. Send {} or omit body to use all defaults.

    Example:
        POST /ConfigurationManager/DeployInfrastructureTool?toolName=telegraf
        Body: {"configuration": {"TELEGRAF_GENERAL_INTERVAL": "60s"}}
    """
    if request is None:
        request = DeployRequest()

    result = process_deploy_request(
        tool_name=toolName,
        request=request,
        endpoint="DeployInfrastructureTool",
        allowed_tool_names=INFRASTRUCTURE_TOOLS
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return JSONResponse(status_code=200, content=result)


@app.post("/ConfigurationManager/DeployServiceTool")
async def deploy_service_tool(
    toolName: str = Query(..., description="Name of the service tool to deploy. Valid values: fluentd, falco"),
    request: DeployRequest = None
):
    """
    Deploy a service monitoring tool (fluentd or falco).

    - toolName: query parameter with the tool to deploy.
    - Body: optional JSON with env var overrides. Send {} or omit body to use all defaults.

    Example:
        POST /ConfigurationManager/DeployServiceTool?toolName=falco
        Body: {"configuration": {"FALCO_EXPORTER_PORT": "9377"}}
    """
    if request is None:
        request = DeployRequest()

    result = process_deploy_request(
        tool_name=toolName,
        request=request,
        endpoint="DeployServiceTool",
        allowed_tool_names=SERVICE_TOOLS
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return JSONResponse(status_code=200, content=result)


@app.post("/ConfigurationManager/DeploySecurityTool")
async def deploy_security_tool(
    toolName: str = Query(..., description="Name of the security tool to deploy. Valid values: snort3"),
    request: DeployRequest = None
):
    """
    Deploy a security tool (snort3).

    - toolName: query parameter with the tool to deploy.
    - Body: optional JSON with env var overrides. Send {} or omit body to use all defaults.

    Example:
        POST /ConfigurationManager/DeploySecurityTool?toolName=snort3
        Body: {"configuration": {"SNORT_KAFKA_TOPIC_OUT": "my_alerts"}}
    """
    if request is None:
        request = DeployRequest()

    result = process_deploy_request(
        tool_name=toolName,
        request=request,
        endpoint="DeploySecurityTool",
        allowed_tool_names=SECURITY_TOOLS
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return JSONResponse(status_code=200, content=result)


@app.get("/ConfigurationManager/getConfigurationOptions")
async def get_configuration_options_endpoint(
    toolName: str = Query(..., description="Name of the tool to query options for.")
):
    """
    Return all configurable environment variables for a given tool with their default values.
    Defaults are read directly from the Pydantic model for that tool.

    Example: GET /ConfigurationManager/getConfigurationOptions?toolName=tshark
    """
    result = get_configuration_options(toolName)

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result["message"])

    return JSONResponse(status_code=200, content=result)


@app.get("/ConfigurationManager/getConfiguration")
async def get_configuration_endpoint(
    config_id: str = Query(..., description="The config_id hash returned by a previous deploy call.")
):
    """
    Retrieve a stored deployment configuration from MongoDB by its config_id.

    Example: GET /ConfigurationManager/getConfiguration?config_id=<hash>
    """
    result = get_configuration_by_id(config_id)

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result["message"])

    return JSONResponse(status_code=200, content=result)


@app.put("/ConfigurationManager/updateConfiguration")
async def update_configuration_endpoint(
    toolName: str = Query(..., description="Name of the tool to update."),
    request: UpdateConfigurationRequest = None
):
    """
    Update an existing deployment configuration identified by config_id.
    Retrieves the stored configuration, merges the new values, and redeploys.
    Only the variables explicitly sent are overridden; the rest keep their stored values.

    - toolName: query parameter indicating which tool's config model to use for validation.
    - Body: JSON with config_id and optional configuration overrides.

    Example:
        PUT /ConfigurationManager/updateConfiguration?toolName=tshark
        Body: {"config_id": "<hash>", "configuration": {"TSHARK_BASE_TOPIC": "new_topic"}}
    """
    if request is None:
        raise HTTPException(status_code=422, detail="Request body with config_id is required.")

    result = process_update_configuration(
        tool_name=toolName,
        request=request
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return JSONResponse(status_code=200, content=result)


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Configuration Manager API server")
    parser.add_argument("--host",   default="0.0.0.0",      help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port",   type=int, default=8000,  help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true",     help="Enable auto-reload on file changes")
    args = parser.parse_args()

    uvicorn.run(
        "configuration_manager_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )
