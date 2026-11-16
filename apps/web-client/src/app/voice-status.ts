"use client";

import { useEffect, useState } from "react";
import { connector, type VoiceStatus } from "@/connector";
import type { SpeechOptions } from "./voice-player";
import type { VoiceSettings } from "./voice-settings";

export const NO_VOICE_STATUS: VoiceStatus = {
  stt: false,
  tts_languages: [],
  default_voice: null,
};

let loadedStatus: VoiceStatus = NO_VOICE_STATUS;
let pendingStatus: Promise<VoiceStatus> | null = null;

export function loadVoiceStatus(): Promise<VoiceStatus> {
  pendingStatus ??= connector
    .voiceStatus()
    .then((status) => {
      loadedStatus = status;
      return status;
    })
    .catch(() => {
      pendingStatus = null;
      return NO_VOICE_STATUS;
    });
  return pendingStatus;
}

export function currentVoiceStatus(): VoiceStatus {
  return loadedStatus;
}

export function serverSpeaks(status: VoiceStatus): boolean {
  return status.tts_languages.length > 0;
}

export function useVoiceStatus(): VoiceStatus {
  const [status, setStatus] = useState<VoiceStatus>(loadedStatus);

  useEffect(() => {
    let current = true;
    loadVoiceStatus().then((next) => {
      if (current) setStatus(next);
    });
    return () => {
      current = false;
    };
  }, []);

  return status;
}

export function speechOptionsFor(settings: VoiceSettings, status: VoiceStatus): SpeechOptions {
  return {
    voice: settings.serverVoiceName ?? status.default_voice ?? undefined,
    speed: settings.serverSpeed,
    serverLanguages: status.tts_languages,
  };
}
