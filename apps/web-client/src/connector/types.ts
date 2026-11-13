export type ServiceState = "ok" | "degraded" | "down";

export interface HealthStatus {
  status: ServiceState;
  version: string;
  database: ServiceState;
}

export interface Me {
  email: string;
  name: string | null;
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

export interface ToolStarted {
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolFinished {
  name: string;
  failed: boolean;
}

export interface Acknowledgement {
  text: string;
}

export interface ReplyStreamHandlers {
  onToken?: (text: string) => void;
  onThinking?: () => void;
  onAcknowledgement?: (acknowledgement: Acknowledgement) => void;
  onTool?: (tool: ToolStarted) => void;
  onToolResult?: (tool: ToolFinished) => void;
}

export interface PushStatus {
  configured: boolean;
  public_key: string | null;
  subscriptions: number;
}

export interface PushTestResult {
  sent: number;
  expired: number;
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

export interface ConversationStatus {
  answering: boolean;
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

export type DocumentStatus = "pending" | "indexed" | "failed";

export interface DocumentSummary {
  id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  page_count: number | null;
  status: DocumentStatus;
  error: string | null;
  created_at: string;
}

export interface DocumentList {
  documents: DocumentSummary[];
}

export interface McpConnection {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  has_token: boolean;
  created_at: string;
}

export interface McpConnectionList {
  connections: McpConnection[];
}

export interface McpConnectionDraft {
  name: string;
  url: string;
  token: string;
}

export interface McpConnectionUpdate {
  enabled?: boolean;
  url?: string;
  token?: string;
}

export interface McpConnectionTest {
  ok: boolean;
  tool_count: number;
  error: string | null;
}

export interface McpConnectionPreset {
  id: string;
  label: string;
  name: string;
  url: string;
  help: string;
}

export interface McpConnectionPresetList {
  presets: McpConnectionPreset[];
}
