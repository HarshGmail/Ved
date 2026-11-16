import { createLevelReader } from "./audio-level";
import { getVoicePlayer } from "./voice-player";

export type Utterance = { kind: "speech"; blob: Blob } | { kind: "silence" };

export interface Listening {
  result: Promise<Utterance>;
  cancel: () => void;
}

export class MicrophoneUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MicrophoneUnavailableError";
  }
}

const DENIED_COPY = "Allow microphone access for Ved in your browser settings";
const MISSING_COPY = "Ved can't find a microphone on this device";
const NO_AUDIO_COPY = "This browser can't record audio";
const MIC_CONSTRAINTS: MediaStreamConstraints = {
  audio: { echoCancellation: true, noiseSuppression: true },
};
const PREFERRED_MIME_TYPES = ["audio/webm;codecs=opus", "audio/mp4"] as const;
const SPEECH_LEVEL = 0.12;
const LISTEN_TICK_MS = 50;
const SILENCE_END_MS = 1200;
const NO_SPEECH_TIMEOUT_MS = 8000;
const MAX_UTTERANCE_MS = 30000;
const MUTED_GAIN = 0;

export function recordingSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof MediaRecorder !== "undefined" &&
    typeof navigator !== "undefined" &&
    navigator.mediaDevices !== undefined &&
    typeof navigator.mediaDevices.getUserMedia === "function"
  );
}

function preferredMimeType(): string | undefined {
  return PREFERRED_MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
}

function microphoneError(error: unknown): MicrophoneUnavailableError {
  const denied =
    error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "SecurityError");
  return new MicrophoneUnavailableError(denied ? DENIED_COPY : MISSING_COPY);
}

function releaseStream(stream: MediaStream): void {
  stream.getTracks().forEach((track) => track.stop());
}

class UtteranceCapture {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private analysis: { source: MediaStreamAudioSourceNode; analyser: AnalyserNode; mute: GainNode } | null = null;
  private readLevel: () => number = () => 0;
  private timer: ReturnType<typeof setInterval> | null = null;
  private startedAt = 0;
  private speechStartedAt = 0;
  private lastVoiceAt = 0;
  private settled = false;
  private resolve: (utterance: Utterance) => void = () => undefined;
  private reject: (error: unknown) => void = () => undefined;

  constructor(private readonly onLevel: (level: number) => void) {}

  run(): Promise<Utterance> {
    return new Promise<Utterance>((resolve, reject) => {
      this.resolve = resolve;
      this.reject = reject;
      this.open().catch((error: unknown) => {
        this.settled = true;
        reject(error);
      });
    });
  }

  cancel(): void {
    if (this.recorder?.state === "recording") {
      this.recorder.onstop = null;
      this.recorder.stop();
    }
    this.end({ kind: "silence" });
  }

  private async open(): Promise<void> {
    const player = getVoicePlayer();
    player.unlock();
    const context = player.audioContext();
    if (!context) throw new MicrophoneUnavailableError(NO_AUDIO_COPY);

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
    } catch (error: unknown) {
      throw microphoneError(error);
    }
    if (this.settled) {
      releaseStream(stream);
      return;
    }

    this.stream = stream;
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    const mute = context.createGain();
    mute.gain.value = MUTED_GAIN;
    source.connect(analyser);
    analyser.connect(mute);
    mute.connect(context.destination);
    this.analysis = { source, analyser, mute };
    this.readLevel = createLevelReader(analyser);

    this.startedAt = performance.now();
    this.timer = setInterval(() => this.tick(), LISTEN_TICK_MS);
  }

  private tick(): void {
    const level = this.readLevel();
    this.onLevel(level);
    const now = performance.now();
    if (this.recorder === null) {
      this.waitForSpeech(level, now);
      return;
    }
    if (level >= SPEECH_LEVEL) this.lastVoiceAt = now;
    const quietFor = now - this.lastVoiceAt;
    const spokenFor = now - this.speechStartedAt;
    if (quietFor >= SILENCE_END_MS || spokenFor >= MAX_UTTERANCE_MS) this.stopRecording();
  }

  private waitForSpeech(level: number, now: number): void {
    if (level >= SPEECH_LEVEL) {
      this.startRecording(now);
      return;
    }
    if (now - this.startedAt >= NO_SPEECH_TIMEOUT_MS) this.end({ kind: "silence" });
  }

  private startRecording(now: number): void {
    if (!this.stream) return;
    const mimeType = preferredMimeType();
    const recorder = new MediaRecorder(this.stream, mimeType ? { mimeType } : undefined);
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    };
    recorder.onstop = () => {
      this.end({ kind: "speech", blob: new Blob(this.chunks, { type: recorder.mimeType }) });
    };
    this.recorder = recorder;
    this.speechStartedAt = now;
    this.lastVoiceAt = now;
    recorder.start();
  }

  private stopRecording(): void {
    this.clearTimer();
    if (this.recorder?.state === "recording") this.recorder.stop();
  }

  private clearTimer(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }

  private end(utterance: Utterance): void {
    if (this.settled) return;
    this.settled = true;
    this.clearTimer();
    if (this.stream) releaseStream(this.stream);
    if (this.analysis) {
      this.analysis.source.disconnect();
      this.analysis.analyser.disconnect();
      this.analysis.mute.disconnect();
    }
    this.onLevel(0);
    this.resolve(utterance);
  }
}

export function listenForUtterance(onLevel: (level: number) => void): Listening {
  const capture = new UtteranceCapture(onLevel);
  return {
    result: capture.run(),
    cancel: () => capture.cancel(),
  };
}
