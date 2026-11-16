"use client";

import { useEffect, useRef, useState } from "react";
import type { AgentReply } from "@/connector";
import styles from "./talk-mode.module.css";
import { type EmblemState, VedEmblem } from "./ved-emblem";
import { type TalkPhase, type TalkState, type TalkTurnHandlers, createTalkSession, INITIAL_TALK_STATE, type TalkSession } from "./talk-session";
import { toSpeakableText } from "./speech-text";

interface TalkOverlayProps {
  ask: (prompt: string, handlers: TalkTurnHandlers) => Promise<AgentReply | null>;
  isBusy: () => boolean;
  onClose: () => void;
}

const EMBLEM_SIZE = 200;
const LEVEL_SMOOTHING = 0.35;
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const CLOSE_KEY = "Escape";

const PHASE_LABELS: Record<TalkPhase, string> = {
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  paused: "Tap to talk",
};

const EMBLEM_STATES: Record<TalkPhase, EmblemState> = {
  listening: "idle",
  thinking: "thinking",
  speaking: "speaking",
  paused: "idle",
};

function emblemLabel(phase: TalkPhase): string {
  if (phase === "paused") return "Tap to talk";
  if (phase === "thinking" || phase === "speaking") return "Interrupt Ved and talk";
  return "Ved is listening";
}

function prefersReducedMotion(): boolean {
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

export function TalkOverlay({ ask, isBusy, onClose }: TalkOverlayProps) {
  const [talk, setTalk] = useState<TalkState>(INITIAL_TALK_STATE);
  const rootRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLButtonElement>(null);
  const sessionRef = useRef<TalkSession | null>(null);
  const askRef = useRef(ask);
  const closeRef = useRef(onClose);

  useEffect(() => {
    askRef.current = ask;
    closeRef.current = onClose;
  });

  useEffect(() => {
    const session = createTalkSession({
      ask: (prompt, handlers) => askRef.current(prompt, handlers),
      isBusy,
      emit: (patch) => setTalk((current) => ({ ...current, ...patch })),
    });
    sessionRef.current = session;
    session.start();

    const closeWhenHidden = () => {
      if (document.hidden) closeRef.current();
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === CLOSE_KEY) closeRef.current();
    };
    document.addEventListener("visibilitychange", closeWhenHidden);
    window.addEventListener("keydown", closeOnEscape);
    endRef.current?.focus({ preventScroll: true });

    return () => {
      document.removeEventListener("visibilitychange", closeWhenHidden);
      window.removeEventListener("keydown", closeOnEscape);
      session.end();
      sessionRef.current = null;
    };
  }, [isBusy]);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    let frame = 0;
    let smoothed = 0;
    const tick = () => {
      const raw = sessionRef.current?.readLevel() ?? 0;
      smoothed += (raw - smoothed) * LEVEL_SMOOTHING;
      rootRef.current?.style.setProperty("--level", smoothed.toFixed(3));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  const phase = talk.phase;
  const status = talk.notice ?? PHASE_LABELS[phase];
  const replyCaption = toSpeakableText(talk.reply);

  return (
    <div
      ref={rootRef}
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label="Talk to Ved"
      data-phase={phase}
    >
      <div className={styles.stage}>
        <span className={styles.ring} data-ring="inner" aria-hidden="true" />
        <span className={styles.ring} data-ring="middle" aria-hidden="true" />
        <span className={styles.ring} data-ring="outer" aria-hidden="true" />
        <button
          type="button"
          className={styles.emblemButton}
          aria-label={emblemLabel(phase)}
          onClick={() => sessionRef.current?.interrupt()}
        >
          <VedEmblem state={EMBLEM_STATES[phase]} size={EMBLEM_SIZE} />
        </button>
      </div>

      <p className={styles.status} role="status">
        {status}
      </p>

      {talk.audioHeld && (
        <button type="button" className={styles.hear} onClick={() => sessionRef.current?.hearAgain()}>
          Tap to hear
        </button>
      )}

      <div className={styles.captions}>
        {talk.heard && (
          <p key={talk.heard} className={styles.heard}>
            {talk.heard}
          </p>
        )}
        {replyCaption && <p className={styles.reply}>{replyCaption}</p>}
      </div>

      <button
        ref={endRef}
        type="button"
        className={styles.end}
        onClick={() => closeRef.current()}
      >
        End
      </button>
    </div>
  );
}
