import { cutSentences, toSpeakableText } from "./speech-text";
import type { SpeechOptions, VoicePlayer } from "./voice-player";

export interface SpeechStream {
  push: (token: string) => void;
  breakSegment: () => void;
  finish: () => Promise<void>;
  cancel: () => void;
}

export function createSpeechStream(
  player: VoicePlayer,
  options: SpeechOptions,
  onSentence: () => void = () => undefined,
): SpeechStream {
  let pending = "";
  let cancelled = false;

  function queue(raw: string): void {
    if (cancelled) return;
    const spoken = toSpeakableText(raw).trim();
    if (spoken === "") return;
    player.enqueue(spoken, options);
    onSentence();
  }

  function takePending(): void {
    queue(pending);
    pending = "";
  }

  return {
    push(token) {
      if (cancelled) return;
      const { sentences, rest } = cutSentences(pending + token);
      pending = rest;
      sentences.forEach(queue);
    },
    breakSegment() {
      if (!cancelled) takePending();
    },
    finish() {
      if (cancelled) return Promise.resolve();
      takePending();
      return player.finish();
    },
    cancel() {
      cancelled = true;
      pending = "";
    },
  };
}
