"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import {
  Users,
  Shield,
  Activity,
  AlertTriangle,
  Monitor,
  UserPlus,
  Server,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  CheckCircle,
  XCircle,
  ChevronRight,
  Settings,
  ToggleLeft,
  ToggleRight,
  Eye,
  Wrench,
  BarChart3,
  Network,
  Lock,
  FileSearch,
  Layers,
  Cpu,
  Check,
} from "lucide-react";

type JsonPrimitive = string | number | boolean;
type JsonValue = JsonPrimitive | JsonObject;
type JsonObject = {
  [key: string]: JsonValue;
};
type ToolApiName =
  | "tshark"
  | "flow_module"
  | "telegraf"
  | "fluentd"
  | "falco"
  | "snort3";
type ConfigurableVariable = {
  name: string;
  default_value?: JsonPrimitive | null;
};
type EditorMode = "deploy" | "update";
type SnortRulesAction = "" | "add" | "replace" | "remove";
type ToolDependencyStatus =
  | "idle"
  | "checking"
  | "ready"
  | "not_ready"
  | "error";
type DeployPayload = {
  toolName: ToolApiName;
  configuration: JsonObject;
  rules?: string[];
  include_default_rules?: boolean;
};
type UpdatePayload = {
  toolName: ToolApiName;
  config_id: string;
  configuration: JsonObject;
  rules_action?: "add" | "remove" | "replace";
  rules?: string[];
  rule_sids?: string[];
  include_default_rules?: boolean;
};

const TOOL_NAME_TO_API_NAME: Record<string, ToolApiName | undefined> = {
  Tshark: "tshark",
  Flow: "flow_module",
  Telegraf: "telegraf",
  Fluentd: "fluentd",
  Falco: "falco",
  Snort: "snort3",
};

const SUPPORTED_TOOLS_MESSAGE =
  "This proof of concept currently supports Tshark, Snort, Flow, Telegraf, Fluentd, and Falco.";

const TOOL_OPTIONS_BY_POSTURE: Record<string, string[]> = {
  "Network Security Posture": ["Tshark", "Snort", "Flow"],
  "Infrastructure Security Posture": ["Telegraf"],
  "Service Security Posture": ["Fluentd", "Falco"],
};

function formatJsonLabel(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getApiToolName(toolLabel: string): ToolApiName | undefined {
  return TOOL_NAME_TO_API_NAME[toolLabel];
}

function getErrorMessage(error: unknown, fallback: string) {
  if (
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof error.message === "string"
  ) {
    const normalizedMessage = error.message.trim();

    if (
      normalizedMessage.includes("NetworkError when attempting to fetch resource") ||
      normalizedMessage.includes("Failed to fetch")
    ) {
      return "The GUI could not complete the request because the web client lost connection to the GUI/backend momentarily. If services were restarting, wait a few seconds and retry.";
    }

    return error.message;
  }

  if (
    typeof error === "object" &&
    error !== null &&
    "detail" in error &&
    typeof error.detail === "string"
  ) {
    return error.detail;
  }

  if (
    typeof error === "object" &&
    error !== null &&
    "error" in error &&
    typeof error.error === "string"
  ) {
    return error.error;
  }

  return fallback;
}

function isBrowserTransportError(error: unknown) {
  return (
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof error.message === "string" &&
    (error.message.includes("NetworkError when attempting to fetch resource") ||
      error.message.includes("Failed to fetch"))
  );
}

function parseSnortRulesInput(rulesInput: string) {
  return rulesInput
    .split(/\r?\n/)
    .map((rule) => rule.trim())
    .filter(Boolean);
}

function parseCommaSeparatedInput(input: string) {
  return input
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function buildDeployPayload(
  toolName: ToolApiName,
  configuration: JsonObject,
  snortRulesInput: string,
  includeDefaultRules: boolean,
): DeployPayload {
  const payload: DeployPayload = {
    toolName,
    configuration,
  };

  if (toolName !== "snort3") {
    return payload;
  }

  const parsedRules = parseSnortRulesInput(snortRulesInput);

  if (parsedRules.length > 0) {
    payload.rules = parsedRules;
    payload.include_default_rules = includeDefaultRules;
  }

  return payload;
}

function buildDraftConfigFromVariables(
  variables: ConfigurableVariable[],
): JsonObject {
  return variables.reduce<JsonObject>((config, variable) => {
    config[variable.name] =
      variable.default_value === null || variable.default_value === undefined
        ? ""
        : variable.default_value;

    return config;
  }, {});
}

function buildDraftConfigFromResolvedEnv(
  variables: ConfigurableVariable[],
  resolvedEnv: Record<string, unknown>,
): JsonObject {
  const config = buildDraftConfigFromVariables(variables);

  for (const variable of variables) {
    if (variable.name in resolvedEnv) {
      const value = resolvedEnv[variable.name];
      if (
        typeof value === "string" ||
        typeof value === "number" ||
        typeof value === "boolean"
      ) {
        config[variable.name] = value;
      }
    }
  }

  return config;
}

function resolvedEnvMatchesDraftConfig(
  draftConfig: JsonObject,
  resolvedEnv: Record<string, unknown>,
): boolean {
  return Object.entries(draftConfig).every(([key, value]) => {
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      const nestedResolvedEnv =
        typeof resolvedEnv[key] === "object" &&
        resolvedEnv[key] !== null &&
        !Array.isArray(resolvedEnv[key])
          ? (resolvedEnv[key] as Record<string, unknown>)
          : {};

      return resolvedEnvMatchesDraftConfig(value, nestedResolvedEnv);
    }

    return String(resolvedEnv[key] ?? "") === String(value);
  });
}

function snortRulesUpdateMatchesStoredState(
  rulesAction: SnortRulesAction,
  rulesInput: string,
  ruleSidsInput: string,
  includeDefaultRules: boolean,
  storedRulesConfig: Record<string, unknown>,
): boolean {
  if (!rulesAction) {
    return true;
  }

  const storedCustomRules = Array.isArray(storedRulesConfig.custom_rules)
    ? storedRulesConfig.custom_rules.filter(
        (rule): rule is string => typeof rule === "string",
      )
    : [];
  const storedCustomRuleSids = Array.isArray(storedRulesConfig.custom_rule_sids)
    ? storedRulesConfig.custom_rule_sids.filter(
        (sid): sid is string => typeof sid === "string",
      )
    : [];
  const parsedRules = parseSnortRulesInput(rulesInput);
  const parsedRuleSids = parseCommaSeparatedInput(ruleSidsInput);
  const storedIncludeDefaultRules =
    typeof storedRulesConfig.include_default_rules === "boolean"
      ? storedRulesConfig.include_default_rules
      : true;

  if (rulesAction === "add") {
    return parsedRules.every((rule) => storedCustomRules.includes(rule));
  }

  if (rulesAction === "replace") {
    return (
      storedIncludeDefaultRules === includeDefaultRules &&
      storedCustomRules.length === parsedRules.length &&
      storedCustomRules.every((rule, index) => rule === parsedRules[index])
    );
  }

  return parsedRuleSids.every((sid) => !storedCustomRuleSids.includes(sid));
}

// ─── KPI Card ───────────────────────────────────────────────
function KpiCard({
  title,
  value,
  change,
  changeType,
  icon: Icon,
  color,
}: {
  title: string;
  value: string;
  change: string;
  changeType: "up" | "down" | "neutral";
  icon: React.ElementType;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-500/10 text-blue-400",
    green: "bg-green-500/10 text-green-400",
    purple: "bg-purple-500/10 text-purple-400",
    amber: "bg-amber-500/10 text-amber-400",
    cyan: "bg-cyan-500/10 text-cyan-400",
    red: "bg-red-500/10 text-red-400",
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 transition-all hover:border-gray-700">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">{title}</p>
        <div className={`rounded-lg p-2 ${colorMap[color]}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <p className="mt-3 text-3xl font-bold text-white">{value}</p>
      <div className="mt-2 flex items-center gap-1 text-xs">
        {changeType === "up" && (
          <ArrowUpRight className="h-3 w-3 text-green-400" />
        )}
        {changeType === "down" && (
          <ArrowDownRight className="h-3 w-3 text-red-400" />
        )}
        <span
          className={
            changeType === "up"
              ? "text-green-400"
              : changeType === "down"
                ? "text-red-400"
                : "text-gray-500"
          }
        >
          {change}
        </span>
        <span className="text-gray-600">vs last week</span>
      </div>
    </div>
  );
}

// ─── Status Badge ───────────────────────────────────────────
function StatusBadge({
  status,
}: {
  status: "online" | "degraded" | "offline";
}) {
  const config = {
    online: {
      label: "Online",
      className: "bg-green-500/10 text-green-400",
      icon: CheckCircle,
    },
    degraded: {
      label: "Degraded",
      className: "bg-amber-500/10 text-amber-400",
      icon: AlertTriangle,
    },
    offline: {
      label: "Offline",
      className: "bg-red-500/10 text-red-400",
      icon: XCircle,
    },
  };
  const { label, className, icon: Icon } = config[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${className}`}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  );
}

// ─── Toggle Switch (for Admin tool activation) ──────────────
function ToolToggle({
  name,
  description,
  enabled,
  icon: Icon,
}: {
  name: string;
  description: string;
  enabled: boolean;
  icon: React.ElementType;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-4 transition-all hover:border-gray-700">
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-purple-500/10 p-2 text-purple-400">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm font-medium text-white">{name}</p>
          <p className="text-xs text-gray-500">{description}</p>
        </div>
      </div>
      <button
        className={`flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium transition-all ${
          enabled
            ? "bg-green-500/10 text-green-400 hover:bg-green-500/20"
            : "bg-gray-800 text-gray-500 hover:bg-gray-700"
        }`}
      >
        {enabled ? (
          <>
            <ToggleRight className="h-4 w-4" /> Active
          </>
        ) : (
          <>
            <ToggleLeft className="h-4 w-4" /> Inactive
          </>
        )}
      </button>
    </div>
  );
}

function SelectableOptionsBox({
  title,
  description,
  options,
  selectedOption,
  onSelect,
}: {
  title: string;
  description: string;
  options: string[];
  selectedOption: string;
  onSelect: (option: string) => void;
}) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <p className="mt-1 text-sm text-gray-400">{description}</p>
      </div>
      <div className="space-y-3">
        <label
          htmlFor={title}
          className="block text-xs font-medium uppercase tracking-[0.2em] text-gray-500"
        >
          Available options
        </label>
        <div className="relative">
          <select
            id={title}
            value={selectedOption}
            onChange={(event) => onSelect(event.target.value)}
            className="w-full appearance-none rounded-lg border border-gray-800 bg-gray-950/50 px-4 py-3 pr-10 text-sm font-medium text-white outline-none transition-all hover:border-gray-700 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
          >
            {options.map((option) => (
              <option key={option} value={option} className="bg-gray-950">
                {option}
              </option>
            ))}
          </select>
          <ChevronRight className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 rotate-90 text-gray-500" />
        </div>
        <div className="inline-flex items-center gap-1 rounded-full bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-300">
          <Check className="h-3 w-3" />
          Selected: {selectedOption}
        </div>
      </div>
    </div>
  );
}

function MonitoringToolConfigurationBox({
  posture,
  selectedTool,
  draftConfig,
  isLaunchEditorOpen,
  isLoadingConfiguration,
  configurationMessage,
  editorMode,
  loadedConfigId,
  reconfigureConfigId,
  snortRulesInput,
  snortRuleSidsInput,
  snortIncludeDefaultRules,
  snortRulesAction,
  currentSnortRules,
  currentSnortRuleSids,
  toolDependencyStatus,
  toolDependencyMessage,
  onPostureChange,
  onToolChange,
  onDraftFieldChange,
  onReconfigureConfigIdChange,
  onSnortRulesInputChange,
  onSnortRuleSidsInputChange,
  onSnortIncludeDefaultRulesChange,
  onSnortRulesActionChange,
  onLaunchClick,
  onReconfigureClick,
  onLoadCurrentConfigClick,
  onSubmitSuccess,
}: {
  posture: string;
  selectedTool: string;
  draftConfig: JsonObject | null;
  isLaunchEditorOpen: boolean;
  isLoadingConfiguration: boolean;
  configurationMessage: string;
  editorMode: EditorMode;
  loadedConfigId: string | null;
  reconfigureConfigId: string;
  snortRulesInput: string;
  snortRuleSidsInput: string;
  snortIncludeDefaultRules: boolean;
  snortRulesAction: SnortRulesAction;
  currentSnortRules: string[];
  currentSnortRuleSids: string[];
  toolDependencyStatus: ToolDependencyStatus;
  toolDependencyMessage: string;
  onPostureChange: (posture: string) => void;
  onToolChange: (tool: string) => void;
  onDraftFieldChange: (path: string[], value: JsonPrimitive) => void;
  onReconfigureConfigIdChange: (value: string) => void;
  onSnortRulesInputChange: (value: string) => void;
  onSnortRuleSidsInputChange: (value: string) => void;
  onSnortIncludeDefaultRulesChange: (value: boolean) => void;
  onSnortRulesActionChange: (value: SnortRulesAction) => void;
  onLaunchClick: () => void;
  onReconfigureClick: () => void;
  onLoadCurrentConfigClick: () => void;
  onSubmitSuccess: (mode: EditorMode, configId?: string) => void;
}) {
  const availableTools = TOOL_OPTIONS_BY_POSTURE[posture] ?? [];
  const [isDeploying, setIsDeploying] = useState(false);
  const [deployMessage, setDeployMessage] = useState("");
  const selectedApiToolName = getApiToolName(selectedTool);
  const isSupportedInPoc = Boolean(selectedApiToolName);
  const isToolWithDependency = selectedApiToolName === "snort3" || selectedApiToolName === "flow_module";
  const isSnortTool = selectedApiToolName === "snort3";
  const parsedSnortRules = isSnortTool
    ? parseSnortRulesInput(snortRulesInput)
    : [];
  const parsedSnortRuleSids = isSnortTool
    ? parseCommaSeparatedInput(snortRuleSidsInput)
    : [];
  const snortHasCustomRules = parsedSnortRules.length > 0;
  const deployPayload =
    draftConfig && selectedApiToolName
      ? buildDeployPayload(
          selectedApiToolName,
          draftConfig,
          snortRulesInput,
          snortIncludeDefaultRules,
        )
      : null;
  const updatePayload =
    draftConfig && selectedApiToolName && loadedConfigId
      ? (() => {
          const payload: UpdatePayload = {
            toolName: selectedApiToolName,
            config_id: loadedConfigId,
            configuration: draftConfig,
          };

          if (selectedApiToolName === "snort3") {
            if (snortRulesAction === "add") {
              payload.rules_action = "add";
              payload.rules = parsedSnortRules;
            } else if (snortRulesAction === "replace") {
              payload.rules_action = "replace";
              payload.rules = parsedSnortRules;
              payload.include_default_rules = snortIncludeDefaultRules;
            } else if (snortRulesAction === "remove") {
              payload.rules_action = "remove";
              payload.rule_sids = parsedSnortRuleSids;
            }
          }

          return payload;
        })()
      : null;
  const submitPayload = editorMode === "update" ? updatePayload : deployPayload;
  const exportedJson = submitPayload ? JSON.stringify(submitPayload, null, 2) : "";
  const isToolDependencyBlocking =
    isToolWithDependency &&
    (toolDependencyStatus === "checking" ||
      toolDependencyStatus === "not_ready");

  useEffect(() => {
    setDeployMessage("");
  }, [editorMode, loadedConfigId, selectedTool, isLaunchEditorOpen]);

  const handleSubmit = async () => {
    if (!submitPayload || isDeploying || isToolDependencyBlocking) {
      return;
    }

    if (!selectedApiToolName) {
      setDeployMessage(SUPPORTED_TOOLS_MESSAGE);
      return;
    }

    if (editorMode === "update" && !loadedConfigId) {
      setDeployMessage("Load a valid config_id before sending an update.");
      return;
    }

    if (selectedApiToolName === "snort3" && editorMode === "update") {
      if (
        (snortRulesAction === "add" || snortRulesAction === "replace") &&
        parsedSnortRules.length === 0
      ) {
        setDeployMessage(
          `The '${snortRulesAction}' action requires at least one Snort3 custom rule.`,
        );
        return;
      }

      if (snortRulesAction === "remove" && parsedSnortRuleSids.length === 0) {
        setDeployMessage(
          "The 'remove' action requires at least one Snort3 SID separated by commas.",
        );
        return;
      }
    }

    setIsDeploying(true);
    setDeployMessage("");

    try {
      const response = await fetch(
        editorMode === "update"
          ? "/api/configuration-manager/update"
          : "/api/configuration-manager/deploy",
        {
          method: editorMode === "update" ? "PUT" : "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(submitPayload),
        },
      );
      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(
            payload,
            `${editorMode === "update" ? "Update" : "Deploy"} failed with status ${response.status}.`,
          ),
        );
      }

      const configId =
        payload &&
        typeof payload === "object" &&
        "config_id" in payload &&
        typeof payload.config_id === "string"
          ? payload.config_id
          : undefined;

      setDeployMessage(
        editorMode === "update"
          ? configId
            ? `Configuration updated successfully. Config ID: ${configId}`
            : "Configuration updated successfully."
          : configId
            ? `Deploy request sent successfully. Config ID: ${configId}`
            : "Deploy request sent successfully.",
      );
      onSubmitSuccess(editorMode, configId);
    } catch (error) {
      if (
        editorMode === "update" &&
        loadedConfigId &&
        draftConfig &&
        isBrowserTransportError(error)
      ) {
        try {
          const recoveryResponse = await fetch(
            `/api/configuration-manager/configuration?config_id=${encodeURIComponent(loadedConfigId)}`,
            {
              cache: "no-store",
            },
          );
          const recoveryPayload = await recoveryResponse.json().catch(() => null);

          if (recoveryResponse.ok) {
            const recoveryData =
              recoveryPayload &&
              typeof recoveryPayload === "object" &&
              "data" in recoveryPayload &&
              typeof recoveryPayload.data === "object" &&
              recoveryPayload.data !== null
                ? (recoveryPayload.data as Record<string, unknown>)
                : {};
            const recoveryResolvedEnv =
              typeof recoveryData.resolved_env === "object" &&
              recoveryData.resolved_env !== null
                ? (recoveryData.resolved_env as Record<string, unknown>)
                : {};
            const recoveryRulesConfig =
              typeof recoveryData.rules_config === "object" &&
              recoveryData.rules_config !== null
                ? (recoveryData.rules_config as Record<string, unknown>)
                : {};

            const didConfigPersist = resolvedEnvMatchesDraftConfig(
              draftConfig,
              recoveryResolvedEnv,
            );
            const didRulesPersist =
              selectedApiToolName !== "snort3" ||
              snortRulesUpdateMatchesStoredState(
                snortRulesAction,
                snortRulesInput,
                snortRuleSidsInput,
                snortIncludeDefaultRules,
                recoveryRulesConfig,
              );

            if (didConfigPersist && didRulesPersist) {
              setDeployMessage(
                "The browser briefly lost connection before receiving the response, but the stored configuration now reflects the requested update.",
              );
              onSubmitSuccess(editorMode, loadedConfigId);
              return;
            }
          }
        } catch {
          // Ignore recovery errors and fall back to the original message below.
        }
      }

      setDeployMessage(
        getErrorMessage(
          error,
          editorMode === "update"
            ? "Update failed. Check if the backend services are available."
            : "Deploy failed. Check if the backend services are available.",
        ),
      );
    } finally {
      setIsDeploying(false);
    }
  };

  const renderJsonFields = (config: JsonObject, path: string[] = []) =>
    Object.entries(config).map(([key, value]) => {
      const fieldPath = [...path, key];
      const fieldId = `json-field-${fieldPath.join("-")}`;

      if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        return (
          <div
            key={fieldPath.join(".")}
            className="rounded-lg border border-gray-800 bg-[#08101d] p-4"
          >
            <h5 className="mb-3 text-sm font-semibold text-cyan-200">
              {formatJsonLabel(key)}
            </h5>
            <div className="space-y-3">{renderJsonFields(value, fieldPath)}</div>
          </div>
        );
      }

      const inputType = typeof value === "number" ? "number" : "text";

      return (
        <div key={fieldPath.join(".")} className="space-y-2">
          <label
            htmlFor={fieldId}
            className="block text-xs font-medium uppercase tracking-[0.2em] text-cyan-300"
          >
            {formatJsonLabel(key)}
          </label>
          {typeof value === "boolean" ? (
            <select
              id={fieldId}
              value={String(value)}
              onChange={(event) =>
                onDraftFieldChange(fieldPath, event.target.value === "true")
              }
              className="w-full rounded-lg border border-cyan-500/30 bg-white px-4 py-3 text-sm text-black outline-none transition-all focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20"
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : (
            <input
              id={fieldId}
              type={inputType}
              value={String(value)}
              onChange={(event) =>
                onDraftFieldChange(
                  fieldPath,
                  typeof value === "number"
                    ? Number(event.target.value)
                    : event.target.value,
                )
              }
              className="w-full rounded-lg border border-cyan-500/30 bg-white px-4 py-3 text-sm text-black outline-none transition-all focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20"
            />
          )}
        </div>
      );
    });

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-white">
          Monitoring Tool Configuration
        </h3>
        <p className="mt-1 text-sm text-gray-400">
          Select a security posture, then choose the monitoring tool to manage.
        </p>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <label
            htmlFor="monitoring-posture"
            className="block text-xs font-medium uppercase tracking-[0.2em] text-gray-500"
          >
            Security posture
          </label>
          <div className="relative">
            <select
              id="monitoring-posture"
              value={posture}
              onChange={(event) => onPostureChange(event.target.value)}
              className="w-full appearance-none rounded-lg border border-gray-800 bg-gray-950/50 px-4 py-3 pr-10 text-sm font-medium text-black outline-none transition-all hover:border-gray-700 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
            >
              {Object.keys(TOOL_OPTIONS_BY_POSTURE).map((option) => (
                <option key={option} value={option} className="bg-gray-950">
                  {option}
                </option>
              ))}
            </select>
            <ChevronRight className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 rotate-90 text-gray-500" />
          </div>
        </div>

        <div className="space-y-2">
          <label
            htmlFor="monitoring-tool"
            className="block text-xs font-medium uppercase tracking-[0.2em] text-gray-500"
          >
            Monitoring tool
          </label>
          <div className="relative">
            <select
              id="monitoring-tool"
              value={selectedTool}
              onChange={(event) => onToolChange(event.target.value)}
              className="w-full appearance-none rounded-lg border border-gray-800 bg-gray-950/50 px-4 py-3 pr-10 text-sm font-medium text-black outline-none transition-all hover:border-gray-700 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
            >
              <option value="" className="bg-gray-950">
                Select a tool
              </option>
              {availableTools.map((option) => (
                <option key={option} value={option} className="bg-gray-950">
                  {option}
                </option>
              ))}
            </select>
            <ChevronRight className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 rotate-90 text-gray-500" />
          </div>
        </div>

        {selectedTool && (
          <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4">
            <div className="mb-4 inline-flex items-center gap-1 rounded-full bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-300">
              <Check className="h-3 w-3" />
              Selected: {posture} / {selectedTool}
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={onLaunchClick}
                disabled={isLoadingConfiguration || !isSupportedInPoc}
                className="rounded-lg bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-cyan-400 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
              >
                {isLoadingConfiguration ? "Loading Configuration..." : "Launch Service"}
              </button>
              <button
                type="button"
                onClick={onReconfigureClick}
                disabled={isLoadingConfiguration || !isSupportedInPoc}
                className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm font-semibold text-amber-300 transition-colors hover:border-amber-400 hover:bg-amber-400 hover:text-slate-950 disabled:cursor-not-allowed disabled:border-gray-700 disabled:bg-gray-900 disabled:text-gray-500"
              >
                Reconfigure Service
              </button>
            </div>
            {!isSupportedInPoc && (
              <p className="mt-3 text-xs text-amber-300">
                {SUPPORTED_TOOLS_MESSAGE}
              </p>
            )}
            {configurationMessage && (
              <p
                className={`mt-3 text-xs ${
                  draftConfig ? "text-cyan-200" : "text-amber-300"
                }`}
              >
                {configurationMessage}
              </p>
            )}
          </div>
        )}

        {isLaunchEditorOpen && (
          <div className="rounded-lg border border-cyan-500/20 bg-slate-950/70 p-4">
            <div className="mb-3">
              <h4 className="text-sm font-semibold text-white">
                {editorMode === "update"
                  ? "Service Reconfiguration"
                  : "Service Launch Configuration"}
              </h4>
              <p className="mt-1 text-xs text-gray-400">
                {editorMode === "update"
                  ? "Load a stored configuration by config_id and then edit it before sending updateConfiguration."
                  : "Edit the form fields below. The JSON export is rebuilt from the current form values."}
              </p>
            </div>

            {editorMode === "update" && !draftConfig && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <label
                    htmlFor="reconfigure-config-id"
                    className="block text-xs font-medium uppercase tracking-[0.2em] text-cyan-300"
                  >
                    Config ID
                  </label>
                  <input
                    id="reconfigure-config-id"
                    type="text"
                    value={reconfigureConfigId}
                    onChange={(event) =>
                      onReconfigureConfigIdChange(event.target.value)
                    }
                    placeholder="Paste the config_id returned by deploy"
                    className="w-full rounded-lg border border-cyan-500/30 bg-white px-4 py-3 text-sm text-black outline-none transition-all focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20"
                  />
                </div>
                <button
                  type="button"
                  onClick={onLoadCurrentConfigClick}
                  disabled={isLoadingConfiguration}
                  className="rounded-lg bg-amber-400 px-4 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-amber-300 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
                >
                  {isLoadingConfiguration
                    ? "Loading Current Configuration..."
                    : "Load Current Configuration"}
                </button>
              </div>
            )}

            {draftConfig && (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <div className="space-y-3">
                  {editorMode === "update" && loadedConfigId && (
                    <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4">
                      <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyan-300">
                        Loaded Config ID
                      </p>
                      <p className="mt-2 break-all font-mono text-sm text-white">
                        {loadedConfigId}
                      </p>
                    </div>
                  )}

                  {renderJsonFields(draftConfig)}

                  {isSnortTool && (
                    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
                      <div className="mb-3">
                        <h5 className="text-sm font-semibold text-white">
                          {editorMode === "update"
                            ? "Snort3 Rules Update"
                            : "Snort3 Custom Rules"}
                        </h5>
                        <p className="mt-1 text-xs text-gray-400">
                          {editorMode === "update"
                            ? "Current rules are shown below. Select an action only if you want to change the Snort3 rules contract."
                            : "Paste one Snort3 rule per line. The Configuration Manager validator will reject invalid rules and the GUI will surface that error message."}
                        </p>
                      </div>

                      <div
                        className={`mb-4 rounded-lg border px-3 py-2 text-xs ${
                          toolDependencyStatus === "ready"
                            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                            : toolDependencyStatus === "not_ready"
                              ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
                              : toolDependencyStatus === "error"
                                ? "border-red-500/30 bg-red-500/10 text-red-200"
                                : "border-cyan-500/30 bg-cyan-500/10 text-cyan-200"
                        }`}
                      >
                        {toolDependencyMessage ||
                          "Checking whether tshark has already been deployed..."}
                      </div>

                      {editorMode === "update" ? (
                        <div className="space-y-4">
                          <div className="rounded-lg border border-gray-800 bg-[#08101d] p-4">
                            <p className="text-xs font-medium uppercase tracking-[0.2em] text-cyan-300">
                              Current custom rules
                            </p>
                            <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-gray-800 bg-[#0b1120] px-4 py-3 font-mono text-sm text-white">
                              {currentSnortRules.length > 0
                                ? currentSnortRules.join("\n")
                                : "No current custom Snort3 rules."}
                            </pre>
                            <p className="mt-3 text-xs text-gray-400">
                              Current SIDs:{" "}
                              {currentSnortRuleSids.length > 0
                                ? currentSnortRuleSids.join(", ")
                                : "none"}
                            </p>
                          </div>

                          <div className="space-y-2">
                            <label
                              htmlFor="snort3-rules-action"
                              className="block text-xs font-medium uppercase tracking-[0.2em] text-cyan-300"
                            >
                              Rules action
                            </label>
                            <select
                              id="snort3-rules-action"
                              value={snortRulesAction}
                              onChange={(event) =>
                                onSnortRulesActionChange(
                                  event.target.value as SnortRulesAction,
                                )
                              }
                              className="w-full rounded-lg border border-cyan-500/30 bg-white px-4 py-3 text-sm text-black outline-none transition-all focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20"
                            >
                              <option value="">Do not change rules</option>
                              <option value="add">add</option>
                              <option value="replace">replace</option>
                              <option value="remove">remove</option>
                            </select>
                          </div>

                          {(snortRulesAction === "add" ||
                            snortRulesAction === "replace") && (
                            <div className="space-y-2">
                              <label
                                htmlFor="snort3-rules-input"
                                className="block text-xs font-medium uppercase tracking-[0.2em] text-cyan-300"
                              >
                                New custom rules
                              </label>
                              <textarea
                                id="snort3-rules-input"
                                value={snortRulesInput}
                                onChange={(event) =>
                                  onSnortRulesInputChange(event.target.value)
                                }
                                placeholder='alert tcp any any -> any any (msg:"snort3 test rule"; sid:1000001; rev:1;)'
                                spellCheck={false}
                                rows={8}
                                className="w-full rounded-lg border border-cyan-500/30 bg-white px-4 py-3 font-mono text-sm text-black outline-none transition-all focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20"
                              />
                              <p className="text-xs text-gray-400">
                                Write one rule per line. The '{snortRulesAction}'
                                action requires at least one rule.
                              </p>
                            </div>
                          )}

                          {snortRulesAction === "replace" && (
                            <label className="flex items-start gap-3 rounded-lg border border-cyan-500/20 bg-[#08101d] p-3">
                              <input
                                type="checkbox"
                                checked={snortIncludeDefaultRules}
                                onChange={(event) =>
                                  onSnortIncludeDefaultRulesChange(
                                    event.target.checked,
                                  )
                                }
                                className="mt-1 h-4 w-4 rounded border-gray-600"
                              />
                              <div>
                                <p className="text-sm font-medium text-white">
                                  Include default/community Snort3 rules
                                </p>
                                <p className="mt-1 text-xs text-gray-400">
                                  This flag is applied only with the 'replace'
                                  action.
                                </p>
                              </div>
                            </label>
                          )}

                          {snortRulesAction === "remove" && (
                            <div className="space-y-2">
                              <label
                                htmlFor="snort3-rule-sids-input"
                                className="block text-xs font-medium uppercase tracking-[0.2em] text-cyan-300"
                              >
                                Rule SIDs to remove
                              </label>
                              <input
                                id="snort3-rule-sids-input"
                                type="text"
                                value={snortRuleSidsInput}
                                onChange={(event) =>
                                  onSnortRuleSidsInputChange(
                                    event.target.value,
                                  )
                                }
                                placeholder="1000001, 1000002"
                                className="w-full rounded-lg border border-cyan-500/30 bg-white px-4 py-3 font-mono text-sm text-black outline-none transition-all focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20"
                              />
                              <p className="text-xs text-gray-400">
                                Enter one or more current SIDs separated by
                                commas.
                              </p>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="space-y-4">
                          <label className="flex items-start gap-3 rounded-lg border border-cyan-500/20 bg-[#08101d] p-3">
                            <input
                              type="checkbox"
                              checked={
                                snortHasCustomRules
                                  ? snortIncludeDefaultRules
                                  : true
                              }
                              disabled={!snortHasCustomRules}
                              onChange={(event) =>
                                onSnortIncludeDefaultRulesChange(
                                  event.target.checked,
                                )
                              }
                              className="mt-1 h-4 w-4 rounded border-gray-600"
                            />
                            <div>
                              <p className="text-sm font-medium text-white">
                                Include default/community Snort3 rules
                              </p>
                              <p className="mt-1 text-xs text-gray-400">
                                {snortHasCustomRules
                                  ? "Checked: deploy custom rules together with the default rules set."
                                  : "When no custom rules are provided, Snort3 deploys with the default rules set only."}
                              </p>
                            </div>
                          </label>

                          <div className="space-y-2">
                            <label
                              htmlFor="snort3-rules-input"
                              className="block text-xs font-medium uppercase tracking-[0.2em] text-cyan-300"
                            >
                              Custom rules
                            </label>
                            <textarea
                              id="snort3-rules-input"
                              value={snortRulesInput}
                              onChange={(event) =>
                                onSnortRulesInputChange(event.target.value)
                              }
                              placeholder='alert tcp any any -> any any (msg:"snort3 test rule"; sid:1000001; rev:1;)'
                              spellCheck={false}
                              rows={8}
                              className="w-full rounded-lg border border-cyan-500/30 bg-white px-4 py-3 font-mono text-sm text-black outline-none transition-all focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20"
                            />
                            <div className="flex items-center justify-between text-xs text-gray-400">
                              <span>One rule per line.</span>
                              <span>
                                {snortHasCustomRules
                                  ? `${parsedSnortRules.length} custom rule${parsedSnortRules.length === 1 ? "" : "s"} ready`
                                  : "Default-rules-only deploy"}
                              </span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <div className="space-y-2">
                  <label className="block text-xs font-medium uppercase tracking-[0.2em] text-cyan-300">
                    {editorMode === "update" ? "Update Payload JSON" : "Deploy Payload JSON"}
                  </label>
                  <pre className="min-h-[360px] overflow-x-auto rounded-lg border border-cyan-500/30 bg-[#0b1120] px-4 py-3 font-mono text-sm text-white">
                    {exportedJson}
                  </pre>
                  <button
                    type="button"
                    onClick={handleSubmit}
                    disabled={!submitPayload || isDeploying || isToolDependencyBlocking}
                    className="w-full rounded-lg bg-emerald-500 px-4 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
                  >
                    {isDeploying
                      ? editorMode === "update"
                        ? "Updating..."
                        : "Deploying..."
                      : editorMode === "update"
                        ? "Update Configuration"
                        : "Deploy"}
                  </button>
                  {isToolDependencyBlocking && (
                    <p className="text-xs text-amber-300">
                      {editorMode === "update" ? "Update" : "Deploy"} is blocked until tshark is deployed and its topic
                      is available to the selected tool.
                    </p>
                  )}
                  {deployMessage && (
                    <p className="text-xs text-gray-300">{deployMessage}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// ADMIN DASHBOARD
// ═══════════════════════════════════════════════════════════════
function AdminDashboard() {
  const [selectedSecurityPosture, setSelectedSecurityPosture] = useState(
    "Network Security Posture",
  );
  const [selectedMonitoringTool, setSelectedMonitoringTool] = useState("");
  const [isLaunchEditorOpen, setIsLaunchEditorOpen] = useState(false);
  const [draftConfig, setDraftConfig] = useState<JsonObject | null>(null);
  const [isLoadingConfiguration, setIsLoadingConfiguration] = useState(false);
  const [configurationMessage, setConfigurationMessage] = useState("");
  const [editorMode, setEditorMode] = useState<EditorMode>("deploy");
  const [reconfigureConfigId, setReconfigureConfigId] = useState("");
  const [loadedConfigId, setLoadedConfigId] = useState<string | null>(null);
  const [snortRulesInput, setSnortRulesInput] = useState("");
  const [snortRuleSidsInput, setSnortRuleSidsInput] = useState("");
  const [snortIncludeDefaultRules, setSnortIncludeDefaultRules] = useState(true);
  const [snortRulesAction, setSnortRulesAction] = useState<SnortRulesAction>("");
  const [currentSnortRules, setCurrentSnortRules] = useState<string[]>([]);
  const [currentSnortRuleSids, setCurrentSnortRuleSids] = useState<string[]>([]);
  const [toolDependencyStatus, setToolDependencyStatus] =
    useState<ToolDependencyStatus>("idle");
  const [toolDependencyMessage, setToolDependencyMessage] = useState("");

  const resetSnortFormState = () => {
    setSnortRulesInput("");
    setSnortRuleSidsInput("");
    setSnortIncludeDefaultRules(true);
    setSnortRulesAction("");
    setCurrentSnortRules([]);
    setCurrentSnortRuleSids([]);
    setToolDependencyStatus("idle");
    setToolDependencyMessage("");
  };

  const resetEditorState = () => {
    setEditorMode("deploy");
    setReconfigureConfigId("");
    setLoadedConfigId(null);
  };

  const loadToolDependencyStatus = async (toolName: string) => {
    setToolDependencyStatus("checking");
    setToolDependencyMessage(
      "Checking whether tshark has already been deployed...",
    );

    try {
      const response = await fetch(
        `/api/configuration-manager/dependencies?toolName=${toolName}`,
        {
          cache: "no-store",
        },
      );
      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(
            payload,
            "Could not verify whether tshark is already deployed.",
          ),
        );
      }

      const dependencyReady =
        payload &&
        typeof payload === "object" &&
        "dependencyReady" in payload &&
        typeof payload.dependencyReady === "boolean"
          ? payload.dependencyReady
          : false;
      const message =
        payload &&
        typeof payload === "object" &&
        "message" in payload &&
        typeof payload.message === "string"
          ? payload.message
          : dependencyReady
            ? "Detected a tshark deployment that the tool can consume."
            : "Tshark has not been deployed yet. Deploy tshark first.";

      setToolDependencyStatus(dependencyReady ? "ready" : "not_ready");
      setToolDependencyMessage(message);
    } catch (error) {
      setToolDependencyStatus("error");
      setToolDependencyMessage(
        getErrorMessage(
          error,
          "Could not verify the tshark dependency. You can still rely on the backend validation.",
        ),
      );
    }
  };

  const updateDraftConfigValue = (
    config: JsonObject,
    path: string[],
    value: JsonPrimitive,
  ): JsonObject => {
    const [currentKey, ...restPath] = path;

    if (!currentKey) {
      return config;
    }

    if (restPath.length === 0) {
      return {
        ...config,
        [currentKey]: value,
      };
    }

    const nextValue = config[currentKey];

    if (typeof nextValue !== "object" || nextValue === null || Array.isArray(nextValue)) {
      return config;
    }

    return {
      ...config,
      [currentKey]: updateDraftConfigValue(nextValue, restPath, value),
    };
  };

  const loadToolDefaultConfiguration = async () => {
    const apiToolName = getApiToolName(selectedMonitoringTool);

    if (!apiToolName) {
      setDraftConfig(null);
      setIsLaunchEditorOpen(false);
      setConfigurationMessage(SUPPORTED_TOOLS_MESSAGE);
      resetEditorState();
      return;
    }

    setIsLoadingConfiguration(true);
    setConfigurationMessage("");
    setEditorMode("deploy");
    setReconfigureConfigId("");
    setLoadedConfigId(null);
    resetSnortFormState();

    if (apiToolName === "snort3" || apiToolName === "flow_module") {
      setToolDependencyStatus("checking");
      setToolDependencyMessage(
        "Checking whether tshark has already been deployed...",
      );
    } else {
      setToolDependencyStatus("idle");
      setToolDependencyMessage("");
    }

    try {
      const response = await fetch(
        `/api/configuration-manager/options?toolName=${encodeURIComponent(apiToolName)}`,
        {
          cache: "no-store",
        },
      );
      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          getErrorMessage(
            payload,
            `Failed to load configuration for ${selectedMonitoringTool}.`,
          ),
        );
      }

      const configurableVariables =
        payload &&
        typeof payload === "object" &&
        "configurable_variables" in payload &&
        Array.isArray(payload.configurable_variables)
          ? (payload.configurable_variables as ConfigurableVariable[])
          : [];

      if (configurableVariables.length === 0) {
        throw new Error(
          `Configuration Manager returned no configurable variables for ${selectedMonitoringTool}.`,
        );
      }

      setDraftConfig(buildDraftConfigFromVariables(configurableVariables));
      setIsLaunchEditorOpen(true);
      setConfigurationMessage(
        `Loaded ${configurableVariables.length} configurable values from Configuration Manager.`,
      );

      if (apiToolName === "snort3" || apiToolName === "flow_module") {
        await loadToolDependencyStatus(apiToolName);
      }
    } catch (error) {
      setDraftConfig(null);
      setIsLaunchEditorOpen(false);
      resetEditorState();
      setConfigurationMessage(
        getErrorMessage(
          error,
          `Failed to load configuration for ${selectedMonitoringTool}.`,
        ),
      );
    } finally {
      setIsLoadingConfiguration(false);
    }
  };

  const startReconfigureFlow = () => {
    const apiToolName = getApiToolName(selectedMonitoringTool);

    if (!apiToolName) {
      setDraftConfig(null);
      setIsLaunchEditorOpen(false);
      setConfigurationMessage(SUPPORTED_TOOLS_MESSAGE);
      resetEditorState();
      return;
    }

    setEditorMode("update");
    setIsLaunchEditorOpen(true);
    setDraftConfig(null);
    setReconfigureConfigId("");
    setLoadedConfigId(null);
    resetSnortFormState();
    setConfigurationMessage(
      "Enter a config_id returned by deploy, then load the stored configuration before editing it.",
    );
  };

  const loadCurrentToolConfigurationById = async (configIdOverride?: string) => {
    const apiToolName = getApiToolName(selectedMonitoringTool);
    const requestedConfigId = (configIdOverride ?? reconfigureConfigId).trim();

    if (!apiToolName) {
      setDraftConfig(null);
      setIsLaunchEditorOpen(false);
      setConfigurationMessage(SUPPORTED_TOOLS_MESSAGE);
      resetEditorState();
      return;
    }

    if (!requestedConfigId) {
      setConfigurationMessage(
        "Enter the config_id returned by deploy before loading the stored configuration.",
      );
      setDraftConfig(null);
      setLoadedConfigId(null);
      return;
    }

    setIsLoadingConfiguration(true);
    setConfigurationMessage("");
    setDraftConfig(null);
    setLoadedConfigId(null);
    resetSnortFormState();

    try {
      const [optionsResponse, configurationResponse] = await Promise.all([
        fetch(
          `/api/configuration-manager/options?toolName=${encodeURIComponent(apiToolName)}`,
          {
            cache: "no-store",
          },
        ),
        fetch(
          `/api/configuration-manager/configuration?config_id=${encodeURIComponent(requestedConfigId)}`,
          {
            cache: "no-store",
          },
        ),
      ]);

      const [optionsPayload, configurationPayload] = await Promise.all([
        optionsResponse.json().catch(() => null),
        configurationResponse.json().catch(() => null),
      ]);

      if (!optionsResponse.ok) {
        throw new Error(
          getErrorMessage(
            optionsPayload,
            `Failed to load configuration schema for ${selectedMonitoringTool}.`,
          ),
        );
      }

      if (!configurationResponse.ok) {
        throw new Error(
          getErrorMessage(
            configurationPayload,
            `Failed to load the stored configuration for config_id '${requestedConfigId}'.`,
          ),
        );
      }

      const configurableVariables =
        optionsPayload &&
        typeof optionsPayload === "object" &&
        "configurable_variables" in optionsPayload &&
        Array.isArray(optionsPayload.configurable_variables)
          ? (optionsPayload.configurable_variables as ConfigurableVariable[])
          : [];

      if (configurableVariables.length === 0) {
        throw new Error(
          `Configuration Manager returned no configurable variables for ${selectedMonitoringTool}.`,
        );
      }

      const configurationData =
        configurationPayload &&
        typeof configurationPayload === "object" &&
        "data" in configurationPayload &&
        typeof configurationPayload.data === "object" &&
        configurationPayload.data !== null
          ? (configurationPayload.data as Record<string, unknown>)
          : {};
      const storedToolName =
        typeof configurationData.tool_name === "string"
          ? configurationData.tool_name
          : "";

      if (storedToolName && storedToolName !== apiToolName) {
        throw new Error(
          `Config ID '${requestedConfigId}' belongs to '${storedToolName}', not '${apiToolName}'.`,
        );
      }

      const loadedConfigIdValue =
        configurationPayload &&
        typeof configurationPayload === "object" &&
        "config_id" in configurationPayload &&
        typeof configurationPayload.config_id === "string"
          ? configurationPayload.config_id
          : requestedConfigId;
      const resolvedEnv =
        typeof configurationData.resolved_env === "object" &&
        configurationData.resolved_env !== null
          ? (configurationData.resolved_env as Record<string, unknown>)
          : {};

      setDraftConfig(
        buildDraftConfigFromResolvedEnv(configurableVariables, resolvedEnv),
      );
      setIsLaunchEditorOpen(true);
      setEditorMode("update");
      setLoadedConfigId(loadedConfigIdValue);
      setReconfigureConfigId(loadedConfigIdValue);
      setConfigurationMessage(
        `Loaded stored configuration for ${selectedMonitoringTool}. Config ID: ${loadedConfigIdValue}`,
      );

      if (apiToolName === "snort3") {
        const rulesConfig =
          typeof configurationData.rules_config === "object" &&
          configurationData.rules_config !== null
            ? (configurationData.rules_config as Record<string, unknown>)
            : {};
        const customRules = Array.isArray(rulesConfig.custom_rules)
          ? rulesConfig.custom_rules.filter(
              (rule): rule is string => typeof rule === "string",
            )
          : [];
        const customRuleSids = Array.isArray(rulesConfig.custom_rule_sids)
          ? rulesConfig.custom_rule_sids.filter(
              (sid): sid is string => typeof sid === "string",
            )
          : [];
        const includeDefaultRules =
          typeof rulesConfig.include_default_rules === "boolean"
            ? rulesConfig.include_default_rules
            : true;

        setCurrentSnortRules(customRules);
        setCurrentSnortRuleSids(customRuleSids);
        setSnortIncludeDefaultRules(includeDefaultRules);
        setSnortRulesAction("");
        setSnortRulesInput("");
        setSnortRuleSidsInput("");
        if (apiToolName === "snort3" || apiToolName === "flow_module") {
          await loadToolDependencyStatus(apiToolName);
        }
      }
    } catch (error) {
      setDraftConfig(null);
      setLoadedConfigId(null);
      setConfigurationMessage(
        getErrorMessage(
          error,
          `Failed to load the stored configuration for ${selectedMonitoringTool}.`,
        ),
      );
    } finally {
      setIsLoadingConfiguration(false);
    }
  };

  return (
    <div id="dashboard-top" className="space-y-6">
      {/* Welcome banner */}
      <div className="rounded-xl border border-purple-500/20 bg-gradient-to-r from-purple-900/20 via-blue-900/20 to-cyan-900/20 p-6">
        <h1 className="text-2xl font-bold text-white">
          Platform Administration
        </h1>
        <p className="mt-1 text-sm text-gray-400">
          Configure tools, manage users, and monitor system health across the
          ROBUST-6G Programmable Monitoring Platform.
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Registered Users"
          value="24"
          change="+3"
          changeType="up"
          icon={Users}
          color="blue"
        />
        <KpiCard
          title="Active Tools"
          value="6 / 9"
          change="+1"
          changeType="up"
          icon={Wrench}
          color="purple"
        />
        <KpiCard
          title="Active Visualizations"
          value="4"
          change="+2"
          changeType="up"
          icon={BarChart3}
          color="cyan"
        />
        <KpiCard
          title="System Alerts"
          value="2"
          change="-1"
          changeType="down"
          icon={AlertTriangle}
          color="amber"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ─── Tool Activation Panel ─────────────────────────── */}
        <div className="lg:col-span-2 rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <div className="mb-5 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
              <Settings className="h-5 w-5 text-purple-400" />
              Platform Tools &amp; Functions
            </h3>
            <span className="rounded-full bg-purple-500/10 px-3 py-1 text-xs font-medium text-purple-400">
              4 of 4 active
            </span>
          </div>
          <div className="space-y-3">
            <ToolToggle
              name="Network Traffic Analyzer"
              description="Deep packet inspection and flow analysis"
              enabled={true}
              icon={Network}
            />
            <ToolToggle
              name="Intrusion Detection System"
              description="Signature & anomaly-based detection engine"
              enabled={true}
              icon={Shield}
            />
            <ToolToggle
              name="Communication Bus Module"
              description="Volumetric and application-layer DDoS protection"
              enabled={true}
              icon={Lock}
            />
            <ToolToggle
              name="Data Aggregation Pipeline"
              description="Centralized log collection and indexing"
              enabled={true}
              icon={Layers}
            />
          </div>
        </div>

        {/* ─── System Health ─────────────────────────────────── */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
            <Server className="h-5 w-5 text-cyan-400" />
            System Health
          </h3>
          <div className="space-y-3">
            {[
              { name: "Auth Service", status: "online" as const },
              { name: "PostgreSQL", status: "online" as const },
              { name: "Monitoring Pipeline", status: "online" as const },
              { name: "External API Proxy", status: "online" as const },
              { name: "Alert Engine", status: "online" as const },
              { name: "Visualization Server", status: "online" as const },
            ].map((s, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-3"
              >
                <p className="text-sm text-gray-300">{s.name}</p>
                <StatusBadge status={s.status} />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div id="monitoring-tool-configuration">
        <MonitoringToolConfigurationBox
          posture={selectedSecurityPosture}
          selectedTool={selectedMonitoringTool}
          draftConfig={draftConfig}
          isLaunchEditorOpen={isLaunchEditorOpen}
          isLoadingConfiguration={isLoadingConfiguration}
          configurationMessage={configurationMessage}
          onPostureChange={(nextPosture) => {
            setSelectedSecurityPosture(nextPosture);
            setSelectedMonitoringTool("");
            setIsLaunchEditorOpen(false);
            setDraftConfig(null);
            setConfigurationMessage("");
            resetEditorState();
            resetSnortFormState();
          }}
          onToolChange={(nextTool) => {
            setSelectedMonitoringTool(nextTool);
            setIsLaunchEditorOpen(false);
            setDraftConfig(null);
            setConfigurationMessage("");
            resetEditorState();
            resetSnortFormState();
          }}
          onDraftFieldChange={(path, value) => {
            setDraftConfig((currentConfig) => {
              if (!currentConfig) {
                return currentConfig;
              }

              return updateDraftConfigValue(currentConfig, path, value);
            });
          }}
          editorMode={editorMode}
          loadedConfigId={loadedConfigId}
          reconfigureConfigId={reconfigureConfigId}
          snortRulesInput={snortRulesInput}
          snortRuleSidsInput={snortRuleSidsInput}
          snortIncludeDefaultRules={snortIncludeDefaultRules}
          snortRulesAction={snortRulesAction}
          currentSnortRules={currentSnortRules}
          currentSnortRuleSids={currentSnortRuleSids}
          toolDependencyStatus={toolDependencyStatus}
          toolDependencyMessage={toolDependencyMessage}
          onReconfigureConfigIdChange={setReconfigureConfigId}
          onSnortRulesInputChange={setSnortRulesInput}
          onSnortRuleSidsInputChange={setSnortRuleSidsInput}
          onSnortIncludeDefaultRulesChange={setSnortIncludeDefaultRules}
          onSnortRulesActionChange={setSnortRulesAction}
          onLaunchClick={() => {
            void loadToolDefaultConfiguration();
          }}
          onReconfigureClick={() => {
            startReconfigureFlow();
          }}
          onLoadCurrentConfigClick={() => {
            void loadCurrentToolConfigurationById();
          }}
          onSubmitSuccess={(mode, configId) => {
            if (mode === "update") {
              void loadCurrentToolConfigurationById(
                configId ?? loadedConfigId ?? undefined,
              );
            }
          }}
        />
      </div>

      {/* ─── Quick Actions ───────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            label: "Create User",
            icon: UserPlus,
            color: "blue",
            href: "/dashboard/users",
          },
          {
            label: "Manage Tools",
            icon: Wrench,
            color: "purple",
            href: "/dashboard/tools",
          },
          {
            label: "Visualization Config",
            icon: Eye,
            color: "cyan",
            href: "/dashboard/visualizations",
          },
          {
            label: "Platform Settings",
            icon: Settings,
            color: "amber",
            href: "/dashboard/settings",
          },
        ].map((action, i) => (
          <a
            key={i}
            href={action.href}
            className="group flex items-center gap-3 rounded-xl border border-gray-800 bg-gray-900/50 p-4 transition-all hover:border-gray-700 hover:bg-gray-900"
          >
            <div
              className={`rounded-lg p-2 ${
                action.color === "blue"
                  ? "bg-blue-500/10 text-blue-400"
                  : action.color === "purple"
                    ? "bg-purple-500/10 text-purple-400"
                    : action.color === "cyan"
                      ? "bg-cyan-500/10 text-cyan-400"
                      : "bg-amber-500/10 text-amber-400"
              }`}
            >
              <action.icon className="h-5 w-5" />
            </div>
            <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">
              {action.label}
            </span>
            <ChevronRight className="ml-auto h-4 w-4 text-gray-600 group-hover:text-gray-400 transition-colors" />
          </a>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// USER DASHBOARD
// ═══════════════════════════════════════════════════════════════
function UserDashboard() {
  return (
    <div className="space-y-6">
      {/* Welcome banner */}
      <div className="rounded-xl border border-cyan-500/20 bg-gradient-to-r from-cyan-900/20 via-blue-900/20 to-purple-900/20 p-6">
        <h1 className="text-2xl font-bold text-white">Security Monitoring</h1>
        <p className="mt-1 text-sm text-gray-400">
          Real-time threat detection, active alerts, and monitoring dashboards
          assigned to your profile.
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          title="Active Alerts"
          value="7"
          change="+3"
          changeType="up"
          icon={AlertTriangle}
          color="amber"
        />
        <KpiCard
          title="Monitored Services"
          value="5"
          change="+1"
          changeType="up"
          icon={Monitor}
          color="cyan"
        />
        <KpiCard
          title="Resolved Today"
          value="12"
          change="+4"
          changeType="up"
          icon={CheckCircle}
          color="green"
        />
        <KpiCard
          title="Avg Response Time"
          value="2.4s"
          change="-0.3s"
          changeType="down"
          icon={Clock}
          color="purple"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ─── Active Alerts ─────────────────────────────────── */}
        <div className="lg:col-span-2 rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
              <AlertTriangle className="h-5 w-5 text-amber-400" />
              Active Alerts
            </h3>
            <button className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
              View all <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="space-y-3">
            {[
              {
                severity: "critical",
                title: "Unusual traffic spike detected on Node 7",
                source: "Network Traffic Analyzer",
                time: "5 min ago",
              },
              {
                severity: "high",
                title: "Brute-force attempt from 192.168.1.45",
                source: "Intrusion Detection System",
                time: "12 min ago",
              },
              {
                severity: "medium",
                title: "Latency increase on API Gateway",
                source: "Infrastructure Metrics",
                time: "30 min ago",
              },
              {
                severity: "low",
                title: "TLS certificate expiring in 14 days",
                source: "Vulnerability Scanner",
                time: "1 hour ago",
              },
              {
                severity: "medium",
                title: "Disk usage above 80% on DB node",
                source: "Log Aggregation Pipeline",
                time: "2 hours ago",
              },
              {
                severity: "critical",
                title: "Unauthorized access attempt on admin endpoint",
                source: "Intrusion Detection System",
                time: "3 hours ago",
              },
            ].map((alert, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-4"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`h-2.5 w-2.5 rounded-full ${
                      alert.severity === "critical"
                        ? "bg-red-500 animate-pulse"
                        : alert.severity === "high"
                          ? "bg-orange-400"
                          : alert.severity === "medium"
                            ? "bg-amber-400"
                            : "bg-blue-400"
                    }`}
                  />
                  <div>
                    <p className="text-sm text-white">{alert.title}</p>
                    <p className="text-xs text-gray-500">{alert.source}</p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span
                    className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                      alert.severity === "critical"
                        ? "bg-red-500/10 text-red-400"
                        : alert.severity === "high"
                          ? "bg-orange-500/10 text-orange-400"
                          : alert.severity === "medium"
                            ? "bg-amber-500/10 text-amber-400"
                            : "bg-blue-500/10 text-blue-400"
                    }`}
                  >
                    {alert.severity}
                  </span>
                  <p className="text-xs text-gray-600">{alert.time}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ─── Monitored Services ────────────────────────────── */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
            <Activity className="h-5 w-5 text-green-400" />
            Monitored Services
          </h3>
          <div className="space-y-3">
            {[
              {
                name: "Network Traffic Analyzer",
                status: "online" as const,
                alerts: 2,
              },
              {
                name: "Intrusion Detection",
                status: "online" as const,
                alerts: 3,
              },
              {
                name: "Vulnerability Scanner",
                status: "online" as const,
                alerts: 1,
              },
              { name: "Log Aggregation", status: "online" as const, alerts: 1 },
              {
                name: "AI Anomaly Engine",
                status: "offline" as const,
                alerts: 0,
              },
            ].map((service, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-950/50 p-3"
              >
                <div>
                  <p className="text-sm text-gray-300">{service.name}</p>
                  {service.alerts > 0 && (
                    <p className="text-xs text-amber-400">
                      {service.alerts} active alert(s)
                    </p>
                  )}
                </div>
                <StatusBadge status={service.status} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── Active Visualization Dashboards ─────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-white">
            <Eye className="h-5 w-5 text-cyan-400" />
            Your Active Dashboards
          </h3>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            {
              name: "Network Overview",
              type: "Grafana",
              description: "Real-time traffic, bandwidth, and flow analysis",
              color: "cyan",
            },
            {
              name: "Threat Intelligence Feed",
              type: "Custom",
              description: "Live threat indicators and IOC correlation",
              color: "red",
            },
            {
              name: "Infrastructure Metrics",
              type: "Grafana",
              description: "CPU, memory, disk, and service metrics",
              color: "green",
            },
          ].map((dash, i) => (
            <a
              key={i}
              href="#"
              className="group rounded-xl border border-gray-800 bg-gray-950/50 p-5 transition-all hover:border-gray-700 hover:bg-gray-900/80"
            >
              <div className="mb-3 flex items-center justify-between">
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                    dash.color === "cyan"
                      ? "bg-cyan-500/10 text-cyan-400"
                      : dash.color === "red"
                        ? "bg-red-500/10 text-red-400"
                        : "bg-green-500/10 text-green-400"
                  }`}
                >
                  {dash.type}
                </span>
                <ChevronRight className="h-4 w-4 text-gray-600 group-hover:text-gray-400 transition-colors" />
              </div>
              <h4 className="text-sm font-semibold text-white group-hover:text-cyan-300 transition-colors">
                {dash.name}
              </h4>
              <p className="mt-1 text-xs text-gray-500">{dash.description}</p>
            </a>
          ))}
        </div>
      </div>

      {/* ─── Recent Activity Timeline ────────────────────────── */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
        <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
          <Clock className="h-5 w-5 text-blue-400" />
          Recent Activity
        </h3>
        <div className="relative space-y-4 pl-6 before:absolute before:left-[9px] before:top-2 before:h-[calc(100%-16px)] before:w-px before:bg-gray-800">
          {[
            {
              action: "Resolved alert",
              detail: "Brute-force attempt mitigated",
              time: "10 min ago",
              color: "bg-green-400",
            },
            {
              action: "Investigated anomaly",
              detail: "Traffic spike on Node 7 — false positive",
              time: "25 min ago",
              color: "bg-blue-400",
            },
            {
              action: "Opened dashboard",
              detail: "Network Overview (Grafana)",
              time: "1 hour ago",
              color: "bg-cyan-400",
            },
            {
              action: "Escalated alert",
              detail: "Unauthorized admin endpoint access → Incident #42",
              time: "3 hours ago",
              color: "bg-amber-400",
            },
            {
              action: "Logged in",
              detail: "Session started from 10.0.1.22",
              time: "4 hours ago",
              color: "bg-purple-400",
            },
          ].map((event, i) => (
            <div key={i} className="relative flex gap-4">
              <div
                className={`absolute -left-[15px] top-1.5 h-3 w-3 rounded-full border-2 border-gray-900 ${event.color}`}
              />
              <div>
                <p className="text-sm text-white">{event.action}</p>
                <p className="text-xs text-gray-500">{event.detail}</p>
                <p className="mt-0.5 text-xs text-gray-600">{event.time}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// MAIN DASHBOARD PAGE — renders based on role
// ═══════════════════════════════════════════════════════════════
export default function DashboardPage() {
  const { data: session } = useSession();
  const role = (session?.user as any)?.role as "ADMIN" | "USER" | undefined;

  useEffect(() => {
    const scrollToHashSection = () => {
      const sectionId = window.location.hash.replace("#", "");
      if (!sectionId) {
        return;
      }

      const section = document.getElementById(sectionId);
      section?.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    // Run after the dashboard content mounts.
    const timeoutId = window.setTimeout(scrollToHashSection, 0);
    window.addEventListener("hashchange", scrollToHashSection);

    return () => {
      window.clearTimeout(timeoutId);
      window.removeEventListener("hashchange", scrollToHashSection);
    };
  }, []);

  return (
    <div className="min-h-screen bg-[#0a0e27] p-6">
      {role === "ADMIN" && <AdminDashboard />}
      {role === "USER" && <UserDashboard />}
      {!role && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-cyan-400" />
        </div>
      )}
    </div>
  );
}
