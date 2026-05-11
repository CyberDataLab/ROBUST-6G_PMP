import { NextResponse } from "next/server";
import {
  isSupportedToolName,
  SUPPORTED_TOOLS_MESSAGE,
} from "../toolSupport";

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

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function PUT(request: Request) {
  const body = await request.json().catch(() => null);

  if (!isPlainObject(body)) {
    return NextResponse.json(
      { status: "error", message: "Request body must be a JSON object." },
      { status: 400 },
    );
  }

  const toolName =
    typeof body.toolName === "string" ? body.toolName.trim() : "";
  const configId =
    typeof body.config_id === "string" ? body.config_id.trim() : "";

  if (!toolName) {
    return NextResponse.json(
      { status: "error", message: "toolName is required." },
      { status: 400 },
    );
  }

  if (!isSupportedToolName(toolName)) {
    return NextResponse.json(
      {
        status: "error",
        message: SUPPORTED_TOOLS_MESSAGE,
      },
      { status: 400 },
    );
  }

  if (!configId) {
    return NextResponse.json(
      { status: "error", message: "config_id is required." },
      { status: 400 },
    );
  }

  const configuration = body.configuration;
  if (!isPlainObject(configuration)) {
    return NextResponse.json(
      {
        status: "error",
        message: "configuration must be an object of environment variable overrides.",
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

  const backendPayload: Record<string, unknown> = {
    config_id: configId,
    configuration,
  };

  if (toolName === "snort3") {
    if (body.rules_action !== undefined) {
      const rulesAction =
        typeof body.rules_action === "string" ? body.rules_action.trim() : "";
      if (!["add", "remove", "replace"].includes(rulesAction)) {
        return NextResponse.json(
          {
            status: "error",
            message: "rules_action must be add, remove, or replace when provided.",
          },
          { status: 400 },
        );
      }
      backendPayload.rules_action = rulesAction;
    }

    if (body.rules !== undefined) {
      if (
        !Array.isArray(body.rules) ||
        body.rules.some((rule) => typeof rule !== "string")
      ) {
        return NextResponse.json(
          {
            status: "error",
            message: "rules must be an array of strings when provided.",
          },
          { status: 400 },
        );
      }

      backendPayload.rules = body.rules;
    }

    if (body.rule_sids !== undefined) {
      if (
        !Array.isArray(body.rule_sids) ||
        body.rule_sids.some((sid) => typeof sid !== "string")
      ) {
        return NextResponse.json(
          {
            status: "error",
            message: "rule_sids must be an array of strings when provided.",
          },
          { status: 400 },
        );
      }

      backendPayload.rule_sids = body.rule_sids;
    }

    if (body.include_default_rules !== undefined) {
      if (typeof body.include_default_rules !== "boolean") {
        return NextResponse.json(
          {
            status: "error",
            message: "include_default_rules must be a boolean when provided.",
          },
          { status: 400 },
        );
      }

      backendPayload.include_default_rules = body.include_default_rules;
    }
  }

  const backendUrl = new URL(
    `${backendBaseUrl}/ConfigurationManager/updateConfiguration`,
  );
  backendUrl.searchParams.set("toolName", toolName);

  try {
    const backendResponse = await fetch(backendUrl.toString(), {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(backendPayload),
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
