import { AGENT_TIMEOUT_MS, type ConnectorConfig, resolveConfig } from "./config";
import { createHttpClient, type RequestOptions } from "./http";
import { createStreamClient } from "./stream";
import type {
  AgentReply,
  ConversationList,
  ConversationTranscript,
  HealthStatus,
  PushStatus,
  PushTestResult,
} from "./types";

export function createConnector(overrides: Partial<ConnectorConfig> = {}) {
  const config = resolveConfig(overrides);
  const request = createHttpClient(config);
  const openStream = createStreamClient(config);

  return {
    config,
    request,
    openStream,
    health: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<HealthStatus>({ path: "/health", ...options }),
    sendMessage: (
      prompt: string,
      conversationId?: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<AgentReply>({
        method: "POST",
        path: "/agent/message",
        body: { prompt, conversation_id: conversationId ?? null },
        timeoutMs: AGENT_TIMEOUT_MS,
        ...options,
      }),
    listConversations: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<ConversationList>({ path: "/conversations", ...options }),
    pushStatus: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<PushStatus>({ path: "/push/status", ...options }),
    subscribeToPush: (
      subscription: PushSubscriptionJSON,
      label?: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<PushStatus>({
        method: "POST",
        path: "/push/subscribe",
        body: {
          endpoint: subscription.endpoint,
          keys: subscription.keys,
          label: label ?? null,
        },
        ...options,
      }),
    unsubscribeFromPush: (
      endpoint: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<PushStatus>({
        method: "POST",
        path: "/push/unsubscribe",
        body: { endpoint },
        ...options,
      }),
    sendTestPush: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<PushTestResult>({ method: "POST", path: "/push/test", ...options }),
    readConversation: (
      conversationId: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<ConversationTranscript>({
        path: `/conversations/${conversationId}`,
        ...options,
      }),
  };
}

export type Connector = ReturnType<typeof createConnector>;

export const connector = createConnector({
  baseUrl: process.env.NEXT_PUBLIC_VED_API_URL,
});

export { ConnectorError, HttpError, NetworkError, TimeoutError } from "./errors";
export type { ConnectorConfig } from "./config";
export type { HttpClient, HttpMethod, RequestOptions } from "./http";
export type { StreamClient, StreamHandle, StreamHandlers } from "./stream";
export type {
  AgentReply,
  ConversationList,
  ConversationSummary,
  ConversationTranscript,
  HealthStatus,
  PushStatus,
  PushTestResult,
  ServiceState,
  ToolInvocation,
  TranscriptMessage,
} from "./types";
