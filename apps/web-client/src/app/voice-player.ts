import { connector } from "@/connector";
import { createLevelAnalyser, createLevelReader } from "./audio-level";
import { cancelDeviceSpeech, type DeviceUtterance, speakOnDevice } from "./device-speech";
import { voiceLanguageFor } from "./speech-voice";

const SAFETY_MARGIN_MS = 2000;
const RESUME_TIMEOUT_MS = 800;

export interface SpeechOptions {
  voice?: string;
  speed: number;
  serverLanguages: readonly string[];
}

export interface VoicePlayer {
  audioContext: () => AudioContext | null;
  unlock: () => void;
  wake: () => Promise<boolean>;
  enqueue: (text: string, options: SpeechOptions) => void;
  finish: () => Promise<void>;
  stop: () => void;
  level: () => number;
  resumeHeld: () => Promise<void>;
  onHeldChange: (listener: (held: boolean) => void) => () => void;
}

interface HeldSentence {
  text: string;
  options: SpeechOptions;
}

interface Output {
  context: AudioContext;
  analyser: AnalyserNode;
  readLevel: () => number;
}

interface SpeechJob {
  text: string;
  options: SpeechOptions;
  server: Promise<ArrayBuffer | null> | null;
}

interface WebkitWindow {
  webkitAudioContext?: typeof AudioContext;
}

function audioContextConstructor(): typeof AudioContext | null {
  if (typeof window === "undefined") return null;
  return window.AudioContext ?? (window as WebkitWindow).webkitAudioContext ?? null;
}

export function routesToServer(text: string, serverLanguages: readonly string[]): boolean {
  if (serverLanguages.length === 0) return false;
  const language = voiceLanguageFor(text);
  return language === null || serverLanguages.includes(language);
}

function playSilence(context: AudioContext): void {
  const source = context.createBufferSource();
  source.buffer = context.createBuffer(1, 1, context.sampleRate);
  source.connect(context.destination);
  source.start();
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function resumeContext(context: AudioContext): Promise<boolean> {
  if (context.state !== "running") {
    await Promise.race([
      context.resume().catch(() => undefined),
      delay(RESUME_TIMEOUT_MS),
    ]);
  }
  return context.state === "running";
}

function haltSource(source: AudioBufferSourceNode): void {
  try {
    source.stop();
  } catch {}
}

export function createVoicePlayer(): VoicePlayer {
  let output: Output | null = null;
  let generation = 0;
  let chain: Promise<void> = Promise.resolve();
  let fetches = new AbortController();
  let currentSource: AudioBufferSourceNode | null = null;
  let currentDevice: DeviceUtterance | null = null;
  let held: HeldSentence | null = null;
  const heldListeners = new Set<(held: boolean) => void>();

  function setHeld(next: HeldSentence | null): void {
    if (held === next) return;
    held = next;
    heldListeners.forEach((listener) => listener(next !== null));
  }

  function ensureOutput(): Output | null {
    if (output) return output;
    const Constructor = audioContextConstructor();
    if (!Constructor) return null;
    const context = new Constructor();
    const analyser = createLevelAnalyser(context);
    analyser.connect(context.destination);
    output = { context, analyser, readLevel: createLevelReader(analyser) };
    return output;
  }

  function unlock(): void {
    const current = ensureOutput();
    if (!current) return;
    if (current.context.state !== "running") {
      current.context.resume().catch(() => undefined);
    }
    playSilence(current.context);
  }

  async function wake(): Promise<boolean> {
    const current = ensureOutput();
    return current ? resumeContext(current.context) : false;
  }

  function prepare(text: string, options: SpeechOptions): SpeechJob {
    if (!routesToServer(text, options.serverLanguages)) return { text, options, server: null };
    const server = connector
      .speak(text, { voice: options.voice, speed: options.speed, signal: fetches.signal })
      .then(
        (audio) => audio,
        () => null,
      );
    return { text, options, server };
  }

  async function speakOnDeviceNow(text: string, run: number): Promise<void> {
    if (run !== generation) return;
    const utterance = speakOnDevice(text);
    currentDevice = utterance;
    await utterance.done;
    if (currentDevice === utterance) currentDevice = null;
  }

  async function playAudio(audio: ArrayBuffer, job: SpeechJob, run: number): Promise<boolean> {
    const current = ensureOutput();
    if (!current) return false;
    const running = held === null ? await resumeContext(current.context) : current.context.state === "running";
    if (!running) {
      if (held === null) setHeld({ text: job.text, options: job.options });
      return false;
    }
    setHeld(null);
    const decoded = await current.context.decodeAudioData(audio).catch(() => null);
    if (decoded === null) return false;
    if (run !== generation) return true;

    await new Promise<void>((resolve) => {
      const source = current.context.createBufferSource();
      const settle = () => {
        clearTimeout(safety);
        if (currentSource === source) currentSource = null;
        resolve();
      };
      const safety = setTimeout(settle, decoded.duration * 1000 + SAFETY_MARGIN_MS);
      source.buffer = decoded;
      source.connect(current.analyser);
      source.onended = settle;
      currentSource = source;
      source.start();
    });
    return true;
  }

  async function play(job: SpeechJob, run: number): Promise<void> {
    if (run !== generation) return;
    if (job.server === null) return speakOnDeviceNow(job.text, run);
    const audio = await job.server;
    if (run !== generation) return;
    if (audio === null || !(await playAudio(audio, job, run))) {
      await speakOnDeviceNow(job.text, run);
    }
  }

  function enqueue(text: string, options: SpeechOptions): void {
    const spoken = text.trim();
    if (spoken === "") return;
    const run = generation;
    const job = prepare(spoken, options);
    chain = chain.then(() => play(job, run)).catch(() => undefined);
  }

  async function resumeHeld(): Promise<void> {
    const pending = held;
    const current = ensureOutput();
    if (pending === null || current === null) return;
    if (!(await resumeContext(current.context))) return;
    setHeld(null);
    enqueue(pending.text, pending.options);
  }

  function stop(): void {
    generation += 1;
    chain = Promise.resolve();
    fetches.abort();
    fetches = new AbortController();
    if (currentSource) haltSource(currentSource);
    currentSource = null;
    currentDevice?.cancel();
    currentDevice = null;
    setHeld(null);
    cancelDeviceSpeech();
  }

  return {
    audioContext: () => ensureOutput()?.context ?? null,
    unlock,
    wake,
    enqueue,
    finish: () => chain,
    stop,
    level: () => output?.readLevel() ?? 0,
    resumeHeld,
    onHeldChange: (listener) => {
      heldListeners.add(listener);
      return () => {
        heldListeners.delete(listener);
      };
    },
  };
}

let sharedPlayer: VoicePlayer | null = null;

export function getVoicePlayer(): VoicePlayer {
  sharedPlayer ??= createVoicePlayer();
  return sharedPlayer;
}
