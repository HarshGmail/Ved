"use client";

import Link from "next/link";
import { type ReactNode, useSyncExternalStore } from "react";
import { BackendStatusLine } from "../backend-status";
import { ConnectionsPanel } from "../connections-panel";
import { ChevronLeftIcon } from "../icons";
import { useInstallOffer } from "../install-banner";
import { promptInstall } from "../install-prompt";
import { Notifications } from "../notifications";
import {
  readThemeChoice,
  subscribeToThemeChanges,
  THEME_CHOICES,
  type ThemeChoice,
  writeThemeChoice,
} from "../theme";
import { usePerson } from "../use-person";
import styles from "./settings.module.css";

const THEME_LABELS: Record<ThemeChoice, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
};
const INSTALLED_COPY = "Installed. Ved opens full screen from this device's home screen.";
const PROMPT_COPY = "Install Ved for a home screen icon, a full-screen view and quicker opening.";
const IOS_COPY = "Tap Share in Safari, then Add to Home Screen.";
const FALLBACK_COPY = "Use your browser menu and choose Install app or Add to Home Screen.";

function serverTheme(): ThemeChoice {
  return "system";
}

function SettingsSection({
  id,
  title,
  plain = false,
  children,
}: {
  id: string;
  title: string;
  plain?: boolean;
  children: ReactNode;
}) {
  const headingId = `${id}-heading`;
  return (
    <section
      id={id}
      className={plain ? styles.plain : styles.card}
      aria-labelledby={headingId}
    >
      <h2 id={headingId} className={styles.cardTitle}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function InstallSection() {
  const { installed, offer } = useInstallOffer();

  if (installed) return <p className={styles.text}>{INSTALLED_COPY}</p>;
  if (offer?.kind === "prompt") {
    return (
      <>
        <p className={styles.text}>{PROMPT_COPY}</p>
        <button
          className={styles.primary}
          type="button"
          onClick={() => promptInstall(offer.event)}
        >
          Install
        </button>
      </>
    );
  }
  return <p className={styles.text}>{offer?.kind === "ios" ? IOS_COPY : FALLBACK_COPY}</p>;
}

function AppearanceSection() {
  const choice = useSyncExternalStore(subscribeToThemeChanges, readThemeChoice, serverTheme);

  return (
    <fieldset className={styles.segments}>
      <legend className={styles.visuallyHidden}>Theme</legend>
      <div className={styles.segmentRow}>
        {THEME_CHOICES.map((option) => (
          <label
            key={option}
            className={styles.segment}
            data-checked={option === choice || undefined}
          >
            <input
              className={styles.radio}
              type="radio"
              name="theme"
              value={option}
              checked={option === choice}
              onChange={() => writeThemeChoice(option)}
            />
            {THEME_LABELS[option]}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function AboutLines() {
  const person = usePerson();

  return (
    <footer className={styles.about}>
      <BackendStatusLine />
      {person && <p>{person.email}</p>}
    </footer>
  );
}

export function SettingsPanel() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.back} aria-label="Back to Ved">
          <ChevronLeftIcon className={styles.backIcon} />
        </Link>
        <h1 className={styles.title}>Settings</h1>
      </header>

      <SettingsSection id="integrations" title="Integrations" plain>
        <ConnectionsPanel />
      </SettingsSection>

      <SettingsSection id="notifications" title="Notifications">
        <Notifications />
      </SettingsSection>

      <SettingsSection id="install" title="Install app">
        <InstallSection />
      </SettingsSection>

      <SettingsSection id="appearance" title="Appearance">
        <AppearanceSection />
      </SettingsSection>

      <AboutLines />
    </main>
  );
}
