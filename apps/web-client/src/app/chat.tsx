"use client";

import { type DragEvent, type FormEvent, useRef, useState } from "react";
import {
  type AgentReply,
  connector,
  StreamUnavailableError,
} from "@/connector";
import styles from "./chat.module.css";
import { DocumentPicker } from "./documents";
import { MarkdownReply } from "./markdown-reply";
import type { TranscriptTurn } from "./transcript";

type Turn =
  | { role: "user"; text: string }
  | { role: "ved"; reply: AgentReply }
  | { role: "error"; text: string };

type StreamingReply = {
  text: string;
  activeTool: string | null;
  thinking: boolean;
  acknowledgement: string | null;
};

const PLACEHOLDER = "Ved, remind me at 8 PM to call Mom";
const THINKING_LABEL = "thinking…";
const NOTHING_STREAMED: StreamingReply = {
  text: "",
  activeTool: null,
  thinking: false,
  acknowledgement: null,
};

function carriesFiles(event: DragEvent): boolean {
  return event.dataTransfer.types.includes("Files");
}

function hasSomethingToShow(reply: StreamingReply): boolean {
  return Boolean(
    reply.text || reply.activeTool || reply.thinking || reply.acknowledgement,
  );
}

function toolLabel(reply: AgentReply): string | null {
  if (reply.tool_calls.length === 0) return null;
  return reply.tool_calls
    .map((call) => (call.failed ? `${call.name} (failed)` : call.name))
    .join(", ");
}

async function requestReply(
  prompt: string,
  conversationId: string | undefined,
  onProgress: (update: (current: StreamingReply) => StreamingReply) => void,
): Promise<AgentReply> {
  try {
    return await connector.streamMessage(prompt, conversationId, {
      onToken: (text) =>
        onProgress((current) => ({
          ...current,
          text: current.text + text,
          thinking: false,
          acknowledgement: null,
        })),
      onThinking: () =>
        onProgress((current) => ({ ...current, thinking: true })),
      onAcknowledgement: ({ text }) =>
        onProgress((current) => ({
          ...current,
          acknowledgement: text,
          thinking: false,
        })),
      onTool: (tool) =>
        onProgress((current) => ({
          ...current,
          text: "",
          activeTool: tool.name,
          thinking: false,
        })),
      onToolResult: () =>
        onProgress((current) => ({ ...current, activeTool: null })),
    });
  } catch (error: unknown) {
    if (error instanceof StreamUnavailableError) {
      return connector.sendMessage(prompt, conversationId);
    }
    throw error;
  }
}

interface ChatProps {
  conversationId?: string;
  initialTurns?: TranscriptTurn[];
  onReply?: (conversationId: string) => void;
  onNewConversation?: () => void;
  onDocuments?: (files: File[]) => void;
}

export function Chat({
  conversationId: initialConversationId,
  initialTurns = [],
  onReply,
  onNewConversation,
  onDocuments,
}: ChatProps) {
  const [turns, setTurns] = useState<Turn[]>(initialTurns);
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState(false);
  const [streaming, setStreaming] = useState<StreamingReply | null>(null);
  const [conversationId, setConversationId] = useState(initialConversationId);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function onDragOver(event: DragEvent) {
    if (!onDocuments || !carriesFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDragging(true);
  }

  function onDragLeave(event: DragEvent) {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    setDragging(false);
  }

  function onDrop(event: DragEvent) {
    if (!onDocuments || !carriesFiles(event)) return;
    event.preventDefault();
    setDragging(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) onDocuments(files);
  }

  function startNewConversation() {
    setConversationId(undefined);
    setTurns([]);
    inputRef.current?.focus();
    onNewConversation?.();
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed || pending) return;

    setTurns((current) => [...current, { role: "user", text: trimmed }]);
    setPrompt("");
    setPending(true);
    setStreaming(NOTHING_STREAMED);

    try {
      const reply = await requestReply(trimmed, conversationId, (update) =>
        setStreaming((current) => update(current ?? NOTHING_STREAMED)),
      );
      setConversationId(reply.conversation_id);
      setTurns((current) => [...current, { role: "ved", reply }]);
      onReply?.(reply.conversation_id);
    } catch (error: unknown) {
      setTurns((current) => [
        ...current,
        {
          role: "error",
          text: error instanceof Error ? error.message : "Request failed",
        },
      ]);
    } finally {
      setStreaming(null);
      setPending(false);
      inputRef.current?.focus();
    }
  }

  return (
    <section
      className={styles.chat}
      data-dragging={dragging || undefined}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {turns.length > 0 && (
        <div className={styles.toolbar}>
          <span className={styles.thread}>
            {conversationId ? "remembering this thread" : "new thread"}
          </span>
          <button
            className={styles.reset}
            type="button"
            onClick={startNewConversation}
            disabled={pending}
          >
            New conversation
          </button>
        </div>
      )}

      <ol className={styles.turns}>
        {turns.map((turn, index) => (
          <li key={index} className={styles.turn} data-role={turn.role}>
            {turn.role === "user" && <p className={styles.bubble}>{turn.text}</p>}
            {turn.role === "error" && (
              <p className={styles.bubble}>{turn.text}</p>
            )}
            {turn.role === "ved" && (
              <div className={styles.bubble}>
                <MarkdownReply text={turn.reply.text} />
                {toolLabel(turn.reply) && (
                  <p className={styles.tools}>{toolLabel(turn.reply)}</p>
                )}
              </div>
            )}
          </li>
        ))}
        {streaming && hasSomethingToShow(streaming) && (
          <li className={styles.turn} data-role="ved" aria-live="polite">
            <div className={styles.bubble}>
              {streaming.text && <MarkdownReply text={streaming.text} />}
              {!streaming.text && streaming.acknowledgement && (
                <p className={styles.status}>{streaming.acknowledgement}</p>
              )}
              {!streaming.text &&
                !streaming.acknowledgement &&
                streaming.thinking && (
                  <p className={styles.status}>{THINKING_LABEL}</p>
                )}
              {streaming.activeTool && (
                <p className={styles.tools}>using {streaming.activeTool}…</p>
              )}
            </div>
          </li>
        )}
      </ol>

      <form className={styles.form} onSubmit={onSubmit}>
        {onDocuments && (
          <DocumentPicker className={styles.attach} onFiles={onDocuments} />
        )}
        <input
          ref={inputRef}
          className={styles.input}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder={PLACEHOLDER}
          aria-label="Message Ved"
          disabled={pending}
        />
        <button className={styles.send} type="submit" disabled={pending}>
          {pending ? "…" : "Send"}
        </button>
      </form>
    </section>
  );
}
