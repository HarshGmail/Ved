"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { noSubscription } from "./use-read-aloud";
import { readVoiceSettings } from "./voice-settings";

interface RecognitionAlternative {
  readonly transcript: string;
}

interface RecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  [index: number]: RecognitionAlternative;
}

interface RecognitionResultList {
  readonly length: number;
  [index: number]: RecognitionResult;
}

interface RecognitionResultEvent extends Event {
  readonly resultIndex: number;
  readonly results: RecognitionResultList;
}

interface RecognitionErrorEvent extends Event {
  readonly error: string;
}

interface RecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: RecognitionResultEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type RecognitionConstructor = new () => RecognitionLike;

type RecognitionWindow = Window & {
  SpeechRecognition?: RecognitionConstructor;
  webkitSpeechRecognition?: RecognitionConstructor;
};

export interface SpeechInput {
  supported: boolean;
  listening: boolean;
  interim: string | null;
  error: string | null;
  start: () => void;
  stop: () => void;
}

const QUIET_ERRORS: ReadonlySet<string> = new Set(["no-speech", "aborted"]);

function recognitionConstructor(): RecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const speechWindow = window as RecognitionWindow;
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

function speechInputAvailable(): boolean {
  return recognitionConstructor() !== null;
}

export function useSpeechInputSupport(): boolean {
  return useSyncExternalStore(noSubscription, speechInputAvailable, () => false);
}

function transcriptsOf(event: RecognitionResultEvent): { interim: string; final: string } {
  let interim = "";
  let final = "";
  for (let index = event.resultIndex; index < event.results.length; index += 1) {
    const result = event.results[index];
    if (result.isFinal) {
      final += result[0].transcript;
    } else {
      interim += result[0].transcript;
    }
  }
  return { interim: interim.trim(), final: final.trim() };
}

export function useSpeechInput(onFinal: (text: string) => void): SpeechInput {
  const supported = useSpeechInputSupport();
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<RecognitionLike | null>(null);
  const finalRef = useRef(onFinal);

  useEffect(() => {
    finalRef.current = onFinal;
  }, [onFinal]);

  useEffect(() => {
    return () => recognitionRef.current?.abort();
  }, []);

  const start = useCallback(() => {
    const Recognition = recognitionConstructor();
    if (!Recognition || recognitionRef.current) return;

    const recognition = new Recognition();
    recognition.lang = readVoiceSettings().listenLang;
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const transcripts = transcriptsOf(event);
      if (transcripts.final) {
        setInterim(null);
        finalRef.current(transcripts.final);
        return;
      }
      setInterim(transcripts.interim);
    };
    recognition.onerror = (event) => {
      setError(QUIET_ERRORS.has(event.error) ? null : event.error);
    };
    recognition.onend = () => {
      if (recognitionRef.current === recognition) recognitionRef.current = null;
      setListening(false);
      setInterim(null);
    };

    recognitionRef.current = recognition;
    setError(null);
    setListening(true);
    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setListening(false);
      setError("unavailable");
    }
  }, []);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  return { supported, listening, interim, error, start, stop };
}
