import { describe, it, expect, beforeEach } from 'vitest';
import { useModelSettingsStore } from '../../stores/modelSettingsStore';

describe('modelSettingsStore', () => {
  beforeEach(() => {
    useModelSettingsStore.setState({
      selectedLLM: 'qwen2.5-3b-instruct',
      selectedSTT: 'whisper-base',
      selectedTTS: 'piper-en-us-lessac-medium',
      confidenceThresholds: {
        sttMinConfidence: 0.7,
        intentMinConfidence: 0.6,
        entityMinConfidence: 0.65,
      },
    });
  });

  describe('model selection', () => {
    it('has default model selections', () => {
      const state = useModelSettingsStore.getState();
      expect(state.selectedLLM).toBe('qwen2.5-3b-instruct');
      expect(state.selectedSTT).toBe('whisper-base');
      expect(state.selectedTTS).toBe('piper-en-us-lessac-medium');
    });

    it('changes selected LLM', () => {
      useModelSettingsStore.getState().setSelectedLLM('qwen2.5-9b-instruct');
      expect(useModelSettingsStore.getState().selectedLLM).toBe('qwen2.5-9b-instruct');
    });

    it('changes selected STT', () => {
      useModelSettingsStore.getState().setSelectedSTT('whisper-small');
      expect(useModelSettingsStore.getState().selectedSTT).toBe('whisper-small');
    });

    it('changes selected TTS', () => {
      useModelSettingsStore.getState().setSelectedTTS('piper-en-us-ryan-medium');
      expect(useModelSettingsStore.getState().selectedTTS).toBe('piper-en-us-ryan-medium');
    });
  });

  describe('model toggling', () => {
    it('toggles LLM model enabled state', () => {
      const before = useModelSettingsStore.getState().llmModels.find((m) => m.id === 'qwen2.5-3b-instruct');
      expect(before?.enabled).toBe(true);

      useModelSettingsStore.getState().toggleModel('llm', 'qwen2.5-3b-instruct');

      const after = useModelSettingsStore.getState().llmModels.find((m) => m.id === 'qwen2.5-3b-instruct');
      expect(after?.enabled).toBe(false);
    });

    it('toggles STT model enabled state', () => {
      useModelSettingsStore.getState().toggleModel('stt', 'whisper-tiny');
      const model = useModelSettingsStore.getState().sttModels.find((m) => m.id === 'whisper-tiny');
      expect(model?.enabled).toBe(false);
    });

    it('toggles TTS model enabled state', () => {
      useModelSettingsStore.getState().toggleModel('tts', 'piper-en-us-lessac-medium');
      const model = useModelSettingsStore.getState().ttsModels.find(
        (m) => m.id === 'piper-en-us-lessac-medium'
      );
      expect(model?.enabled).toBe(false);
    });
  });

  describe('confidence thresholds', () => {
    it('has default thresholds', () => {
      const { confidenceThresholds } = useModelSettingsStore.getState();
      expect(confidenceThresholds.sttMinConfidence).toBe(0.7);
      expect(confidenceThresholds.intentMinConfidence).toBe(0.6);
      expect(confidenceThresholds.entityMinConfidence).toBe(0.65);
    });

    it('sets STT confidence threshold', () => {
      useModelSettingsStore.getState().setConfidenceThreshold('sttMinConfidence', 0.85);
      expect(useModelSettingsStore.getState().confidenceThresholds.sttMinConfidence).toBe(0.85);
    });

    it('sets intent confidence threshold', () => {
      useModelSettingsStore.getState().setConfidenceThreshold('intentMinConfidence', 0.75);
      expect(useModelSettingsStore.getState().confidenceThresholds.intentMinConfidence).toBe(0.75);
    });

    it('clamps threshold to 0-1 range', () => {
      useModelSettingsStore.getState().setConfidenceThreshold('sttMinConfidence', 1.5);
      expect(useModelSettingsStore.getState().confidenceThresholds.sttMinConfidence).toBe(1);

      useModelSettingsStore.getState().setConfidenceThreshold('sttMinConfidence', -0.5);
      expect(useModelSettingsStore.getState().confidenceThresholds.sttMinConfidence).toBe(0);
    });

    it('resets thresholds to defaults', () => {
      useModelSettingsStore.getState().setConfidenceThreshold('sttMinConfidence', 0.99);
      useModelSettingsStore.getState().setConfidenceThreshold('intentMinConfidence', 0.99);
      useModelSettingsStore.getState().resetConfidenceThresholds();

      const { confidenceThresholds } = useModelSettingsStore.getState();
      expect(confidenceThresholds.sttMinConfidence).toBe(0.7);
      expect(confidenceThresholds.intentMinConfidence).toBe(0.6);
    });
  });

  describe('model validation', () => {
    it('validates existing enabled model', () => {
      // Ensure model is enabled first
      const model = useModelSettingsStore.getState().llmModels.find((m) => m.id === 'qwen2.5-3b-instruct');
      if (!model?.enabled) {
        useModelSettingsStore.getState().toggleModel('llm', 'qwen2.5-3b-instruct');
      }

      const result = useModelSettingsStore.getState().validateModelConfig('llm', 'qwen2.5-3b-instruct');
      expect(result.valid).toBe(true);
      expect(result.modelName).toBe('Qwen 2.5 3B (Fast)');
      expect(result.checks.length).toBeGreaterThan(0);
    });

    it('validates disabled model shows disabled check', () => {
      // Ensure model is enabled first, then disable it
      const model = useModelSettingsStore.getState().llmModels.find((m) => m.id === 'qwen2.5-9b-instruct');
      if (!model?.enabled) {
        useModelSettingsStore.getState().toggleModel('llm', 'qwen2.5-9b-instruct');
      }
      // Now disable it
      useModelSettingsStore.getState().toggleModel('llm', 'qwen2.5-9b-instruct');

      const result = useModelSettingsStore.getState().validateModelConfig('llm', 'qwen2.5-9b-instruct');
      const enabledCheck = result.checks.find((c) => c.name === 'Model enabled');
      expect(enabledCheck?.passed).toBe(false);

      // Re-enable for other tests
      useModelSettingsStore.getState().toggleModel('llm', 'qwen2.5-9b-instruct');
    });

    it('returns invalid for non-existent model', () => {
      const result = useModelSettingsStore.getState().validateModelConfig('llm', 'nonexistent');
      expect(result.valid).toBe(false);
      expect(result.modelName).toBe('Unknown');
    });
  });

  describe('type safety', () => {
    it('ModelConfig has no any types', () => {
      const model = useModelSettingsStore.getState().llmModels[0];
      expect(typeof model.id).toBe('string');
      expect(typeof model.name).toBe('string');
      expect(typeof model.performance.speed).toBe('number');
      expect(typeof model.performance.quality).toBe('number');
      expect(typeof model.performance.memoryUsage).toBe('string');
      expect(typeof model.enabled).toBe('boolean');
    });
  });
});
