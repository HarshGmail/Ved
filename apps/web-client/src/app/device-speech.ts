import { planVoice } from "./speech-voice";
import { readVoiceSettings } from "./voice-settings";

const FALLBACK_LANGUAGE = "en-US";
const NOTHING_TO_SPEAK: DeviceUtterance = {
  done: Promise.resolve(),
  cancel: () => undefined,
};

export interface DeviceUtterance {
  done: Promise<void>;
  cancel: () => void;
}

export function speechSynthesisAvailable(): boolean {
  return (
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    "SpeechSynthesisUtterance" in window
  );
}

export function cancelDeviceSpeech(): void {
  if (speechSynthesisAvailable()) window.speechSynthesis.cancel();
}

export function speakOnDevice(text: string): DeviceUtterance {
  if (!speechSynthesisAvailable()) return NOTHING_TO_SPEAK;
  const engine = window.speechSynthesis;
  const settings = readVoiceSettings();
  const plan = planVoice(engine.getVoices(), text, settings);
  if (plan.status === "missing") return NOTHING_TO_SPEAK;

  let finish: () => void = () => undefined;
  const done = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.voice = plan.voice ?? null;
  utterance.lang = plan.voice?.lang ?? FALLBACK_LANGUAGE;
  utterance.rate = settings.rate;
  utterance.pitch = settings.pitch;
  utterance.onend = finish;
  utterance.onerror = finish;
  engine.speak(utterance);
  return { done, cancel: finish };
}
