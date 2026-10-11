import type { ConnectorConfig } from "./config";
import { HttpError, NetworkError, TimeoutError } from "./errors";

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RequestOptions {
  method?: HttpMethod;
  path: string;
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export function buildUrl(
  baseUrl: string,
  path: string,
  query: RequestOptions["query"],
): string {
  const url = new URL(path.replace(/^\//, ""), ensureTrailingSlash(baseUrl));
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }
  return url.toString();
}

function ensureTrailingSlash(value: string): string {
  return value.endsWith("/") ? value : `${value}/`;
}

function isFormData(body: unknown): body is FormData {
  return typeof FormData !== "undefined" && body instanceof FormData;
}

function encodeBody(body: unknown): BodyInit | undefined {
  if (body === undefined) return undefined;
  return isFormData(body) ? body : JSON.stringify(body);
}

export async function buildHeaders(
  config: ConnectorConfig,
  options: RequestOptions,
): Promise<Headers> {
  const headers = new Headers({ Accept: "application/json" });
  if (options.body !== undefined && !isFormData(options.body)) {
    headers.set("Content-Type", "application/json");
  }
  const token = await config.getAuthToken?.();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  for (const [key, value] of Object.entries(options.headers ?? {})) {
    headers.set(key, value);
  }
  return headers;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function combineSignals(
  timeoutMs: number,
  external?: AbortSignal,
): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new TimeoutError(timeoutMs)), timeoutMs);
  const forwardAbort = () => controller.abort(external?.reason);

  if (external) {
    if (external.aborted) forwardAbort();
    else external.addEventListener("abort", forwardAbort, { once: true });
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      external?.removeEventListener("abort", forwardAbort);
    },
  };
}

export function createHttpClient(config: ConnectorConfig) {
  return async function request<TResponse>(
    options: RequestOptions,
  ): Promise<TResponse> {
    const timeoutMs = options.timeoutMs ?? config.defaultTimeoutMs;
    const { signal, cleanup } = combineSignals(timeoutMs, options.signal);

    let response: Response;
    try {
      response = await fetch(buildUrl(config.baseUrl, options.path, options.query), {
        method: options.method ?? "GET",
        headers: await buildHeaders(config, options),
        body: encodeBody(options.body),
        signal,
      });
    } catch (cause) {
      if (signal.reason instanceof TimeoutError) throw signal.reason;
      throw new NetworkError(cause);
    } finally {
      cleanup();
    }

    const body = await parseBody(response);
    if (!response.ok) {
      throw new HttpError(response.status, response.statusText, body);
    }
    return body as TResponse;
  };
}

export type HttpClient = ReturnType<typeof createHttpClient>;
