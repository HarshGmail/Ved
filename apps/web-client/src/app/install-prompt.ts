export const INSTALL_READY_EVENT = "ved-install-ready";
export const INSTALL_SNOOZE_KEY = "ved.install-banner.snoozed-until";

const SNOOZE_DAYS = 14;
const DAY_MS = 24 * 60 * 60 * 1000;

export const INSTALL_CAPTURE_SCRIPT = `window.addEventListener("beforeinstallprompt",function(e){e.preventDefault();window.__vedInstallPrompt=e;window.dispatchEvent(new Event("${INSTALL_READY_EVENT}"))});`;

export interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export type InstallWindow = Window & { __vedInstallPrompt?: InstallPromptEvent };

type NavigatorWithStandalone = Navigator & { standalone?: boolean };

export function isStandalone(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches || (navigator as NavigatorWithStandalone).standalone === true;
}

export function isIosDevice(): boolean {
  const isIphoneOrIpad = /iPad|iPhone|iPod/.test(navigator.userAgent);
  const isIpadDesktopMode = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  return isIphoneOrIpad || isIpadDesktopMode;
}

export function isSnoozed(now: number): boolean {
  try {
    return Number(localStorage.getItem(INSTALL_SNOOZE_KEY) ?? 0) > now;
  } catch {
    return false;
  }
}

export function snoozeInstallBanner(now: number): void {
  try {
    localStorage.setItem(INSTALL_SNOOZE_KEY, String(now + SNOOZE_DAYS * DAY_MS));
  } catch {}
}

export async function promptInstall(event: InstallPromptEvent): Promise<void> {
  await event.prompt();
  await event.userChoice;
  (window as InstallWindow).__vedInstallPrompt = undefined;
}
