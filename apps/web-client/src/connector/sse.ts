import type { ConnectorConfig } from "./config";
import {
  HttpError,
  NetworkError,
  StreamUnavailableError,
  TimeoutError,
} from "./errors";
import { buildHeaders, buildUrl } from "./http";

export interface SseEvent {
  event: string;
  data: string;
}

export interface EventStreamOptions {
  path: string;
  body: unknown;
  onEvent: (event: SseEvent) => void;
  signal?: AbortSignal;
  idleTimeoutMs: number;
}

const DEFAULT_EVENT_NAME = "message";
const EVENT_STREAM_TYPE = "text/event-stream";
const LINE_BREAK = /\r\n|\r|\n/;
const ROUTE_MISSING_STATUSES = new Set([404, 405, 501]);

export function createSseParser(onEvent: (event: SseEvent) => void) {
  let buffer = "";
  let eventName = "";
  let dataLines: string[] = [];

  function dispatch() {
    if (dataLines.length > 0) {
      onEvent({ event: eventName || DEFAULT_EVENT_NAME, data: dataLines.join("\n") });
    }
    eventName = "";
    dataLines = [];
  }

  function processLine(line: string) {
    if (line === "") {
      dispatch();
      return;
    }
    if (line.startsWith(":")) return;

    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const rawValue = colon === -1 ? "" : line.slice(colon + 1);
    const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;

    if (field === "event") eventName = value;
    else if (field === "data") dataLines.push(value);
  }

  function drainCompleteLines() {
    for (;;) {
      const match = LINE_BREAK.exec(buffer);
      if (!match) return;
      const endsOnLoneCarriageReturn =
        match[0] === "\r" && match.index === buffer.length - 1;
      if (endsOnLoneCarriageReturn) return;
      processLine(buffer.slice(0, match.index));
      buffer = buffer.slice(match.index + match[0].length);
    }
  }

  return {
    push(chunk: string) {
      buffer += chunk;
      drainCompleteLines();
    },
    end() {
      if (buffer) processLine(buffer.replace(/\r$/, ""));
      buffer = "";
      dispatch();
    },
  };
}

function createIdleDeadline(idleTimeoutMs: number, external?: AbortSignal) {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const forwardAbort = () => controller.abort(external?.reason);

  const restart = () => {
    clearTimeout(timer);
    timer = setTimeout(
      () => controller.abort(new TimeoutError(idleTimeoutMs)),
      idleTimeoutMs,
    );
  };

  if (external) {
    if (external.aborted) forwardAbort();
    else external.addEventListener("abort", forwardAbort, { once: true });
  }
  restart();

  return {
    signal: controller.signal,
    restart,
    cleanup: () => {
      clearTimeout(timer);
      external?.removeEventListener("abort", forwardAbort);
    },
  };
}

async function readErrorBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  try {
    return contentType.includes("application/json")
      ? await response.json()
      : await response.text();
  } catch {
    return null;
  }
}

export function createEventStreamClient(config: ConnectorConfig) {
  return async function postEventStream(options: EventStreamOptions): Promise<void> {
    const deadline = createIdleDeadline(options.idleTimeoutMs, options.signal);
    const toConnectorError = (cause: unknown) =>
      deadline.signal.reason instanceof TimeoutError
        ? deadline.signal.reason
        : new NetworkError(cause);

    try {
      let response: Response;
      try {
        const headers = await buildHeaders(config, {
          path: options.path,
          body: options.body,
        });
        headers.set("Accept", EVENT_STREAM_TYPE);
        response = await fetch(buildUrl(config.baseUrl, options.path, undefined), {
          method: "POST",
          headers,
          body: JSON.stringify(options.body),
          signal: deadline.signal,
        });
      } catch (cause) {
        throw toConnectorError(cause);
      }

      if (ROUTE_MISSING_STATUSES.has(response.status)) {
        throw new StreamUnavailableError(`backend answered ${response.status}`);
      }
      if (!response.ok) {
        throw new HttpError(
          response.status,
          response.statusText,
          await readErrorBody(response),
        );
      }
      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.includes(EVENT_STREAM_TYPE) || !response.body) {
        throw new StreamUnavailableError("the response is not an event stream");
      }

      const parser = createSseParser(options.onEvent);
      const decoder = new TextDecoder();
      const reader = response.body.getReader();
      try {
        for (;;) {
          let chunk: ReadableStreamReadResult<Uint8Array>;
          try {
            chunk = await reader.read();
          } catch (cause) {
            throw toConnectorError(cause);
          }
          if (chunk.done) break;
          deadline.restart();
          parser.push(decoder.decode(chunk.value, { stream: true }));
        }
      } finally {
        await reader.cancel().catch(() => undefined);
      }
      parser.push(decoder.decode());
      parser.end();
    } finally {
      deadline.cleanup();
    }
  };
}

export type EventStreamClient = ReturnType<typeof createEventStreamClient>;
