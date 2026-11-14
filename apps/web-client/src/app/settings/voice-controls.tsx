"use client";

import type { ReactNode } from "react";
import { orderVoicesForPicker, voiceLabel, voicesForLanguage, type VoiceLanguage, VOICE_LANGUAGE_NAMES } from "../speech-voice";
import { useReadAloud, useSpeechVoices } from "../use-read-aloud";
import { useSpeechInputSupport } from "../use-speech-input";
import {
  LISTEN_LANGUAGES,
  PITCH_RANGE,
  RATE_RANGE,
  updateVoiceSettings,
  useVoiceSettings,
} from "../voice-settings";
import styles from "./settings.module.css";

const UNSUPPORTED_COPY = "This browser can't read replies aloud.";
const AUTO_READ_LABEL = "Read replies aloud automatically";
const AUTO_SEND_LABEL = "Send automatically after speaking";
const IPHONE_TAP_HINT = "On iPhone, Ved starts reading after you've tapped once in the app.";
const ENHANCED_VOICE_TIP =
  "On iPhone, more natural voices can be downloaded in Settings → Accessibility → Spoken Content → Voices (look for Enhanced or Premium).";
const TELUGU_VOICE_TIP =
  "For Telugu, add a Telugu voice in your phone's text-to-speech settings (Android: Google Text-to-speech → Install voice data → Telugu).";
const DICTATION_TIP = "Tip: tap the mic on your keyboard to dictate.";
const PRIVACY_NOTE = "Speech recognition is done by your phone or browser (Apple or Google), not by Ved's server.";
const AUTO_VOICE_LABEL = "Automatic (Indian English when available)";
const AUTO_LANGUAGE_VOICE_LABEL = "Automatic";
const TEST_ID = "voice-settings-test";
const TEST_PHRASE = "Hi, I'm Ved.";

function formatRate(rate: number): string {
  return `${rate.toFixed(1)}×`;
}

function formatPitch(pitch: number): string {
  return pitch.toFixed(1);
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className={styles.switchRow}>
      <span>{label}</span>
      <input
        className={styles.switchInput}
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className={styles.switchTrack} aria-hidden="true" />
    </label>
  );
}

function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <label className={styles.field}>
      <span className={styles.fieldLabel}>{label}</span>
      {children}
    </label>
  );
}

function VoicePicker({
  label,
  value,
  automaticLabel,
  voices,
  onChange,
}: {
  label: string;
  value: string | null;
  automaticLabel: string;
  voices: SpeechSynthesisVoice[];
  onChange: (name: string | null) => void;
}) {
  return (
    <Field label={label}>
      <select
        className={styles.select}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value || null)}
      >
        <option value="">{automaticLabel}</option>
        {voices.map((voice) => (
          <option key={voice.voiceURI} value={voice.name}>
            {voiceLabel(voice)}
          </option>
        ))}
      </select>
    </Field>
  );
}

function RangeField({
  label,
  value,
  range,
  format,
  onChange,
}: {
  label: string;
  value: number;
  range: { min: number; max: number; step: number };
  format: (value: number) => string;
  onChange: (value: number) => void;
}) {
  return (
    <Field
      label={
        <>
          {label} <output className={styles.fieldValue}>{format(value)}</output>
        </>
      }
    >
      <input
        className={styles.slider}
        type="range"
        min={range.min}
        max={range.max}
        step={range.step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </Field>
  );
}

function LanguageVoicePicker({
  language,
  savedName,
  voices,
  onChange,
}: {
  language: VoiceLanguage;
  savedName: string | null;
  voices: SpeechSynthesisVoice[];
  onChange: (name: string | null) => void;
}) {
  const name = VOICE_LANGUAGE_NAMES[language];
  const candidates = voicesForLanguage(voices, language);
  return (
    <div className={styles.group}>
      <VoicePicker
        label={`${name} voice`}
        value={savedName}
        automaticLabel={AUTO_LANGUAGE_VOICE_LABEL}
        voices={candidates}
        onChange={onChange}
      />
      {candidates.length === 0 && (
        <p className={styles.hint}>No {name} voice on this device yet.</p>
      )}
    </div>
  );
}

export function VoiceControls() {
  const { supported, speak } = useReadAloud();
  const voices = useSpeechVoices();
  const settings = useVoiceSettings();
  const dictationSupported = useSpeechInputSupport();

  if (!supported) return <p className={styles.text}>{UNSUPPORTED_COPY}</p>;

  return (
    <>
      <div className={styles.group}>
        <ToggleRow
          label={AUTO_READ_LABEL}
          checked={settings.autoRead}
          onChange={(autoRead) => updateVoiceSettings({ autoRead })}
        />
        <p className={styles.hint}>{IPHONE_TAP_HINT}</p>
      </div>

      <ToggleRow
        label={AUTO_SEND_LABEL}
        checked={settings.autoSend}
        onChange={(autoSend) => updateVoiceSettings({ autoSend })}
      />

      <div className={styles.group}>
        <VoicePicker
          label="Voice"
          value={settings.voiceName}
          automaticLabel={AUTO_VOICE_LABEL}
          voices={orderVoicesForPicker(voices)}
          onChange={(voiceName) => updateVoiceSettings({ voiceName })}
        />
        <p className={styles.hint}>{ENHANCED_VOICE_TIP}</p>
      </div>

      <div className={styles.group}>
        <LanguageVoicePicker
          language="te"
          savedName={settings.teluguVoiceName}
          voices={voices}
          onChange={(teluguVoiceName) => updateVoiceSettings({ teluguVoiceName })}
        />
        <p className={styles.hint}>{TELUGU_VOICE_TIP}</p>
      </div>

      <LanguageVoicePicker
        language="hi"
        savedName={settings.hindiVoiceName}
        voices={voices}
        onChange={(hindiVoiceName) => updateVoiceSettings({ hindiVoiceName })}
      />

      <RangeField
        label="Speed"
        value={settings.rate}
        range={RATE_RANGE}
        format={formatRate}
        onChange={(rate) => updateVoiceSettings({ rate })}
      />

      <RangeField
        label="Pitch"
        value={settings.pitch}
        range={PITCH_RANGE}
        format={formatPitch}
        onChange={(pitch) => updateVoiceSettings({ pitch })}
      />

      <div className={styles.group}>
        <Field label="Speech language">
          <select
            className={styles.select}
            value={settings.listenLang}
            onChange={(event) =>
              updateVoiceSettings({ listenLang: event.target.value as typeof settings.listenLang })
            }
          >
            {LISTEN_LANGUAGES.map((language) => (
              <option key={language.code} value={language.code}>
                {language.label}
              </option>
            ))}
          </select>
        </Field>
        {!dictationSupported && <p className={styles.hint}>{DICTATION_TIP}</p>}
      </div>

      <button
        className={styles.primary}
        type="button"
        onClick={() => speak(TEST_ID, TEST_PHRASE)}
      >
        Test voice
      </button>

      <p className={styles.hint}>{PRIVACY_NOTE}</p>
    </>
  );
}
