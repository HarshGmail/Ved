export type ServiceState = "ok" | "degraded" | "down";

export interface HealthStatus {
  status: ServiceState;
  version: string;
  database: ServiceState;
}

export interface ToolInvocation {
  name: string;
  arguments: Record<string, unknown>;
  failed: boolean;
}

export interface AgentReply {
  text: string;
  model: string;
  tool_calls: ToolInvocation[];
}
