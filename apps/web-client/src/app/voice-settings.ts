import { useMemo, useSyncExternalStore } from "react";

export type ListenLanguage = "en-IN" | "te-IN" | "hi-IN" | "en-US";

export interface VoiceSettings {
  autoRead: boolean;
  voiceName: string | null;
  teluguVoiceName: string | null;
  hindiVoiceName: string | null;
  rate: number;
  pitch: number;
  listenLang: ListenLanguage;
  autoSend: boolean;
}

interface NumberRange {
  min: number;
  max: number;
  step: number;
}

export const VOICE_STORAGE_KEY = "ved.voice";
export const VOICE_CHANGE_EVENT = "ved-voice-change";

export const LISTEN_LANGUAGES: readonly { code: ListenLanguage; label: string }[] = [
  { code: "en-IN", label: "English (India)" },
  { code: "te-IN", label: "Telugu" },
  { code: "hi-IN", label: "Hindi" },
  { code: "en-US", label: "English (US)" },
];

export const RATE_RANGE: NumberRange = { min: 0.8, max: 1.4, step: 0.1 };
export const PITCH_RANGE: NumberRange = { min: 0.8, max: 1.3, step: 0.1 };

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  autoRead: false,
  voiceName: null,
  teluguVoiceName: null,
  hindiVoiceName: null,
  rate: 1,
  pitch: 1,
  listenLang: "en-IN",
  autoSend: true,
};

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function clampToRange(value: number, range: NumberRange): number {
  const tenths = Math.round(value / range.step) * range.step;
  return Math.min(range.max, Math.max(range.min, Math.round(tenths * 10) / 10));
}

function optionalName(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function isListenLanguage(value: unknown): value is ListenLanguage {
  return LISTEN_LANGUAGES.some((language) => language.code === value);
}

export function parseVoiceSettings(raw: string | null): VoiceSettings {
  if (raw === null) return DEFAULT_VOICE_SETTINGS;
  try {
    const stored: unknown = JSON.parse(raw);
    if (typeof stored !== "object" || stored === null) return DEFAULT_VOICE_SETTINGS;
    const fields = stored as Record<string, unknown>;
    return {
      autoRead: fields.autoRead === true,
      voiceName: optionalName(fields.voiceName),
      teluguVoiceName: optionalName(fields.teluguVoiceName),
      hindiVoiceName: optionalName(fields.hindiVoiceName),
      rate: isFiniteNumber(fields.rate)
        ? clampToRange(fields.rate, RATE_RANGE)
        : DEFAULT_VOICE_SETTINGS.rate,
      pitch: isFiniteNumber(fields.pitch)
        ? clampToRange(fields.pitch, PITCH_RANGE)
        : DEFAULT_VOICE_SETTINGS.pitch,
      listenLang: isListenLanguage(fields.listenLang)
        ? fields.listenLang
        : DEFAULT_VOICE_SETTINGS.listenLang,
      autoSend: typeof fields.autoSend === "boolean" ? fields.autoSend : DEFAULT_VOICE_SETTINGS.autoSend,
    };
  } catch {
    return DEFAULT_VOICE_SETTINGS;
  }
}

function readStoredVoiceSettings(): string | null {
  try {
    return localStorage.getItem(VOICE_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function readVoiceSettings(): VoiceSettings {
  return parseVoiceSettings(readStoredVoiceSettings());
}

export function writeVoiceSettings(settings: VoiceSettings): void {
  try {
    localStorage.setItem(VOICE_STORAGE_KEY, JSON.stringify(settings));
  } catch {}
  window.dispatchEvent(new Event(VOICE_CHANGE_EVENT));
}

export function updateVoiceSettings(patch: Partial<VoiceSettings>): void {
  writeVoiceSettings({ ...readVoiceSettings(), ...patch });
}

function subscribeToVoiceSettings(onChange: () => void): () => void {
  window.addEventListener(VOICE_CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(VOICE_CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useVoiceSettings(): VoiceSettings {
  const raw = useSyncExternalStore(subscribeToVoiceSettings, readStoredVoiceSettings, () => null);
  return useMemo(() => parseVoiceSettings(raw), [raw]);
}
