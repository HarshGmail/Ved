export class ConnectorError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConnectorError";
  }
}

function explain(body: unknown): string | null {
  if (typeof body === "string" && body.trim()) return body.trim();
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
  }
  return null;
}

export class HttpError extends ConnectorError {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, statusText: string, body: unknown) {
    super(explain(body) ?? `Request failed with status ${status} ${statusText}`);
    this.name = "HttpError";
    this.status = status;
    this.body = body;
  }
}

export class TimeoutError extends ConnectorError {
  constructor(timeoutMs: number) {
    super(`Request timed out after ${timeoutMs}ms`);
    this.name = "TimeoutError";
  }
}

export class NetworkError extends ConnectorError {
  constructor(cause: unknown) {
    super("Network request failed");
    this.name = "NetworkError";
    this.cause = cause;
  }
}

export class StreamError extends ConnectorError {
  constructor(detail: string) {
    super(detail);
    this.name = "StreamError";
  }
}

export class StreamUnavailableError extends ConnectorError {
  constructor(reason: string) {
    super(`Streaming is not available: ${reason}`);
    this.name = "StreamUnavailableError";
  }
}
