"use client";

import { useCallback, useEffect, useState } from "react";
import { connector } from "@/connector";
import styles from "./notifications.module.css";

type State =
  | { kind: "checking" }
  | { kind: "unsupported" }
  | { kind: "unconfigured" }
  | { kind: "blocked" }
  | { kind: "off" }
  | { kind: "on"; endpoint: string }
  | { kind: "error"; reason: string };

const VAPID_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;

function toApplicationServerKey(base64: string): Uint8Array<ArrayBuffer> {
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

export function Notifications() {
  const [state, setState] = useState<State>({ kind: "checking" });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const detect = useCallback(async (): Promise<State> => {
    if (!pushSupported()) return { kind: "unsupported" };
    if (!VAPID_KEY) return { kind: "unconfigured" };
    if (Notification.permission === "denied") return { kind: "blocked" };

    try {
      const registration = await navigator.serviceWorker.ready;
      const existing = await registration.pushManager.getSubscription();
      return existing ? { kind: "on", endpoint: existing.endpoint } : { kind: "off" };
    } catch (error: unknown) {
      return { kind: "error", reason: describe(error) };
    }
  }, []);

  useEffect(() => {
    let active = true;
    detect().then((next) => {
      if (active) setState(next);
    });
    return () => {
      active = false;
    };
  }, [detect]);

  async function enable() {
    if (!VAPID_KEY) return;
    setBusy(true);
    setNote(null);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState({ kind: permission === "denied" ? "blocked" : "off" });
        return;
      }

      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: toApplicationServerKey(VAPID_KEY),
      });

      await connector.subscribeToPush(subscription.toJSON(), navigator.userAgent);
      setState({ kind: "on", endpoint: subscription.endpoint });
      setNote("Reminders will arrive here, even with Ved closed.");
    } catch (error: unknown) {
      setState({ kind: "error", reason: describe(error) });
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true);
    setNote(null);
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        await connector.unsubscribeFromPush(subscription.endpoint);
        await subscription.unsubscribe();
      }
      setState({ kind: "off" });
    } catch (error: unknown) {
      setState({ kind: "error", reason: describe(error) });
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    setNote(null);
    try {
      const result = await connector.sendTestPush();
      setNote(
        result.sent > 0
          ? `Sent to ${result.sent} device${result.sent === 1 ? "" : "s"}.`
          : "No device received it — try enabling notifications again.",
      );
    } catch (error: unknown) {
      setNote(describe(error));
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "checking") return null;

  return (
    <section className={styles.panel} data-state={state.kind}>
      <p className={styles.line}>
        {state.kind === "unsupported" && "This browser cannot deliver reminders."}
        {state.kind === "unconfigured" && "Push keys are not set up on the server."}
        {state.kind === "blocked" &&
          "Notifications are blocked — allow them in browser settings to get reminders."}
        {state.kind === "off" && "Reminders will not reach you until notifications are on."}
        {state.kind === "on" && "Reminders will be delivered to this device."}
        {state.kind === "error" && state.reason}
      </p>

      <div className={styles.actions}>
        {(state.kind === "off" || state.kind === "error") && (
          <button className={styles.button} onClick={enable} disabled={busy}>
            Enable reminders
          </button>
        )}
        {state.kind === "on" && (
          <>
            <button className={styles.button} onClick={test} disabled={busy}>
              Send test
            </button>
            <button className={styles.quiet} onClick={disable} disabled={busy}>
              Turn off
            </button>
          </>
        )}
      </div>

      {note && <p className={styles.note}>{note}</p>}
    </section>
  );
}
