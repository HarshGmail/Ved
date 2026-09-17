"use client";

import { useEffect, useState } from "react";
import { connector, type HealthStatus } from "@/connector";
import styles from "./backend-status.module.css";

type Probe =
  | { state: "checking" }
  | { state: "reachable"; health: HealthStatus }
  | { state: "unreachable"; reason: string };

export function BackendStatus() {
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

  const indicator =
    probe.state === "reachable" && probe.health.status !== "ok"
      ? "degraded"
      : probe.state;

  return (
    <p className={styles.status} data-state={indicator}>
      <span className={styles.dot} aria-hidden="true" />
      {probe.state === "checking" && "checking backend…"}
      {probe.state === "reachable" &&
        `backend ${probe.health.status} — v${probe.health.version} · db ${probe.health.database}`}
      {probe.state === "unreachable" && `backend unreachable — ${probe.reason}`}
    </p>
  );
}
