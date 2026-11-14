"use client";

import {
  type DragEvent,
  type FormEvent,
  type ReactNode,
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
import { ArrowUpIcon, MicIcon } from "./icons";
import { MarkdownReply } from "./markdown-reply";
import { ReadAloudButton } from "./read-aloud-button";
import { missingVoiceCopy } from "./speech-voice";
import { type TranscriptTurn, transcriptToTurns } from "./transcript";
import { type EmblemState, VedEmblem } from "./ved-emblem";
import { useReadAloud } from "./use-read-aloud";
import { useSpeechInput } from "./use-speech-input";
import { readVoiceSettings } from "./voice-settings";
import { Welcome } from "./welcome";

type Turn =
  | { role: "user"; text: string }
  | { role: "ved"; reply: AgentReply; readId?: string }
  | { role: "error"; text: string };

type QueuedPrompt = { id: number; text: string };

type StreamingReply = {
  text: string;
  activeTool: string | null;
  thinking: boolean;
  acknowledgement: string | null;
};

const PLACEHOLDER = "Ved, remind me at 8 PM to call Mom";
export const COMPOSER_INPUT_ID = "ved-composer";
const THINKING_LABEL = "thinking…";
const BACKGROUND_PLACEHOLDER = "Ved is still answering…";
const ANSWER_POLL_MS = 3000;
const AVATAR_SIZE = 28;
const DICTATION_BLOCKED_COPY = "Allow microphone access for Ved in your browser settings";
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

function emblemStateFor(reply: StreamingReply): EmblemState {
  return reply.text ? "speaking" : "thinking";
}

function joinWords(first: string, second: string): string {
  return [first.trim(), second.trim()].filter((part) => part.length > 0).join(" ");
}

function dictationNotice(error: string | null): { text: string; tone: "muted" | "danger" } | null {
  if (error === null) return null;
  if (error === "not-allowed" || error === "service-not-allowed") {
    return { text: DICTATION_BLOCKED_COPY, tone: "muted" };
  }
  return { text: `Voice input stopped (${error}).`, tone: "danger" };
}

function readIdFor(turn: Turn, index: number): string {
  return (turn.role === "ved" && turn.readId) || `history-${index}`;
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

function PendingReply({
  state,
  children,
}: {
  state: EmblemState;
  children: ReactNode;
}) {
  return (
    <li className={styles.pendingTurn} data-role="ved" aria-live="polite">
      <VedEmblem
        state={state}
        size={AVATAR_SIZE}
        className={styles.avatar}
      />
      <div className={styles.bubble}>{children}</div>
    </li>
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
  firstName?: string | null;
  onReply?: (conversationId: string) => void;
  onDocuments?: (files: File[]) => void;
}

export function Chat({
  conversationId: initialConversationId,
  initialTurns = [],
  firstName = null,
  onReply,
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
  const [dictationBase, setDictationBase] = useState("");
  const nextQueuedId = useRef(0);
  const nextReadId = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const readAloud = useReadAloud();
  const speakAloud = readAloud.speak;
  const busy = pending || awaitingBackground;
  const showWelcome = turns.length === 0 && !busy && queue.length === 0;

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
        const readId = `reply-${nextReadId.current}`;
        nextReadId.current += 1;
        setConversationId(reply.conversation_id);
        setTurns((current) => [...current, { role: "ved", reply, readId }]);
        if (readVoiceSettings().autoRead) speakAloud(readId, reply.text);
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
    [conversationId, onReply, speakAloud],
  );

  useEffect(() => {
    if (busy || queue.length === 0) return;
    const [next, ...rest] = queue;
    setQueue(rest);
    sendPrompt(next.text);
  }, [busy, queue, sendPrompt]);

  function suggest(suggestion: string) {
    setPrompt(suggestion);
    inputRef.current?.focus();
  }

  function submitText(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    readAloud.stop();
    setPrompt("");

    if (busy || queue.length > 0) {
      const id = nextQueuedId.current++;
      setQueue((current) => [...current, { id, text: trimmed }]);
      return;
    }
    sendPrompt(trimmed);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    submitText(prompt);
  }

  function handleDictationFinal(text: string) {
    const transcript = joinWords(dictationBase, text);
    setPrompt(transcript);
    if (readVoiceSettings().autoSend) submitText(transcript);
  }

  const speech = useSpeechInput(handleDictationFinal);
  const notice = dictationNotice(speech.error);
  const shownPrompt = speech.interim === null ? prompt : joinWords(dictationBase, speech.interim);

  function toggleDictation() {
    if (speech.listening) {
      speech.stop();
      return;
    }
    readAloud.stop();
    setDictationBase(prompt);
    speech.start();
  }

  function toggleReadAloud(readId: string, text: string) {
    if (readAloud.speakingId === readId) {
      readAloud.stop();
      return;
    }
    readAloud.speak(readId, text);
  }

  return (
    <section
      className={styles.chat}
      data-dragging={dragging || undefined}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {showWelcome ? (
        <Welcome firstName={firstName} onPick={suggest} />
      ) : (
        <ol className={styles.turns}>
          {turns.map((turn, index) => {
            const readId = readIdFor(turn, index);
            return (
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
                    {readAloud.supported && turn.reply.text.trim() !== "" && (
                      <ReadAloudButton
                        speaking={readAloud.speakingId === readId}
                        note={
                          readAloud.unvoicedId === readId && readAloud.unvoicedLanguage
                            ? missingVoiceCopy(readAloud.unvoicedLanguage)
                            : null
                        }
                        onToggle={() => toggleReadAloud(readId, turn.reply.text)}
                      />
                    )}
                  </div>
                )}
              </li>
            );
          })}
          {awaitingBackground && (
            <PendingReply state="thinking">
              <TypingIndicator label={BACKGROUND_PLACEHOLDER} />
            </PendingReply>
          )}
          {streaming && (
            <PendingReply state={emblemStateFor(streaming)}>
              {streaming.text ? (
                <MarkdownReply text={streaming.text} />
              ) : (
                <TypingIndicator label={waitingLabel(streaming)} />
              )}
            </PendingReply>
          )}
          {queue.map((item) => (
            <li key={item.id} className={styles.turn} data-role="user">
              <p className={styles.bubble}>
                {item.text} <span className={styles.queued}>queued</span>
              </p>
            </li>
          ))}
        </ol>
      )}

      <form className={styles.composer} onSubmit={onSubmit}>
        <div className={styles.field}>
          {onDocuments && (
            <DocumentPicker className={styles.attach} onFiles={onDocuments} />
          )}
          <input
            ref={inputRef}
            id={COMPOSER_INPUT_ID}
            className={styles.input}
            value={shownPrompt}
            onChange={(event) => setPrompt(event.target.value)}
            readOnly={speech.listening}
            data-interim={speech.interim !== null || undefined}
            placeholder={PLACEHOLDER}
            aria-label="Message Ved"
          />
          {speech.supported && (
            <button
              type="button"
              className={styles.mic}
              data-listening={speech.listening || undefined}
              aria-label={speech.listening ? "Stop listening" : "Speak"}
              onClick={toggleDictation}
            >
              <MicIcon className={styles.micIcon} />
            </button>
          )}
          <button className={styles.send} type="submit" aria-label="Send">
            <ArrowUpIcon className={styles.sendIcon} />
          </button>
        </div>
        {notice && (
          <p className={styles.notice} data-tone={notice.tone} role="status">
            {notice.text}
          </p>
        )}
      </form>
    </section>
  );
}
