"use client";

import Link from "next/link";
import { BackendStatus } from "./backend-status";
import { GearIcon, ListIcon, PenIcon } from "./icons";
import styles from "./top-bar.module.css";
import { VedEmblem } from "./ved-emblem";

const BRAND_EMBLEM_SIZE = 28;
const CONVERSATION_PANEL_ID = "conversation-panel";

interface TopBarProps {
  conversationsOpen: boolean;
  onToggleConversations: () => void;
  onNewConversation: () => void;
}

export function TopBar({ conversationsOpen, onToggleConversations, onNewConversation }: TopBarProps) {
  return (
    <header className={styles.bar}>
      <div className={styles.brand}>
        <VedEmblem state="idle" size={BRAND_EMBLEM_SIZE} />
        <span className={styles.name}>Ved</span>
        <BackendStatus />
      </div>

      <div className={styles.actions}>
        <button
          className={`${styles.button} ${styles.conversationsButton}`}
          type="button"
          aria-label="Conversations"
          aria-expanded={conversationsOpen}
          aria-controls={CONVERSATION_PANEL_ID}
          onClick={onToggleConversations}
        >
          <ListIcon className={styles.icon} />
        </button>
        <button
          className={styles.button}
          type="button"
          aria-label="New conversation"
          onClick={onNewConversation}
        >
          <PenIcon className={styles.icon} />
        </button>
        <Link href="/settings" className={styles.button} aria-label="Settings">
          <GearIcon className={styles.icon} />
        </Link>
      </div>
    </header>
  );
}
