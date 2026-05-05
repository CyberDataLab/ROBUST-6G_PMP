import { NextRequest, NextResponse } from "next/server";

const SUPPORTED_TOOLS = new Set(["tshark", "snort3"]);

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
        message: "This proof of concept currently supports tshark and snort3.",
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

  const backendUrl = new URL(
    `${backendBaseUrl}/ConfigurationManager/getConfigurationOptions`,
  );
  backendUrl.searchParams.set("toolName", toolName);

  try {
    const backendResponse = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
    });
    const backendText = await backendResponse.text();
    const payload = parseJsonSafely(backendText);

    if (!backendResponse.ok) {
      return NextResponse.json(
        {
          status: "error",
          message: getBackendErrorMessage(
            payload,
            `Configuration Manager returned HTTP ${backendResponse.status}.`,
          ),
        },
        { status: backendResponse.status },
      );
    }

    return NextResponse.json(payload, { status: backendResponse.status });
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
