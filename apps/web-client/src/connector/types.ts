export interface HealthStatus {
  status: "ok" | "degraded" | "down";
  version?: string;
}
