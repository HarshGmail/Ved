import {
  AGENT_TIMEOUT_MS,
  type ConnectorConfig,
  resolveConfig,
  STREAM_IDLE_TIMEOUT_MS,
} from "./config";
import { createHttpClient, type RequestOptions } from "./http";
import { createReplyStream } from "./reply-stream";
import { createEventStreamClient } from "./sse";
import { createStreamClient } from "./stream";
import type {
  AgentReply,
  ConversationList,
  ConversationTranscript,
  HealthStatus,
  PushStatus,
  PushTestResult,
  ReplyStreamHandlers,
} from "./types";

export function createConnector(overrides: Partial<ConnectorConfig> = {}) {
  const config = resolveConfig(overrides);
  const request = createHttpClient(config);
  const openStream = createStreamClient(config);
  const postEventStream = createEventStreamClient(config);
  const streamReply = createReplyStream(postEventStream);

  return {
    config,
    request,
    openStream,
    postEventStream,
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
    streamMessage: (
      prompt: string,
      conversationId: string | undefined,
      handlers: ReplyStreamHandlers,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      streamReply({
        prompt,
        conversationId,
        handlers,
        idleTimeoutMs: STREAM_IDLE_TIMEOUT_MS,
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

export {
  ConnectorError,
  HttpError,
  NetworkError,
  StreamError,
  StreamUnavailableError,
  TimeoutError,
} from "./errors";
export type { ConnectorConfig } from "./config";
export type { HttpClient, HttpMethod, RequestOptions } from "./http";
export type { EventStreamClient, SseEvent } from "./sse";
export type { StreamClient, StreamHandle, StreamHandlers } from "./stream";
export type {
  Acknowledgement,
  AgentReply,
  ConversationList,
  ConversationSummary,
  ConversationTranscript,
  HealthStatus,
  PushStatus,
  PushTestResult,
  ReplyStreamHandlers,
  ServiceState,
  ToolFinished,
  ToolInvocation,
  ToolStarted,
  TranscriptMessage,
} from "./types";
