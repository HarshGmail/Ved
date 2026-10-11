"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { type ConversationSummary, connector, HttpError } from "@/connector";
import { Chat } from "./chat";
import { ConversationList } from "./conversation-list";
import { useConversationParam } from "./conversation-url";
import styles from "./conversations.module.css";
import { DocumentShelf, useDocuments } from "./documents";
import { type TranscriptTurn, transcriptToTurns } from "./transcript";

const UNUSABLE_ID_STATUSES = new Set([404, 422]);
const MISSING_CONVERSATION_NOTICE =
  "That conversation no longer exists, so this is a new one.";

type Session =
  | { key: number; conversationId: null; status: "ready"; turns: []; notice?: string }
  | { key: number; conversationId: string; status: "loading" }
  | { key: number; conversationId: string; status: "ready"; turns: TranscriptTurn[] }
  | { key: number; conversationId: string; status: "failed"; reason: string };

interface Listing {
  conversations: ConversationSummary[];
  fetchedAt: number;
  error: string | null;
}

function sessionFor(conversationId: string | null, key: number): Session {
  if (conversationId === null) {
    return { key, conversationId: null, status: "ready", turns: [] };
  }
  return { key, conversationId, status: "loading" };
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function isUnusableId(error: unknown): boolean {
  return error instanceof HttpError && UNUSABLE_ID_STATUSES.has(error.status);
}

export function Conversations() {
  const [paramId, writeParam] = useConversationParam();
  const [seenParamId, setSeenParamId] = useState(paramId);
  const [session, setSession] = useState<Session>(() => sessionFor(paramId, 0));
  const [listing, setListing] = useState<Listing>({
    conversations: [],
    fetchedAt: 0,
    error: null,
  });
  const [panelOpen, setPanelOpen] = useState(false);
  const documents = useDocuments();
  const activeSessionKey = useRef(session.key);

  if (paramId !== seenParamId) {
    setSeenParamId(paramId);
    if (paramId !== session.conversationId) {
      setSession(sessionFor(paramId, session.key + 1));
    }
  }

  const refreshList = useCallback(async () => {
    try {
      const { conversations } = await connector.listConversations();
      setListing({ conversations, fetchedAt: Date.now(), error: null });
    } catch (error: unknown) {
      setListing((current) => ({ ...current, error: describe(error) }));
    }
  }, []);

  useEffect(() => {
    refreshList();
  }, [refreshList]);

  useEffect(() => {
    activeSessionKey.current = session.key;
  }, [session.key]);

  useEffect(() => {
    if (session.status !== "loading") return;
    const { key, conversationId } = session;
    const controller = new AbortController();

    connector
      .readConversation(conversationId, { signal: controller.signal })
      .then((transcript) => {
        setSession((current) =>
          current.key === key
            ? { key, conversationId, status: "ready", turns: transcriptToTurns(transcript) }
            : current,
        );
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (isUnusableId(error)) {
          setSession((current) =>
            current.key === key
              ? {
                  key: key + 1,
                  conversationId: null,
                  status: "ready",
                  turns: [],
                  notice: MISSING_CONVERSATION_NOTICE,
                }
              : current,
          );
          writeParam(null, "replace");
          return;
        }
        setSession((current) =>
          current.key === key
            ? { key, conversationId, status: "failed", reason: describe(error) }
            : current,
        );
      });

    return () => controller.abort();
  }, [session, writeParam]);

  function open(conversationId: string | null) {
    setPanelOpen(false);
    const alreadyShowing =
      conversationId !== null &&
      conversationId === session.conversationId &&
      session.status !== "failed";
    if (alreadyShowing) return;
    setSession(sessionFor(conversationId, session.key + 1));
    if (conversationId !== paramId) writeParam(conversationId, "push");
  }

  function onReply(sessionKey: number, conversationId: string) {
    refreshList();
    const fromAnAbandonedChat = sessionKey !== activeSessionKey.current;
    if (fromAnAbandonedChat) return;
    if (conversationId !== session.conversationId) {
      setSession((current) => ({
        key: current.key,
        conversationId,
        status: "ready",
        turns: [],
      }));
      writeParam(conversationId, paramId === null ? "replace" : "push");
    }
  }

  return (
    <div className={styles.workspace}>
      <button
        className={styles.toggle}
        type="button"
        aria-expanded={panelOpen}
        aria-controls="conversation-panel"
        onClick={() => setPanelOpen((open) => !open)}
      >
        {panelOpen ? "Hide conversations" : "Conversations"}
      </button>

      <aside id="conversation-panel" className={styles.panel} data-open={panelOpen}>
        <ConversationList
          conversations={listing.conversations}
          activeId={session.conversationId}
          now={listing.fetchedAt}
          error={listing.error}
          onSelect={open}
          onNewConversation={() => open(null)}
        />
      </aside>

      <DocumentShelf
        documents={documents.documents}
        uploading={documents.uploading}
        error={documents.error}
        onRemove={documents.remove}
      />

      {session.status === "ready" && session.conversationId === null && session.notice && (
        <p className={styles.notice}>{session.notice}</p>
      )}
      {session.status === "loading" && (
        <p className={styles.notice}>Loading conversation…</p>
      )}
      {session.status === "failed" && (
        <p className={styles.notice} data-tone="error">
          Could not load this conversation — {session.reason}
        </p>
      )}
      {session.status !== "loading" && (
        <Chat
          key={session.key}
          conversationId={session.conversationId ?? undefined}
          initialTurns={session.status === "ready" ? session.turns : []}
          onReply={(conversationId) => onReply(session.key, conversationId)}
          onNewConversation={() => open(null)}
          onDocuments={documents.upload}
        />
      )}
    </div>
  );
}
