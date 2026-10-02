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
  conversation_id: string;
  tool_calls: ToolInvocation[];
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  last_message_at: string;
}

export interface ConversationList {
  conversations: ConversationSummary[];
}

export interface TranscriptMessage {
  id: string;
  role: string;
  text: string;
  model: string | null;
  tool_calls: ToolInvocation[];
  created_at: string;
}

export interface ConversationTranscript {
  id: string;
  title: string | null;
  messages: TranscriptMessage[];
}
