import { connector } from "@/connector";
import { createLevelAnalyser, createLevelReader } from "./audio-level";
import { cancelDeviceSpeech, type DeviceUtterance, speakOnDevice } from "./device-speech";
import { voiceLanguageFor } from "./speech-voice";

const SAFETY_MARGIN_MS = 2000;

export interface SpeechOptions {
  voice?: string;
  speed: number;
  serverLanguages: readonly string[];
}

export interface VoicePlayer {
  audioContext: () => AudioContext | null;
  unlock: () => void;
  enqueue: (text: string, options: SpeechOptions) => void;
  finish: () => Promise<void>;
  stop: () => void;
  level: () => number;
}

interface Output {
  context: AudioContext;
  analyser: AnalyserNode;
  readLevel: () => number;
}

interface SpeechJob {
  text: string;
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

  function prepare(text: string, options: SpeechOptions): SpeechJob {
    if (!routesToServer(text, options.serverLanguages)) return { text, server: null };
    const server = connector
      .speak(text, { voice: options.voice, speed: options.speed, signal: fetches.signal })
      .then(
        (audio) => audio,
        () => null,
      );
    return { text, server };
  }

  async function speakOnDeviceNow(text: string, run: number): Promise<void> {
    if (run !== generation) return;
    const utterance = speakOnDevice(text);
    currentDevice = utterance;
    await utterance.done;
    if (currentDevice === utterance) currentDevice = null;
  }

  async function playAudio(audio: ArrayBuffer, run: number): Promise<boolean> {
    const current = ensureOutput();
    if (!current) return false;
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
    if (audio === null || !(await playAudio(audio, run))) {
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

  function stop(): void {
    generation += 1;
    chain = Promise.resolve();
    fetches.abort();
    fetches = new AbortController();
    if (currentSource) haltSource(currentSource);
    currentSource = null;
    currentDevice?.cancel();
    currentDevice = null;
    cancelDeviceSpeech();
  }

  return {
    audioContext: () => ensureOutput()?.context ?? null,
    unlock,
    enqueue,
    finish: () => chain,
    stop,
    level: () => output?.readLevel() ?? 0,
  };
}

let sharedPlayer: VoicePlayer | null = null;

export function getVoicePlayer(): VoicePlayer {
  sharedPlayer ??= createVoicePlayer();
  return sharedPlayer;
}
