export const TOOL_DEPLOY_ENDPOINTS = {
  tshark: "DeployNetworkTool",
  flow_module: "DeployNetworkTool",
  telegraf: "DeployInfrastructureTool",
  fluentd: "DeployServiceTool",
  falco: "DeployServiceTool",
  snort3: "DeploySecurityTool",
} as const;

export type SupportedToolName = keyof typeof TOOL_DEPLOY_ENDPOINTS;

export const SUPPORTED_TOOL_NAMES = Object.keys(
  TOOL_DEPLOY_ENDPOINTS,
) as SupportedToolName[];

export function isSupportedToolName(
  toolName: string,
): toolName is SupportedToolName {
  return toolName in TOOL_DEPLOY_ENDPOINTS;
}

export const SUPPORTED_TOOLS_MESSAGE =
  "This proof of concept currently supports Tshark, Snort, Flow, Telegraf, Fluentd, and Falco.";
