import { type ConnectorConfig, resolveConfig } from "./config";
import { createHttpClient, type RequestOptions } from "./http";
import { createStreamClient } from "./stream";
import type { AgentReply, HealthStatus } from "./types";

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
    sendMessage: (prompt: string, options: Pick<RequestOptions, "signal"> = {}) =>
      request<AgentReply>({
        method: "POST",
        path: "/agent/message",
        body: { prompt },
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
  HealthStatus,
  ServiceState,
  ToolInvocation,
} from "./types";
