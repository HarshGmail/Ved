"use client";

import { cancelDeviceSpeech, speakOnDevice } from "../device-speech";
import { orderVoicesForPicker, voiceLabel, voicesForLanguage, type VoiceLanguage, VOICE_LANGUAGE_NAMES } from "../speech-voice";
import { useSpeechSupport, useSpeechVoices } from "../use-read-aloud";
import { useSpeechInputSupport } from "../use-speech-input";
import { serverSpeaks, useVoiceStatus } from "../voice-status";
import {
  LISTEN_LANGUAGES,
  PITCH_RANGE,
  RATE_RANGE,
  updateVoiceSettings,
  useVoiceSettings,
} from "../voice-settings";
import { Field, formatRate, RangeField, ToggleRow } from "./settings-fields";
import { ServerVoiceControls } from "./server-voice-controls";
import styles from "./settings.module.css";

const UNSUPPORTED_DEVICE_COPY = "This browser can't read replies aloud on its own.";
const AUTO_READ_LABEL = "Read replies aloud automatically";
const AUTO_SEND_LABEL = "Send automatically after speaking";
const IPHONE_TAP_HINT = "On iPhone, Ved starts reading after you've tapped once in the app.";
const ENHANCED_VOICE_TIP =
  "On iPhone, more natural voices can be downloaded in Settings → Accessibility → Spoken Content → Voices (look for Enhanced or Premium).";
const TELUGU_VOICE_TIP =
  "For Telugu, add a Telugu voice in your phone's text-to-speech settings (Android: Google Text-to-speech → Install voice data → Telugu).";
const DICTATION_TIP = "Tip: tap the mic on your keyboard to dictate.";
const SERVER_PRIVACY_NOTE =
  "Talk mode sends your voice to Ved's server to be transcribed, and the server voice speaks the replies. Device voices and browser dictation are handled by your phone or browser.";
const DEVICE_PRIVACY_NOTE =
  "Speech recognition is done by your phone or browser (Apple or Google), not by Ved's server.";
const DEVICE_HEADING = "Device voice (used for Telugu or when the server voice is off)";
const AUTO_VOICE_LABEL = "Automatic (Indian English when available)";
const AUTO_LANGUAGE_VOICE_LABEL = "Automatic";
const DEVICE_TEST_PHRASE = "Hi, I'm Ved.";

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

function DeviceVoiceControls() {
  const voices = useSpeechVoices();
  const settings = useVoiceSettings();

  return (
    <div className={styles.subsection}>
      <h3 className={styles.subheading}>{DEVICE_HEADING}</h3>

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
        label="Device speed"
        value={settings.rate}
        range={RATE_RANGE}
        format={formatRate}
        onChange={(rate) => updateVoiceSettings({ rate })}
      />

      <RangeField
        label="Pitch"
        value={settings.pitch}
        range={PITCH_RANGE}
        format={(pitch) => pitch.toFixed(1)}
        onChange={(pitch) => updateVoiceSettings({ pitch })}
      />

      <button
        className={styles.primary}
        type="button"
        onClick={() => {
          cancelDeviceSpeech();
          speakOnDevice(DEVICE_TEST_PHRASE);
        }}
      >
        Test device voice
      </button>
    </div>
  );
}

export function VoiceControls() {
  const status = useVoiceStatus();
  const settings = useVoiceSettings();
  const dictationSupported = useSpeechInputSupport();
  const deviceSupported = useSpeechSupport();

  return (
    <>
      <ServerVoiceControls status={status} settings={settings} />

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

      {deviceSupported ? <DeviceVoiceControls /> : <p className={styles.hint}>{UNSUPPORTED_DEVICE_COPY}</p>}

      <p className={styles.hint}>{serverSpeaks(status) ? SERVER_PRIVACY_NOTE : DEVICE_PRIVACY_NOTE}</p>
    </>
  );
}
