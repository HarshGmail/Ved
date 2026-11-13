"use client";

import {
  type DragEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  type AgentReply,
  connector,
  StreamUnavailableError,
} from "@/connector";
import styles from "./chat.module.css";
import { DocumentPicker } from "./documents";
import { MarkdownReply } from "./markdown-reply";
import { type TranscriptTurn, transcriptToTurns } from "./transcript";

type Turn =
  | { role: "user"; text: string }
  | { role: "ved"; reply: AgentReply }
  | { role: "error"; text: string };

type QueuedPrompt = { id: number; text: string };

type StreamingReply = {
  text: string;
  activeTool: string | null;
  thinking: boolean;
  acknowledgement: string | null;
};

const PLACEHOLDER = "Ved, remind me at 8 PM to call Mom";
const THINKING_LABEL = "thinking…";
const BACKGROUND_PLACEHOLDER = "Ved is still answering…";
const ANSWER_POLL_MS = 3000;
const NOTHING_STREAMED: StreamingReply = {
  text: "",
  activeTool: null,
  thinking: false,
  acknowledgement: null,
};

function carriesFiles(event: DragEvent): boolean {
  return event.dataTransfer.types.includes("Files");
}

function waitingLabel(reply: StreamingReply): string | null {
  if (reply.activeTool) return `using ${reply.activeTool}…`;
  if (reply.acknowledgement) return reply.acknowledgement;
  if (reply.thinking) return THINKING_LABEL;
  return null;
}

function TypingIndicator({ label }: { label?: string | null }) {
  return (
    <p className={styles.typing} role="status" aria-label="Ved is typing">
      <span className={styles.dots} aria-hidden="true">
        <span className={styles.dot} />
        <span className={styles.dot} />
        <span className={styles.dot} />
      </span>
      {label && <span className={styles.typingLabel}>{label}</span>}
    </p>
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
  const [queue, setQueue] = useState<QueuedPrompt[]>([]);
  const [awaitingBackground, setAwaitingBackground] = useState(false);
  const nextQueuedId = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = pending || awaitingBackground;

  useEffect(() => {
    if (!initialConversationId) return;
    const watchedId = initialConversationId;
    let cancelled = false;
    let followed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function checkAnswering() {
      try {
        const { answering } = await connector.conversationStatus(watchedId);
        if (cancelled) return;
        if (answering) {
          followed = true;
          setAwaitingBackground(true);
          timer = setTimeout(checkAnswering, ANSWER_POLL_MS);
          return;
        }
        if (!followed) return;
        const transcript = await connector.readConversation(watchedId);
        if (cancelled) return;
        setTurns(transcriptToTurns(transcript));
        setAwaitingBackground(false);
      } catch {
        if (!cancelled) setAwaitingBackground(false);
      }
    }

    checkAnswering();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [initialConversationId]);

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

  const sendPrompt = useCallback(
    async (text: string) => {
      setTurns((current) => [...current, { role: "user", text }]);
      setPending(true);
      setStreaming(NOTHING_STREAMED);

      try {
        const reply = await requestReply(text, conversationId, (update) =>
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
    },
    [conversationId, onReply],
  );

  useEffect(() => {
    if (busy || queue.length === 0) return;
    const [next, ...rest] = queue;
    setQueue(rest);
    sendPrompt(next.text);
  }, [busy, queue, sendPrompt]);

  function startNewConversation() {
    setConversationId(undefined);
    setTurns([]);
    inputRef.current?.focus();
    onNewConversation?.();
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed) return;
    setPrompt("");

    if (busy || queue.length > 0) {
      const id = nextQueuedId.current++;
      setQueue((current) => [...current, { id, text: trimmed }]);
      return;
    }
    sendPrompt(trimmed);
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
            disabled={busy}
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
        {awaitingBackground && (
          <li className={styles.turn} data-role="ved" aria-live="polite">
            <div className={styles.bubble}>
              <TypingIndicator label={BACKGROUND_PLACEHOLDER} />
            </div>
          </li>
        )}
        {streaming && (
          <li className={styles.turn} data-role="ved" aria-live="polite">
            <div className={styles.bubble}>
              {streaming.text ? (
                <MarkdownReply text={streaming.text} />
              ) : (
                <TypingIndicator label={waitingLabel(streaming)} />
              )}
            </div>
          </li>
        )}
        {queue.map((item) => (
          <li key={item.id} className={styles.turn} data-role="user">
            <p className={styles.bubble}>
              {item.text} <span className={styles.queued}>queued</span>
            </p>
          </li>
        ))}
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
        />
        <button className={styles.send} type="submit">
          Send
        </button>
      </form>
    </section>
  );
}
