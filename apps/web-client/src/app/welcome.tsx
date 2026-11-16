"use client";

import { useSyncExternalStore } from "react";
import { TalkIcon } from "./icons";
import styles from "./welcome.module.css";
import { VedEmblem } from "./ved-emblem";

const SUGGESTIONS = [
  "What's on my plan today?",
  "How much did I spend this month?",
  "Remind me to call Amma tomorrow at 9",
  "What do you remember about me?",
];

const WELCOME_EMBLEM_SIZE = 96;
const MORNING_ENDS_AT_HOUR = 12;
const AFTERNOON_ENDS_AT_HOUR = 18;
const SERVER_GREETING = "Hello";
const TALK_LABEL = "Talk to Ved";

function partOfDay(hour: number): string {
  if (hour < MORNING_ENDS_AT_HOUR) return "Good morning";
  if (hour < AFTERNOON_ENDS_AT_HOUR) return "Good afternoon";
  return "Good evening";
}

function ignoreSubscription(): () => void {
  return () => {};
}

function currentGreeting(): string {
  return partOfDay(new Date().getHours());
}

function serverGreeting(): string {
  return SERVER_GREETING;
}

interface WelcomeProps {
  firstName: string | null;
  onPick: (suggestion: string) => void;
  onTalk?: () => void;
}

export function Welcome({ firstName, onPick, onTalk }: WelcomeProps) {
  const period = useSyncExternalStore(ignoreSubscription, currentGreeting, serverGreeting);
  const greeting = firstName ? `${period}, ${firstName}` : period;

  return (
    <section className={styles.welcome} aria-label="Start a conversation">
      <VedEmblem state="idle" size={WELCOME_EMBLEM_SIZE} />
      <h1 className={styles.greeting}>{greeting}</h1>
      {onTalk && (
        <button className={styles.talk} type="button" onClick={onTalk}>
          <TalkIcon className={styles.talkIcon} />
          {TALK_LABEL}
        </button>
      )}
      <ul className={styles.suggestions}>
        {SUGGESTIONS.map((suggestion) => (
          <li key={suggestion}>
            <button className={styles.chip} type="button" onClick={() => onPick(suggestion)}>
              {suggestion}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
