"use client";

import { useEffect, useState } from "react";
import { connector, type HealthStatus } from "@/connector";
import styles from "./backend-status.module.css";

export type Probe =
  | { state: "checking" }
  | { state: "reachable"; health: HealthStatus }
  | { state: "unreachable"; reason: string };

export function useBackendProbe(): Probe {
  const [probe, setProbe] = useState<Probe>({ state: "checking" });

  useEffect(() => {
    const controller = new AbortController();

    connector
      .health({ signal: controller.signal })
      .then((health) => setProbe({ state: "reachable", health }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setProbe({
          state: "unreachable",
          reason: error instanceof Error ? error.message : "Unknown error",
        });
      });

    return () => controller.abort();
  }, []);

  return probe;
}

export function summarizeBackend(probe: Probe): string {
  if (probe.state === "checking") return "checking backend…";
  if (probe.state === "reachable") {
    const { status, version, database } = probe.health;
    return `backend ${status} — v${version} · db ${database}`;
  }
  return `backend unreachable — ${probe.reason}`;
}

export function BackendStatus() {
  const probe = useBackendProbe();
  const indicator =
    probe.state === "reachable" && probe.health.status !== "ok"
      ? "degraded"
      : probe.state;
  const summary = summarizeBackend(probe);

  return (
    <span
      className={styles.dot}
      role="img"
      aria-label={summary}
      title={summary}
      data-state={indicator}
    />
  );
}

export function BackendStatusLine() {
  const probe = useBackendProbe();
  return <p>{summarizeBackend(probe)}</p>;
}
