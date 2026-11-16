import { type AgentReply, connector } from "@/connector";
import { createSpeechStream, type SpeechStream } from "./speech-stream";
import { currentVoiceStatus, speechOptionsFor } from "./voice-status";
import { getVoicePlayer } from "./voice-player";
import { listenForUtterance, MicrophoneUnavailableError, type Utterance } from "./voice-recording";
import { readVoiceSettings, transcriptionLanguageFor } from "./voice-settings";

export type TalkPhase = "listening" | "thinking" | "speaking" | "paused";

export interface TalkState {
  phase: TalkPhase;
  heard: string | null;
  reply: string;
  notice: string | null;
}

export interface TalkTurnHandlers {
  onToken: (text: string) => void;
  onSegmentBreak: () => void;
}

export interface TalkDependencies {
  ask: (prompt: string, handlers: TalkTurnHandlers) => Promise<AgentReply | null>;
  isBusy: () => boolean;
  emit: (patch: Partial<TalkState>) => void;
}

export interface TalkSession {
  start: () => void;
  interrupt: () => void;
  end: () => void;
  readLevel: () => number;
}

interface Turn {
  stream: SpeechStream;
  finished: Promise<void>;
  resolve: () => void;
  speaking: boolean;
}

export const INITIAL_TALK_STATE: TalkState = {
  phase: "listening",
  heard: null,
  reply: "",
  notice: null,
};

const MAX_EMPTY_LISTENS = 2;
const BUSY_POLL_MS = 150;
const SILENT_LISTEN_COPY = "Tap to talk";
const TRANSCRIPTION_FAILED_COPY = "Ved couldn't make out that. Try again.";
const REPLY_FAILED_COPY = "Ved couldn't answer that. Try again.";
const RESOLVED: Promise<void> = Promise.resolve();

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function microphoneNotice(error: unknown): string {
  return error instanceof MicrophoneUnavailableError ? error.message : "Ved can't use the microphone";
}

export function createTalkSession(deps: TalkDependencies): TalkSession {
  const player = getVoicePlayer();
  let running = false;
  let loopId = 0;
  let micLevel = 0;
  let emptyListens = 0;
  let listening: { cancel: () => void } | null = null;
  let turn: Turn | null = null;
  let settled: Promise<void> = RESOLVED;

  const isCurrent = (id: number) => running && id === loopId;

  function captureUtterance(): Promise<Utterance> {
    const capture = listenForUtterance((level) => {
      micLevel = level;
    });
    listening = capture;
    return capture.result.finally(() => {
      if (listening === capture) listening = null;
      micLevel = 0;
    });
  }

  async function transcribe(blob: Blob): Promise<string> {
    const { text } = await connector.transcribe(
      blob,
      transcriptionLanguageFor(readVoiceSettings().listenLang),
    );
    return text.trim();
  }

  function pause(notice: string | null): void {
    running = false;
    loopId += 1;
    deps.emit({ phase: "paused", notice });
  }

  function countEmptyListen(): boolean {
    emptyListens += 1;
    if (emptyListens < MAX_EMPTY_LISTENS) return false;
    pause(SILENT_LISTEN_COPY);
    return true;
  }

  async function waitUntilChatIdle(current: Turn): Promise<void> {
    while (deps.isBusy() && turn === current) {
      await delay(BUSY_POLL_MS);
    }
  }

  function endTurn(current: Turn): void {
    current.resolve();
    if (turn === current) turn = null;
  }

  function startTurn(prompt: string): void {
    let resolveFinished: () => void = () => undefined;
    const finished = new Promise<void>((resolve) => {
      resolveFinished = resolve;
    });
    const stream: SpeechStream = createSpeechStream(
      player,
      speechOptionsFor(readVoiceSettings(), currentVoiceStatus()),
      () => {
        if (turn === null || turn.stream !== stream) return;
        turn.speaking = true;
        deps.emit({ phase: "speaking" });
      },
    );
    const current: Turn = { stream, finished, resolve: resolveFinished, speaking: false };
    turn = current;
    settled = finished;

    let shownReply = "";
    const handlers: TalkTurnHandlers = {
      onToken: (token) => {
        if (turn !== current) return;
        shownReply += token;
        stream.push(token);
        deps.emit({ reply: shownReply });
      },
      onSegmentBreak: () => {
        if (turn !== current) return;
        stream.breakSegment();
        shownReply = "";
        deps.emit({ reply: "" });
      },
    };

    void (async () => {
      try {
        await waitUntilChatIdle(current);
        if (turn !== current) return;
        const reply = await deps.ask(prompt, handlers);
        if (turn !== current) return;
        if (reply === null) deps.emit({ notice: REPLY_FAILED_COPY });
        await stream.finish();
      } finally {
        endTurn(current);
      }
    })();
  }

  async function listenLoop(id: number): Promise<void> {
    while (isCurrent(id)) {
      await settled;
      if (!isCurrent(id)) return;
      deps.emit({ phase: "listening" });

      let utterance: Utterance;
      try {
        utterance = await captureUtterance();
      } catch (error: unknown) {
        if (isCurrent(id)) pause(microphoneNotice(error));
        return;
      }
      if (!isCurrent(id)) return;
      if (utterance.kind === "silence") {
        if (countEmptyListen()) return;
        continue;
      }

      deps.emit({ phase: "thinking" });
      const heard = await transcribe(utterance.blob).catch(() => null);
      if (!isCurrent(id)) return;
      if (heard === null || heard === "") {
        deps.emit({ notice: TRANSCRIPTION_FAILED_COPY });
        if (countEmptyListen()) return;
        continue;
      }

      emptyListens = 0;
      deps.emit({ heard, reply: "", notice: null });
      startTurn(heard);
    }
  }

  function begin(): void {
    if (running) return;
    running = true;
    emptyListens = 0;
    loopId += 1;
    player.unlock();
    deps.emit({ phase: "listening", notice: null });
    void listenLoop(loopId);
  }

  return {
    start: begin,
    interrupt() {
      if (!running) {
        begin();
        return;
      }
      if (turn === null) return;
      const interrupted = turn;
      interrupted.stream.cancel();
      player.stop();
      endTurn(interrupted);
    },
    end() {
      running = false;
      loopId += 1;
      listening?.cancel();
      if (turn !== null) {
        turn.stream.cancel();
        endTurn(turn);
      }
      player.stop();
    },
    readLevel: () => (turn?.speaking ? player.level() : micLevel),
  };
}
