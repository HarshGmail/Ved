import {
  AGENT_TIMEOUT_MS,
  CONNECTION_TEST_TIMEOUT_MS,
  type ConnectorConfig,
  resolveConfig,
  STREAM_IDLE_TIMEOUT_MS,
  UPLOAD_TIMEOUT_MS,
  VOICE_SPEAK_TIMEOUT_MS,
  VOICE_TRANSCRIBE_TIMEOUT_MS,
} from "./config";
import { createHttpClient, type RequestOptions } from "./http";
import { agentMessageBody, createReplyStream } from "./reply-stream";
import { createEventStreamClient } from "./sse";
import { createStreamClient } from "./stream";
import type {
  AgentReply,
  ClaudeUsage,
  McpConnection,
  McpConnectionDraft,
  McpConnectionList,
  McpConnectionPresetList,
  McpConnectionTest,
  McpConnectionUpdate,
  ConversationList,
  ConversationStatus,
  ConversationTranscript,
  DocumentList,
  DocumentSummary,
  HealthStatus,
  Me,
  PushStatus,
  PushTestResult,
  ReplyStreamHandlers,
  Transcription,
  VoiceInfo,
  VoiceStatus,
} from "./types";

const DOCUMENT_FIELD = "file";
const AUDIO_FIELD = "audio";
const LANGUAGE_FIELD = "language";
const DEFAULT_AUDIO_EXTENSION = "webm";
const AUDIO_EXTENSIONS: ReadonlyArray<readonly [needle: string, extension: string]> = [
  ["mp4", "mp4"],
  ["ogg", "ogg"],
];

export interface ReplyOptions extends Pick<RequestOptions, "signal"> {
  voice?: boolean;
}

export interface SpeakOptions extends Pick<RequestOptions, "signal"> {
  voice?: string;
  speed?: number;
}

function documentForm(file: Blob, filename: string): FormData {
  const form = new FormData();
  form.append(DOCUMENT_FIELD, file, filename);
  return form;
}

function audioExtension(mediaType: string): string {
  return AUDIO_EXTENSIONS.find(([needle]) => mediaType.includes(needle))?.[1] ?? DEFAULT_AUDIO_EXTENSION;
}

function transcriptionForm(audio: Blob, language?: string): FormData {
  const form = new FormData();
  form.append(AUDIO_FIELD, audio, `voice.${audioExtension(audio.type)}`);
  if (language) form.append(LANGUAGE_FIELD, language);
  return form;
}

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
    me: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<Me>({ path: "/me", ...options }),
    sendMessage: (
      prompt: string,
      conversationId?: string,
      options: ReplyOptions = {},
    ) =>
      request<AgentReply>({
        method: "POST",
        path: "/agent/message",
        body: agentMessageBody(prompt, conversationId, options.voice),
        timeoutMs: AGENT_TIMEOUT_MS,
        signal: options.signal,
      }),
    streamMessage: (
      prompt: string,
      conversationId: string | undefined,
      handlers: ReplyStreamHandlers,
      options: ReplyOptions = {},
    ) =>
      streamReply({
        prompt,
        conversationId,
        voice: options.voice,
        handlers,
        idleTimeoutMs: STREAM_IDLE_TIMEOUT_MS,
        signal: options.signal,
      }),
    voiceStatus: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<VoiceStatus>({ path: "/voice/status", ...options }),
    voices: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<VoiceInfo[]>({ path: "/voice/voices", ...options }),
    speak: (text: string, options: SpeakOptions = {}) =>
      request<ArrayBuffer>({
        method: "POST",
        path: "/voice/speak",
        body: { text, voice: options.voice, speed: options.speed },
        binary: true,
        timeoutMs: VOICE_SPEAK_TIMEOUT_MS,
        signal: options.signal,
      }),
    transcribe: (
      audio: Blob,
      language?: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<Transcription>({
        method: "POST",
        path: "/voice/transcribe",
        body: transcriptionForm(audio, language),
        timeoutMs: VOICE_TRANSCRIBE_TIMEOUT_MS,
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
    conversationStatus: (
      conversationId: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<ConversationStatus>({
        path: `/conversations/${conversationId}/status`,
        ...options,
      }),
    listDocuments: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<DocumentList>({ path: "/documents", ...options }),
    uploadDocument: (
      file: Blob,
      filename: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<DocumentSummary>({
        method: "POST",
        path: "/documents",
        body: documentForm(file, filename),
        timeoutMs: UPLOAD_TIMEOUT_MS,
        ...options,
      }),
    deleteDocument: (
      documentId: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<null>({
        method: "DELETE",
        path: `/documents/${documentId}`,
        ...options,
      }),
    listConnections: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<McpConnectionList>({ path: "/connections", ...options }),
    listConnectionPresets: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<McpConnectionPresetList>({ path: "/connections/presets", ...options }),
    claudeUsage: (options: Pick<RequestOptions, "signal"> = {}) =>
      request<ClaudeUsage>({ path: "/usage/claude", ...options }),
    setClaudeBalance: (
      balanceUsd: number,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<ClaudeUsage>({
        method: "PUT",
        path: "/usage/claude/balance",
        body: { balance_usd: balanceUsd },
        ...options,
      }),
    createConnection: (
      draft: McpConnectionDraft,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<McpConnection>({
        method: "POST",
        path: "/connections",
        body: draft,
        ...options,
      }),
    updateConnection: (
      connectionId: string,
      update: McpConnectionUpdate,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<McpConnection>({
        method: "PATCH",
        path: `/connections/${connectionId}`,
        body: update,
        ...options,
      }),
    deleteConnection: (
      connectionId: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<null>({
        method: "DELETE",
        path: `/connections/${connectionId}`,
        ...options,
      }),
    testConnection: (
      connectionId: string,
      options: Pick<RequestOptions, "signal"> = {},
    ) =>
      request<McpConnectionTest>({
        method: "POST",
        path: `/connections/${connectionId}/test`,
        timeoutMs: CONNECTION_TEST_TIMEOUT_MS,
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
  ClaudeUsage,
  McpConnection,
  McpConnectionDraft,
  McpConnectionList,
  McpConnectionPreset,
  McpConnectionPresetList,
  McpConnectionTest,
  McpConnectionUpdate,
  ConversationList,
  ConversationStatus,
  ConversationSummary,
  ConversationTranscript,
  DocumentList,
  DocumentStatus,
  DocumentSummary,
  HealthStatus,
  Me,
  PushStatus,
  PushTestResult,
  ReplyStreamHandlers,
  ServiceState,
  ToolFinished,
  ToolInvocation,
  ToolStarted,
  Transcription,
  TranscriptMessage,
  VoiceInfo,
  VoiceStatus,
} from "./types";
