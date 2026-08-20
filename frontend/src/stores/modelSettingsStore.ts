import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface ModelPerformance {
  speed: number; // 1-10 scale
  quality: number; // 1-10 scale
  memoryUsage: string;
}

export interface ModelConfig {
  id: string;
  name: string;
  description: string;
  size: string;
  performance: ModelPerformance;
  enabled: boolean;
}

export interface ConfidenceThresholds {
  sttMinConfidence: number; // 0.0-1.0, minimum confidence to accept STT result
  intentMinConfidence: number; // 0.0-1.0, minimum confidence for intent detection
  entityMinConfidence: number; // 0.0-1.0, minimum confidence for entity extraction
}

interface ModelSettingsState {
  // LLM Models
  llmModels: ModelConfig[];
  selectedLLM: string;

  // STT Models
  sttModels: ModelConfig[];
  selectedSTT: string;

  // TTS Models
  ttsModels: ModelConfig[];
  selectedTTS: string;

  // Confidence Thresholds
  confidenceThresholds: ConfidenceThresholds;

  // Actions
  setSelectedLLM: (modelId: string) => void;
  setSelectedSTT: (modelId: string) => void;
  setSelectedTTS: (modelId: string) => void;
  toggleModel: (type: 'llm' | 'stt' | 'tts', modelId: string) => void;
  setConfidenceThreshold: (key: keyof ConfidenceThresholds, value: number) => void;
  resetConfidenceThresholds: () => void;

  // Validation
  validateModelConfig: (type: 'llm' | 'stt' | 'tts', modelId: string) => ModelValidationResult;
}

export interface ModelValidationResult {
  valid: boolean;
  modelId: string;
  modelName: string;
  checks: { name: string; passed: boolean; detail: string }[];
}

const defaultConfidenceThresholds: ConfidenceThresholds = {
  sttMinConfidence: 0.7,
  intentMinConfidence: 0.6,
  entityMinConfidence: 0.65,
};

// Default model configurations.
// These must match app/config.py (FAST_MODEL / MAIN_MODEL) — the models actually
// loaded in LM Studio on the i9-14900K + RX 580 machine (CPU inference).
const defaultLLMModels: ModelConfig[] = [
  {
    id: 'qwen2.5-3b-instruct',
    name: 'Qwen 2.5 3B (Fast)',
    description: 'Fast model for quick responses and simple tasks',
    size: '3B parameters',
    performance: {
      speed: 9,
      quality: 6,
      memoryUsage: '~3GB RAM (CPU)',
    },
    enabled: true,
  },
  {
    id: 'qwen2.5-9b-instruct',
    name: 'Qwen 2.5 9B (Reasoning)',
    description: 'Reasoning model for complex analysis and planning',
    size: '9B parameters',
    performance: {
      speed: 5,
      quality: 8,
      memoryUsage: '~8GB RAM (CPU)',
    },
    enabled: true,
  },
];

const defaultSTTModels: ModelConfig[] = [
  {
    id: 'whisper-tiny',
    name: 'Whisper Tiny',
    description: 'Fastest transcription, lower accuracy',
    size: '39M parameters',
    performance: {
      speed: 10,
      quality: 5,
      memoryUsage: '1GB VRAM',
    },
    enabled: true,
  },
  {
    id: 'whisper-base',
    name: 'Whisper Base',
    description: 'Good balance of speed and accuracy',
    size: '74M parameters',
    performance: {
      speed: 8,
      quality: 7,
      memoryUsage: '2GB VRAM',
    },
    enabled: true,
  },
  {
    id: 'whisper-small',
    name: 'Whisper Small',
    description: 'High accuracy, moderate speed',
    size: '244M parameters',
    performance: {
      speed: 6,
      quality: 8,
      memoryUsage: '4GB VRAM',
    },
    enabled: true,
  },
  {
    id: 'whisper-medium',
    name: 'Whisper Medium',
    description: 'Best accuracy, slower speed',
    size: '769M parameters',
    performance: {
      speed: 4,
      quality: 9,
      memoryUsage: '8GB VRAM',
    },
    enabled: false,
  },
];

const defaultTTSModels: ModelConfig[] = [
  {
    id: 'piper-en-us-lessac-medium',
    name: 'Lessac (US English)',
    description: 'Natural female voice, medium quality',
    size: 'Medium',
    performance: {
      speed: 8,
      quality: 8,
      memoryUsage: '500MB',
    },
    enabled: true,
  },
  {
    id: 'piper-en-us-ryan-medium',
    name: 'Ryan (US English)',
    description: 'Natural male voice, medium quality',
    size: 'Medium',
    performance: {
      speed: 8,
      quality: 8,
      memoryUsage: '500MB',
    },
    enabled: true,
  },
  {
    id: 'piper-en-us-hfc-female-medium',
    name: 'HFC Female (US English)',
    description: 'High-quality female voice',
    size: 'Medium',
    performance: {
      speed: 7,
      quality: 9,
      memoryUsage: '600MB',
    },
    enabled: false,
  },
];

export const useModelSettingsStore = create<ModelSettingsState>()(
  persist(
    (set, get) => ({
      llmModels: defaultLLMModels,
      selectedLLM: 'qwen2.5-3b-instruct',

      sttModels: defaultSTTModels,
      selectedSTT: 'whisper-base',

      ttsModels: defaultTTSModels,
      selectedTTS: 'piper-en-us-lessac-medium',

      confidenceThresholds: { ...defaultConfidenceThresholds },

      setSelectedLLM: (modelId) => set({ selectedLLM: modelId }),
      setSelectedSTT: (modelId) => set({ selectedSTT: modelId }),
      setSelectedTTS: (modelId) => set({ selectedTTS: modelId }),

      toggleModel: (type, modelId) =>
        set((state) => {
          const key = type === 'llm' ? 'llmModels' : type === 'stt' ? 'sttModels' : 'ttsModels';
          return {
            [key]: state[key].map((m: ModelConfig) =>
              m.id === modelId ? { ...m, enabled: !m.enabled } : m
            ),
          } as Partial<ModelSettingsState>;
        }),

      setConfidenceThreshold: (key, value) =>
        set((state) => ({
          confidenceThresholds: {
            ...state.confidenceThresholds,
            [key]: Math.max(0, Math.min(1, value)),
          },
        })),

      resetConfidenceThresholds: () =>
        set({ confidenceThresholds: { ...defaultConfidenceThresholds } }),

      validateModelConfig: (type, modelId) => {
        const state = get();
        const models =
          type === 'llm' ? state.llmModels : type === 'stt' ? state.sttModels : state.ttsModels;
        const model = models.find((m) => m.id === modelId);

        if (!model) {
          return {
            valid: false,
            modelId,
            modelName: 'Unknown',
            checks: [
              { name: 'Model exists', passed: false, detail: `Model ${modelId} not found` },
            ],
          };
        }

        const checks: { name: string; passed: boolean; detail: string }[] = [];

        // Check: model exists
        checks.push({
          name: 'Model exists',
          passed: true,
          detail: `${model.name} found in ${type.toUpperCase()} models`,
        });

        // Check: model is enabled
        checks.push({
          name: 'Model enabled',
          passed: model.enabled,
          detail: model.enabled ? 'Model is enabled' : 'Model is disabled',
        });

        // Check: memory requirements (parse VRAM)
        const memMatch = model.performance.memoryUsage.match(/(\d+)\s*GB/);
        if (memMatch) {
          const vramNeeded = parseInt(memMatch[1], 10);
          // Assume 24GB as max available (high-end GPU)
          const maxAvailable = 24;
          checks.push({
            name: 'Memory check',
            passed: vramNeeded <= maxAvailable,
            detail: `Requires ${vramNeeded}GB, max available ${maxAvailable}GB`,
          });
        } else {
          checks.push({
            name: 'Memory check',
            passed: true,
            detail: `${model.performance.memoryUsage} — within typical limits`,
          });
        }

        // Check: quality/speed tradeoff warning
        if (model.performance.speed <= 4 && model.performance.quality >= 8) {
          checks.push({
            name: 'Performance note',
            passed: true,
            detail: 'High quality but slow — best for non-realtime tasks',
          });
        }

        const valid = checks.every((c) => c.passed || c.name === 'Performance note');

        return { valid, modelId, modelName: model.name, checks };
      },
    }),
    {
      name: 'arena-model-settings',
    }
  )
);
