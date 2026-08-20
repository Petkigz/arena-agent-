import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface SettingsState {
  wakeWord: string;
  language: string;
  noiseSuppression: boolean;
  voiceEnabled: boolean;
  voiceSpeed: number;
  selectedVoice: string;
  vadSensitivity: number; // 0-100
  responseDelay: number; // 0-2000ms

  // Actions
  setWakeWord: (wakeWord: string) => void;
  setLanguage: (language: string) => void;
  setNoiseSuppression: (enabled: boolean) => void;
  setVoiceEnabled: (enabled: boolean) => void;
  setVoiceSpeed: (speed: number) => void;
  setSelectedVoice: (voice: string) => void;
  setVadSensitivity: (sensitivity: number) => void;
  setResponseDelay: (delay: number) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      wakeWord: 'hey_lumi',
      language: 'en_US',
      noiseSuppression: true,
      voiceEnabled: true,
      voiceSpeed: 1.0,
      selectedVoice: 'default',
      vadSensitivity: 50,
      responseDelay: 500,

      setWakeWord: (wakeWord) => set({ wakeWord }),
      setLanguage: (language) => set({ language }),
      setNoiseSuppression: (enabled) => set({ noiseSuppression: enabled }),
      setVoiceEnabled: (enabled) => set({ voiceEnabled: enabled }),
      setVoiceSpeed: (speed) => set({ voiceSpeed: speed }),
      setSelectedVoice: (voice) => set({ selectedVoice: voice }),
      setVadSensitivity: (sensitivity) => set({ vadSensitivity: sensitivity }),
      setResponseDelay: (delay) => set({ responseDelay: delay }),
    }),
    {
      name: 'arena-settings',
    }
  )
);
