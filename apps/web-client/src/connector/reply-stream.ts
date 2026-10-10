import { StreamError } from "./errors";
import type { EventStreamClient, SseEvent } from "./sse";
import type {
  AgentReply,
  ReplyStreamHandlers,
  ToolFinished,
  ToolStarted,
} from "./types";

export interface ReplyStreamRequest {
  prompt: string;
  conversationId?: string;
  handlers: ReplyStreamHandlers;
  signal?: AbortSignal;
  idleTimeoutMs: number;
}

interface StreamOutcome {
  reply?: AgentReply;
  failure?: string;
}

const REPLY_STREAM_PATH = "/agent/message/stream";
const ENDED_WITHOUT_REPLY = "The reply stream ended before Ved finished answering.";
const MALFORMED_EVENT = "Ved sent a reply event that could not be read.";

function parsePayload(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch {
    throw new StreamError(MALFORMED_EVENT);
  }
}

export function createReplyStream(postEventStream: EventStreamClient) {
  return async function streamMessage(request: ReplyStreamRequest): Promise<AgentReply> {
    const outcome: StreamOutcome = {};
    const { handlers } = request;

    function onEvent({ event, data }: SseEvent) {
      if (outcome.reply || outcome.failure) return;
      const payload = parsePayload(data);
      switch (event) {
        case "token":
          handlers.onToken?.((payload as { text: string }).text);
          break;
        case "tool":
          handlers.onTool?.(payload as ToolStarted);
          break;
        case "tool_result":
          handlers.onToolResult?.(payload as ToolFinished);
          break;
        case "done":
          outcome.reply = payload as AgentReply;
          break;
        case "error":
          outcome.failure = (payload as { detail: string }).detail;
          break;
      }
    }

    await postEventStream({
      path: REPLY_STREAM_PATH,
      body: { prompt: request.prompt, conversation_id: request.conversationId ?? null },
      onEvent,
      signal: request.signal,
      idleTimeoutMs: request.idleTimeoutMs,
    });

    if (outcome.failure !== undefined) throw new StreamError(outcome.failure);
    if (outcome.reply === undefined) throw new StreamError(ENDED_WITHOUT_REPLY);
    return outcome.reply;
  };
}
