export type ServiceState = "ok" | "degraded" | "down";

export interface HealthStatus {
  status: ServiceState;
  version: string;
  database: ServiceState;
}
