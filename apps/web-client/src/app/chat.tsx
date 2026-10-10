"use client";

import { type FormEvent, useRef, useState } from "react";
import { type AgentReply, connector } from "@/connector";
import styles from "./chat.module.css";
import { MarkdownReply } from "./markdown-reply";

type Turn =
  | { role: "user"; text: string }
  | { role: "ved"; reply: AgentReply }
  | { role: "error"; text: string };

const PLACEHOLDER = "Ved, remind me at 8 PM to call Mom";

function toolLabel(reply: AgentReply): string | null {
  if (reply.tool_calls.length === 0) return null;
  return reply.tool_calls
    .map((call) => (call.failed ? `${call.name} (failed)` : call.name))
    .join(", ");
}

export function Chat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState(false);
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

    try {
      const reply = await connector.sendMessage(trimmed, conversationId);
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
