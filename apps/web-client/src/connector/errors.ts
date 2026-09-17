export class ConnectorError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConnectorError";
  }
}

export class HttpError extends ConnectorError {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, statusText: string, body: unknown) {
    super(`Request failed with status ${status} ${statusText}`);
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
