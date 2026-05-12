import { NextRequest, NextResponse } from "next/server";

const SUPPORTED_TOOLS = new Set(["snort3", "flow_module"]);

function getToolDisplayName(toolName: string): string {
  return toolName === "snort3" ? "Snort3" : toolName === "flow_module" ? "Flow" : toolName;
}

function getBackendBaseUrl() {
  return process.env.EXTERNAL_API_BASE_URL?.replace(/\/$/, "");
}

function parseJsonSafely(text: string) {
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function getBackendErrorMessage(payload: unknown, fallback: string) {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }

  if (
    typeof payload === "object" &&
    payload !== null &&
    "message" in payload &&
    typeof payload.message === "string"
  ) {
    return payload.message;
  }

  if (
    typeof payload === "object" &&
    payload !== null &&
    "error" in payload &&
    typeof payload.error === "string"
  ) {
    return payload.error;
  }

  return fallback;
}

export async function GET(request: NextRequest) {
  const toolName = request.nextUrl.searchParams.get("toolName")?.trim();

  if (!toolName) {
    return NextResponse.json(
      { status: "error", message: "Missing toolName query parameter." },
      { status: 400 },
    );
  }

  if (!SUPPORTED_TOOLS.has(toolName)) {
    return NextResponse.json(
      {
        status: "error",
        message: "Dependency checks are currently implemented for snort3 only.",
      },
      { status: 400 },
    );
  }

  const backendBaseUrl = getBackendBaseUrl();
  if (!backendBaseUrl) {
    return NextResponse.json(
      {
        status: "error",
        message: "EXTERNAL_API_BASE_URL is not configured in the GUI environment.",
      },
      { status: 500 },
    );
  }

  const topicsUrl = new URL(
    `${backendBaseUrl}/ConfigurationManager/getKafkaTopicsState`,
  );
  const runtimeUrl = new URL(
    `${backendBaseUrl}/ConfigurationManager/getToolRuntimeState`,
  );
  runtimeUrl.searchParams.set("toolName", "tshark");

  try {
    const [topicsResponse, runtimeResponse] = await Promise.all([
      fetch(topicsUrl.toString(), {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
        cache: "no-store",
      }),
      fetch(runtimeUrl.toString(), {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
        cache: "no-store",
      }),
    ]);

    const [topicsText, runtimeText] = await Promise.all([
      topicsResponse.text(),
      runtimeResponse.text(),
    ]);
    const topicsPayload = parseJsonSafely(topicsText);
    const runtimePayload = parseJsonSafely(runtimeText);

    if (!runtimeResponse.ok) {
      return NextResponse.json(
        {
          status: "error",
          message: getBackendErrorMessage(
            runtimePayload,
            `Configuration Manager returned HTTP ${runtimeResponse.status} while checking tshark runtime state.`,
          ),
        },
        { status: runtimeResponse.status },
      );
    }

    if (topicsResponse.status === 404) {
      const runtimeStatus =
        runtimePayload &&
        typeof runtimePayload === "object" &&
        "runtime_status" in runtimePayload &&
        typeof runtimePayload.runtime_status === "string"
          ? runtimePayload.runtime_status
          : "unknown";
      const tsharkActive =
        runtimePayload &&
        typeof runtimePayload === "object" &&
        "is_active" in runtimePayload &&
        typeof runtimePayload.is_active === "boolean"
          ? runtimePayload.is_active
          : false;

      return NextResponse.json(
        {
          status: "not_ready",
          toolName,
          dependencyReady: false,
          tsharkActive,
          tsharkRuntimeStatus: runtimeStatus,
          message: tsharkActive
            ? getBackendErrorMessage(
                topicsPayload,
                "Tshark is active, but no producer topics are available in MongoDB CM yet.",
              )
            : "Tshark is not active. Deploy tshark first.",
          topics: {},
        },
        { status: 200 },
      );
    }

    if (!topicsResponse.ok) {
      return NextResponse.json(
        {
          status: "error",
          message: getBackendErrorMessage(
            topicsPayload,
            `Configuration Manager returned HTTP ${topicsResponse.status}.`,
          ),
        },
        { status: topicsResponse.status },
      );
    }

    const topics =
      topicsPayload &&
      typeof topicsPayload === "object" &&
      "topics" in topicsPayload &&
      typeof topicsPayload.topics === "object" &&
      topicsPayload.topics !== null
        ? (topicsPayload.topics as Record<string, string>)
        : {};
    const tsharkRuntimeStatus =
      runtimePayload &&
      typeof runtimePayload === "object" &&
      "runtime_status" in runtimePayload &&
      typeof runtimePayload.runtime_status === "string"
        ? runtimePayload.runtime_status
        : "unknown";
    const tsharkActive =
      runtimePayload &&
      typeof runtimePayload === "object" &&
      "is_active" in runtimePayload &&
      typeof runtimePayload.is_active === "boolean"
        ? runtimePayload.is_active
        : false;

    const tsharkTopic = topics.TSHARK_BASE_TOPIC?.trim();
    const dependencyReady = Boolean(tsharkTopic) && tsharkActive;

    let message = `${getToolDisplayName(toolName)} is not active. Deploy tshark first.`;
    if (tsharkActive && tsharkTopic) {
      message = `Detected active tshark with topic "${tsharkTopic}". ${getToolDisplayName(toolName)} can use it as input.`;
    } else if (tsharkActive) {
      message =
        `Tshark is active, but its topic is not available in MongoDB CM yet.`;
    } else if (tsharkTopic) {
      message =
        `MongoDB CM still stores tshark topic "${tsharkTopic}", but the tshark container is not active. Deploy tshark first.`;
    }

    return NextResponse.json(
      {
        status: dependencyReady ? "success" : "not_ready",
        toolName,
        dependencyReady,
        tsharkActive,
        tsharkRuntimeStatus,
        message,
        topics,
      },
      { status: 200 },
    );
  } catch (error) {
    return NextResponse.json(
      {
        status: "error",
        message: getBackendErrorMessage(
          error,
          "Could not reach Configuration Manager from the GUI backend.",
        ),
      },
      { status: 502 },
    );
  }
}
