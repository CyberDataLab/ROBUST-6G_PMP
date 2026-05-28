import { NextRequest, NextResponse } from "next/server";

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
  const jobId = request.nextUrl.searchParams.get("job_id")?.trim();

  if (!jobId) {
    return NextResponse.json(
      { status: "error", message: "Missing job_id query parameter." },
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
    `${backendBaseUrl}/ConfigurationManager/internal/jobs/${encodeURIComponent(jobId)}`,
  );

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
