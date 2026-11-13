"use client";

import Image from "next/image";
import { useState, useSyncExternalStore } from "react";
import {
  INSTALL_READY_EVENT,
  type InstallPromptEvent,
  type InstallWindow,
  isIosDevice,
  isSnoozed,
  isStandalone,
  promptInstall,
  snoozeInstallBanner,
} from "./install-prompt";
import styles from "./install-banner.module.css";

export type InstallOffer = { kind: "prompt"; event: InstallPromptEvent } | { kind: "ios" };

function ignoreSubscription(): () => void {
  return () => {};
}

function subscribeToInstallEvents(onChange: () => void): () => void {
  const forgetPrompt = () => {
    (window as InstallWindow).__vedInstallPrompt = undefined;
    onChange();
  };
  window.addEventListener(INSTALL_READY_EVENT, onChange);
  window.addEventListener("appinstalled", forgetPrompt);
  return () => {
    window.removeEventListener(INSTALL_READY_EVENT, onChange);
    window.removeEventListener("appinstalled", forgetPrompt);
  };
}

function readCapturedPrompt(): InstallPromptEvent | null {
  return (window as InstallWindow).__vedInstallPrompt ?? null;
}

function noCapturedPrompt(): InstallPromptEvent | null {
  return null;
}

function readSnoozed(): boolean {
  return isSnoozed(Date.now());
}

function alwaysTrue(): boolean {
  return true;
}

function neverTrue(): boolean {
  return false;
}

export function useInstallOffer(): { installed: boolean; offer: InstallOffer | null } {
  const capturedPrompt = useSyncExternalStore(subscribeToInstallEvents, readCapturedPrompt, noCapturedPrompt);
  const iosBrowserTab = useSyncExternalStore(ignoreSubscription, isIosDevice, neverTrue);
  const installed = useSyncExternalStore(ignoreSubscription, isStandalone, neverTrue);

  const offer: InstallOffer | null = capturedPrompt
    ? { kind: "prompt", event: capturedPrompt }
    : iosBrowserTab
      ? { kind: "ios" }
      : null;
  return { installed, offer };
}

export function InstallBanner() {
  const { installed, offer } = useInstallOffer();
  const snoozed = useSyncExternalStore(ignoreSubscription, readSnoozed, alwaysTrue);
  const [dismissed, setDismissed] = useState(false);

  if (installed || snoozed || dismissed || !offer) return null;

  const dismiss = () => {
    snoozeInstallBanner(Date.now());
    setDismissed(true);
  };

  const install = async (event: InstallPromptEvent) => {
    await promptInstall(event);
    dismiss();
  };

  return (
    <div role="status" className={styles.banner}>
      <div className={styles.inner}>
        <Image src="/icon-192.png" alt="" width={32} height={32} className={styles.icon} />
        <p className={styles.message}>
          {offer.kind === "prompt" ? (
            <>
              Install <strong>Ved</strong> for a home screen icon, full screen and quicker opening.
            </>
          ) : (
            <>
              Add <strong>Ved</strong> to your home screen: tap <strong>Share</strong>, then <strong>Add to Home Screen</strong>.
            </>
          )}
        </p>
        {offer.kind === "prompt" && (
          <button type="button" onClick={() => install(offer.event)} className={styles.install}>
            Install
          </button>
        )}
        <button type="button" onClick={dismiss} aria-label="Hide for 14 days" className={styles.dismiss}>
          ✕
        </button>
      </div>
    </div>
  );
}
