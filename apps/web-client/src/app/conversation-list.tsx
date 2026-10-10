"use client";

import type { ConversationSummary } from "@/connector";
import styles from "./conversation-list.module.css";
import { relativeTime } from "./relative-time";

const UNTITLED = "Untitled conversation";

interface ConversationListProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  now: number;
  error: string | null;
  onSelect: (conversationId: string) => void;
  onNewConversation: () => void;
}

export function ConversationList({
  conversations,
  activeId,
  now,
  error,
  onSelect,
  onNewConversation,
}: ConversationListProps) {
  return (
    <nav className={styles.list} aria-label="Conversations">
      <button className={styles.new} type="button" onClick={onNewConversation}>
        New conversation
      </button>

      {error && <p className={styles.note}>{error}</p>}
      {!error && conversations.length === 0 && (
        <p className={styles.note}>No conversations yet.</p>
      )}

      <ol className={styles.items}>
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            <button
              className={styles.item}
              type="button"
              aria-current={conversation.id === activeId ? "page" : undefined}
              onClick={() => onSelect(conversation.id)}
            >
              <span className={styles.title}>{conversation.title || UNTITLED}</span>
              <time className={styles.when} dateTime={conversation.last_message_at}>
                {relativeTime(conversation.last_message_at, now)}
              </time>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
