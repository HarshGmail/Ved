"use client";

import { useEffect, useState } from "react";
import { connector, type VoiceInfo, type VoiceStatus } from "@/connector";
import { getVoicePlayer } from "../voice-player";
import { speechOptionsFor } from "../voice-status";
import {
  readVoiceSettings,
  SERVER_SPEED_RANGE,
  updateVoiceSettings,
  type VoiceSettings,
} from "../voice-settings";
import { Field, formatRate, RangeField } from "./settings-fields";
import styles from "./settings.module.css";

const UNAVAILABLE_COPY = "Ved's server voice is off, so replies use this device's voice.";
const VOICES_FAILED_COPY = "Couldn't load Ved's voices.";
const SERVER_TEST_PHRASE = "Hello, I'm Ved. How can I help?";
const SERVER_VOICE_LABEL = "Ved's voice";
const SERVER_SPEED_LABEL = "Speed";
const SERVER_AUTOMATIC_LABEL = "Automatic";

function voiceOptionLabel(voice: VoiceInfo): string {
  return `${voice.name} (${voice.language})`;
}

function useServerVoices(enabled: boolean): { voices: VoiceInfo[]; failed: boolean } {
  const [state, setState] = useState<{ voices: VoiceInfo[]; failed: boolean }>({
    voices: [],
    failed: false,
  });

  useEffect(() => {
    if (!enabled) return;
    let current = true;
    connector
      .voices()
      .then((voices) => {
        if (current) setState({ voices, failed: false });
      })
      .catch(() => {
        if (current) setState({ voices: [], failed: true });
      });
    return () => {
      current = false;
    };
  }, [enabled]);

  return state;
}

export function ServerVoiceControls({
  status,
  settings,
}: {
  status: VoiceStatus;
  settings: VoiceSettings;
}) {
  const serverOn = status.tts_languages.length > 0;
  const { voices, failed } = useServerVoices(serverOn);

  if (!serverOn) return <p className={styles.hint}>{UNAVAILABLE_COPY}</p>;

  function testServerVoice() {
    const player = getVoicePlayer();
    player.unlock();
    player.stop();
    player.enqueue(SERVER_TEST_PHRASE, speechOptionsFor(readVoiceSettings(), status));
  }

  return (
    <>
      <div className={styles.group}>
        <Field label={SERVER_VOICE_LABEL}>
          <select
            className={styles.select}
            value={settings.serverVoiceName ?? status.default_voice ?? ""}
            onChange={(event) => updateVoiceSettings({ serverVoiceName: event.target.value || null })}
          >
            <option value="">{SERVER_AUTOMATIC_LABEL}</option>
            {voices.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voiceOptionLabel(voice)}
              </option>
            ))}
          </select>
        </Field>
        {failed && <p className={styles.hint}>{VOICES_FAILED_COPY}</p>}
      </div>

      <RangeField
        label={SERVER_SPEED_LABEL}
        value={settings.serverSpeed}
        range={SERVER_SPEED_RANGE}
        format={formatRate}
        onChange={(serverSpeed) => updateVoiceSettings({ serverSpeed })}
      />

      <button className={styles.primary} type="button" onClick={testServerVoice}>
        Test voice
      </button>
    </>
  );
}
