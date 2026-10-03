export interface ConnectorConfig {
  baseUrl: string;
  getAuthToken?: () => string | null | Promise<string | null>;
  defaultTimeoutMs: number;
}

const DEFAULT_BASE_URL = "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 30_000;

export const AGENT_TIMEOUT_MS = 180_000;

export function resolveConfig(
  overrides: Partial<ConnectorConfig> = {},
): ConnectorConfig {
  return {
    baseUrl: overrides.baseUrl ?? DEFAULT_BASE_URL,
    getAuthToken: overrides.getAuthToken,
    defaultTimeoutMs: overrides.defaultTimeoutMs ?? DEFAULT_TIMEOUT_MS,
  };
}
