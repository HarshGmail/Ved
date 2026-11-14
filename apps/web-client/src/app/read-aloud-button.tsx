"use client";

import { SpeakerIcon, StopIcon } from "./icons";
import styles from "./chat.module.css";

const READ_LABEL = "Read aloud";
const STOP_LABEL = "Stop reading";

interface ReadAloudButtonProps {
  speaking: boolean;
  note: string | null;
  onToggle: () => void;
}

export function ReadAloudButton({ speaking, note, onToggle }: ReadAloudButtonProps) {
  return (
    <div className={styles.readAloudRow}>
      <button
        type="button"
        className={styles.readAloud}
        onClick={onToggle}
        aria-label={speaking ? STOP_LABEL : READ_LABEL}
        title={note ?? undefined}
        data-speaking={speaking || undefined}
      >
        {speaking ? (
          <>
            <StopIcon className={styles.readAloudIcon} />
            <span className={styles.readAloudWave} aria-hidden="true">
              <span className={styles.readAloudBar} />
              <span className={styles.readAloudBar} />
              <span className={styles.readAloudBar} />
            </span>
          </>
        ) : (
          <SpeakerIcon className={styles.readAloudIcon} />
        )}
      </button>
      {note && <span className={styles.readAloudNote}>{note}</span>}
    </div>
  );
}
