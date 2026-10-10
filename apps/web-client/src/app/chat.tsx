"use client";

import { type FormEvent, useRef, useState } from "react";
import {
  type AgentReply,
  connector,
  StreamUnavailableError,
} from "@/connector";
import styles from "./chat.module.css";
import { MarkdownReply } from "./markdown-reply";

type Turn =
  | { role: "user"; text: string }
  | { role: "ved"; reply: AgentReply }
  | { role: "error"; text: string };

type StreamingReply = { text: string; activeTool: string | null };

const PLACEHOLDER = "Ved, remind me at 8 PM to call Mom";
const NOTHING_STREAMED: StreamingReply = { text: "", activeTool: null };

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
        onProgress((current) => ({ ...current, text: current.text + text })),
      onTool: (tool) => onProgress(() => ({ text: "", activeTool: tool.name })),
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

export function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState(false);
  const [streaming, setStreaming] = useState<StreamingReply | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const inputRef = useRef<HTMLInputElement>(null);

  function startNewConversation() {
    setConversationId(undefined);
    setTurns([]);
    inputRef.current?.focus();
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
    <section className={styles.chat}>
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
        {streaming && (streaming.text || streaming.activeTool) && (
          <li className={styles.turn} data-role="ved" aria-live="polite">
            <div className={styles.bubble}>
              {streaming.text && <MarkdownReply text={streaming.text} />}
              {streaming.activeTool && (
                <p className={styles.tools}>using {streaming.activeTool}…</p>
              )}
            </div>
          </li>
        )}
      </ol>

      <form className={styles.form} onSubmit={onSubmit}>
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
