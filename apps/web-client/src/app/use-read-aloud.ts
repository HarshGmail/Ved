"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { speechSynthesisAvailable } from "./device-speech";
import { prepareSpeechChunks } from "./speech-text";
import { planVoice, type VoiceLanguage } from "./speech-voice";
import { getVoicePlayer } from "./voice-player";
import { currentVoiceStatus, serverSpeaks, speechOptionsFor, useVoiceStatus } from "./voice-status";
import { readVoiceSettings } from "./voice-settings";

const FALLBACK_LANGUAGE = "en-US";

export interface ReadAloud {
  supported: boolean;
  speakingId: string | null;
  unvoicedId: string | null;
  unvoicedLanguage: VoiceLanguage | null;
  speak: (id: string, text: string) => void;
  stop: () => void;
}

let speechUnlocked = false;

export function noSubscription(): () => void {
  return () => undefined;
}

export function useSpeechSupport(): boolean {
  return useSyncExternalStore(noSubscription, speechSynthesisAvailable, () => false);
}

export function useSpeechVoices(): SpeechSynthesisVoice[] {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);

  useEffect(() => {
    if (!speechSynthesisAvailable()) return;
    const engine = window.speechSynthesis;
    const refresh = () => setVoices(engine.getVoices());
    refresh();
    engine.addEventListener("voiceschanged", refresh);
    return () => engine.removeEventListener("voiceschanged", refresh);
  }, []);

  return voices;
}

function unlockSpeech(): void {
  getVoicePlayer().unlock();
  if (speechUnlocked || !speechSynthesisAvailable()) return;
  speechUnlocked = true;
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(""));
}

export function useReadAloud(): ReadAloud {
  const deviceSupported = useSpeechSupport();
  const serverReady = serverSpeaks(useVoiceStatus());
  const supported = deviceSupported || serverReady;
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const [unvoiced, setUnvoiced] = useState<{ id: string; language: VoiceLanguage } | null>(null);
  const runRef = useRef(0);
  const utterancesRef = useRef<SpeechSynthesisUtterance[]>([]);

  const finishRun = useCallback((run: number) => {
    if (run !== runRef.current) return;
    utterancesRef.current = [];
    setSpeakingId(null);
  }, []);

  const stop = useCallback(() => {
    runRef.current += 1;
    utterancesRef.current = [];
    getVoicePlayer().stop();
    setSpeakingId(null);
  }, []);

  const speakOnServer = useCallback(
    (id: string, chunks: string[]) => {
      const player = getVoicePlayer();
      runRef.current += 1;
      const run = runRef.current;
      player.stop();
      setUnvoiced(null);
      setSpeakingId(id);
      const options = speechOptionsFor(readVoiceSettings(), currentVoiceStatus());
      chunks.forEach((chunk) => player.enqueue(chunk, options));
      void player.finish().then(() => finishRun(run));
    },
    [finishRun],
  );

  const speak = useCallback(
    (id: string, text: string) => {
      const chunks = prepareSpeechChunks(text);
      if (chunks.length === 0) return;
      if (serverReady) {
        speakOnServer(id, chunks);
        return;
      }
      if (!speechSynthesisAvailable()) return;

      const engine = window.speechSynthesis;
      const settings = readVoiceSettings();
      runRef.current += 1;
      const run = runRef.current;
      engine.cancel();

      const plan = planVoice(engine.getVoices(), text, settings);
      if (plan.status === "missing") {
        setSpeakingId(null);
        setUnvoiced({ id, language: plan.language });
        return;
      }
      setUnvoiced(null);

      const utterances = chunks.map((chunk, index) => {
        const utterance = new SpeechSynthesisUtterance(chunk);
        utterance.voice = plan.voice ?? null;
        utterance.lang = plan.voice?.lang ?? FALLBACK_LANGUAGE;
        utterance.rate = settings.rate;
        utterance.pitch = settings.pitch;
        utterance.onend = index === chunks.length - 1 ? () => finishRun(run) : null;
        utterance.onerror = () => finishRun(run);
        return utterance;
      });
      utterancesRef.current = utterances;
      setSpeakingId(id);
      utterances.forEach((utterance) => engine.speak(utterance));
    },
    [finishRun, serverReady, speakOnServer],
  );

  useEffect(() => {
    const stopWhenHidden = () => {
      if (document.hidden) stop();
    };
    window.addEventListener("pointerdown", unlockSpeech, { once: true });
    window.addEventListener("keydown", unlockSpeech, { once: true });
    document.addEventListener("visibilitychange", stopWhenHidden);
    return () => {
      window.removeEventListener("pointerdown", unlockSpeech);
      window.removeEventListener("keydown", unlockSpeech);
      document.removeEventListener("visibilitychange", stopWhenHidden);
      stop();
    };
  }, [stop]);

  return useMemo(
    () => ({
      supported,
      speakingId,
      unvoicedId: unvoiced?.id ?? null,
      unvoicedLanguage: unvoiced?.language ?? null,
      speak,
      stop,
    }),
    [supported, speakingId, unvoiced, speak, stop],
  );
}
