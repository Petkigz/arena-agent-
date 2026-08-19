import { describe, it, expect, beforeEach } from 'vitest';
import { useSettingsStore } from '../../stores/settingsStore';

describe('settingsStore', () => {
  beforeEach(() => {
    useSettingsStore.setState({
      wakeWord: 'hey_lumi',
      language: 'en_US',
      noiseSuppression: true,
      voiceEnabled: true,
      voiceSpeed: 1.0,
      selectedVoice: 'default',
      vadSensitivity: 50,
      responseDelay: 500,
    });
  });

  it('has correct default values', () => {
    const state = useSettingsStore.getState();
    expect(state.wakeWord).toBe('hey_lumi');
    expect(state.voiceSpeed).toBe(1.0);
    expect(state.selectedVoice).toBe('default');
    expect(state.noiseSuppression).toBe(true);
    expect(state.voiceEnabled).toBe(true);
    expect(state.vadSensitivity).toBe(50);
    expect(state.responseDelay).toBe(500);
  });

  it('sets wake word', () => {
    useSettingsStore.getState().setWakeWord('hey_arena');
    expect(useSettingsStore.getState().wakeWord).toBe('hey_arena');
  });

  it('sets voice speed', () => {
    useSettingsStore.getState().setVoiceSpeed(1.5);
    expect(useSettingsStore.getState().voiceSpeed).toBe(1.5);
  });

  it('sets selected voice', () => {
    useSettingsStore.getState().setSelectedVoice('professional');
    expect(useSettingsStore.getState().selectedVoice).toBe('professional');
  });

  it('toggles noise suppression', () => {
    useSettingsStore.getState().setNoiseSuppression(false);
    expect(useSettingsStore.getState().noiseSuppression).toBe(false);
  });

  it('toggles voice enabled', () => {
    useSettingsStore.getState().setVoiceEnabled(false);
    expect(useSettingsStore.getState().voiceEnabled).toBe(false);
  });

  it('sets VAD sensitivity', () => {
    useSettingsStore.getState().setVadSensitivity(75);
    expect(useSettingsStore.getState().vadSensitivity).toBe(75);
  });

  it('sets response delay', () => {
    useSettingsStore.getState().setResponseDelay(1000);
    expect(useSettingsStore.getState().responseDelay).toBe(1000);
  });

  it('does not have a theme field (removed duplicate)', () => {
    const state = useSettingsStore.getState() as unknown as Record<string, unknown>;
    expect(state.theme).toBeUndefined();
  });
});
