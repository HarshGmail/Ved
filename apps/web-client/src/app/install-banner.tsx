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
  snoozeInstallBanner,
} from "./install-prompt";
import styles from "./install-banner.module.css";

type InstallOffer = { kind: "prompt"; event: InstallPromptEvent } | { kind: "ios" };

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

function readHiddenByPlatform(): boolean {
  return isStandalone() || isSnoozed(Date.now());
}

function alwaysHidden(): boolean {
  return true;
}

function neverIos(): boolean {
  return false;
}

export function InstallBanner() {
  const capturedPrompt = useSyncExternalStore(subscribeToInstallEvents, readCapturedPrompt, noCapturedPrompt);
  const iosBrowserTab = useSyncExternalStore(ignoreSubscription, isIosDevice, neverIos);
  const hiddenByPlatform = useSyncExternalStore(ignoreSubscription, readHiddenByPlatform, alwaysHidden);
  const [dismissed, setDismissed] = useState(false);

  if (hiddenByPlatform || dismissed) return null;

  const offer: InstallOffer | null = capturedPrompt
    ? { kind: "prompt", event: capturedPrompt }
    : iosBrowserTab
      ? { kind: "ios" }
      : null;
  if (!offer) return null;

  const dismiss = () => {
    snoozeInstallBanner(Date.now());
    setDismissed(true);
  };

  const install = async (event: InstallPromptEvent) => {
    await event.prompt();
    await event.userChoice;
    (window as InstallWindow).__vedInstallPrompt = undefined;
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
