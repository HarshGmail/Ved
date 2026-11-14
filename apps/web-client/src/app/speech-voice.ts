import type { VoiceSettings } from "./voice-settings";

type VoiceLike = Pick<SpeechSynthesisVoice, "lang" | "name">;

export type VoiceLanguage = "te" | "hi";

export type VoicePlan =
  | { status: "ready"; voice: SpeechSynthesisVoice | undefined }
  | { status: "missing"; language: VoiceLanguage };

export const VOICE_LANGUAGE_NAMES: Record<VoiceLanguage, string> = {
  te: "Telugu",
  hi: "Hindi",
};

const TELUGU_SCRIPT = /[\u0C00-\u0C7F]/g;
const DEVANAGARI_SCRIPT = /[\u0900-\u097F]/g;
const LATIN_LETTERS = /[A-Za-z]/g;

function normalizedLanguage(voice: VoiceLike): string {
  return voice.lang.replace("_", "-").toLowerCase();
}

function countMatches(text: string, pattern: RegExp): number {
  return (text.match(pattern) ?? []).length;
}

export function isIndianEnglish(voice: VoiceLike): boolean {
  return normalizedLanguage(voice).startsWith("en-in");
}

export function isEnglish(voice: VoiceLike): boolean {
  const language = normalizedLanguage(voice);
  return language === "en" || language.startsWith("en-");
}

export function hasLanguage(voice: VoiceLike, language: VoiceLanguage): boolean {
  const normalized = normalizedLanguage(voice);
  return normalized === language || normalized.startsWith(`${language}-`);
}

export function voicesForLanguage(
  voices: readonly SpeechSynthesisVoice[],
  language: VoiceLanguage,
): SpeechSynthesisVoice[] {
  return voices.filter((voice) => hasLanguage(voice, language));
}

export function voiceLanguageFor(text: string): VoiceLanguage | null {
  const telugu = countMatches(text, TELUGU_SCRIPT);
  const devanagari = countMatches(text, DEVANAGARI_SCRIPT);
  const letters = telugu + devanagari + countMatches(text, LATIN_LETTERS);
  if (telugu * 2 > letters) return "te";
  if (devanagari * 2 > letters) return "hi";
  return null;
}

export function pickVoice(
  voices: readonly SpeechSynthesisVoice[],
  savedName: string | null,
): SpeechSynthesisVoice | undefined {
  const saved = savedName === null ? undefined : voices.find((voice) => voice.name === savedName);
  return saved ?? voices.find(isIndianEnglish) ?? voices.find(isEnglish);
}

export function planVoice(
  voices: readonly SpeechSynthesisVoice[],
  text: string,
  settings: VoiceSettings,
): VoicePlan {
  const language = voiceLanguageFor(text);
  if (language === null) {
    return { status: "ready", voice: pickVoice(voices, settings.voiceName) };
  }
  const savedName = language === "te" ? settings.teluguVoiceName : settings.hindiVoiceName;
  const candidates = voicesForLanguage(voices, language);
  const voice = candidates.find((candidate) => candidate.name === savedName) ?? candidates[0];
  return voice ? { status: "ready", voice } : { status: "missing", language };
}

function pickerRank(voice: VoiceLike): number {
  if (isIndianEnglish(voice)) return 0;
  if (isEnglish(voice)) return 1;
  return 2;
}

export function orderVoicesForPicker(voices: readonly SpeechSynthesisVoice[]): SpeechSynthesisVoice[] {
  return [...voices].sort(
    (first, second) => pickerRank(first) - pickerRank(second) || first.name.localeCompare(second.name),
  );
}

export function missingVoiceCopy(language: VoiceLanguage): string {
  return `No ${VOICE_LANGUAGE_NAMES[language]} voice on this device`;
}

export function voiceLabel(voice: VoiceLike): string {
  return `${voice.name} — ${voice.lang}`;
}
