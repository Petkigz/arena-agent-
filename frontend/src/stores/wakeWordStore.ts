import { logger } from '../services/logger';
import { create } from 'zustand';
import { notifications } from '../services/notifications';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface WakeWordSample {
  id: string;
  audio: string; // Base64 encoded
  timestamp: string;
  duration: number;
  sampleRate: number;
  channels: number;
}

export interface WakeWordModel {
  id: string;
  name: string;
  wakeWord: string;
  modelPath: string;
  createdAt: string;
  sampleCount: number;
  accuracy?: number;
  isActive: boolean;
}

interface WakeWordStoreState {
  samples: WakeWordSample[];
  models: WakeWordModel[];
  activeModel: WakeWordModel | null;
  isRecording: boolean;
  isTraining: boolean;

  // Actions
  addSample: (sample: WakeWordSample) => void;
  removeSample: (sampleId: string) => void;
  clearSamples: () => void;
  setRecording: (recording: boolean) => void;
  setTraining: (training: boolean) => void;
  fetchModels: () => Promise<void>;
  trainModel: (wakeWord: string, sensitivity?: number) => Promise<boolean>;
  activateModel: (modelId: string) => Promise<boolean>;
  deleteModel: (modelId: string) => Promise<boolean>;
  fetchActiveModel: () => Promise<void>;
}

export const useWakeWordStore = create<WakeWordStoreState>((set, get) => ({
  samples: [],
  models: [],
  activeModel: null,
  isRecording: false,
  isTraining: false,

  addSample: (sample) =>
    set((state) => ({
      samples: [...state.samples, sample],
    })),

  removeSample: (sampleId) =>
    set((state) => ({
      samples: state.samples.filter((s) => s.id !== sampleId),
    })),

  clearSamples: () => set({ samples: [] }),

  setRecording: (recording) => set({ isRecording: recording }),

  setTraining: (training) => set({ isTraining: training }),

  fetchModels: async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/wakeword/models');
      if (!response.ok) throw new Error('Failed to fetch models');

      const models = await response.json();
      set({ models });
    } catch (error) {
      logger.error('Failed to fetch wake word models', error);
    }
  },

  trainModel: async (wakeWord, sensitivity = 0.5) => {
    const { samples } = get();

    if (samples.length < 5) {
      notifications.warning('At least 5 samples required for training');
      return false;
    }

    set({ isTraining: true });

    try {
      const response = await fetch(API_BASE_URL + '/api/wakeword/train', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          wake_word: wakeWord,
          samples,
          sensitivity,
        }),
      });

      if (!response.ok) throw new Error('Training failed');

      const result = await response.json();

      if (result.success) {
        // Refresh models
        await get().fetchModels();
        set({ samples: [] }); // Clear samples after successful training
        notifications.success('Wake word model trained successfully!');
        return true;
      } else {
        notifications.error(`Training failed: ${result.error}`);
        return false;
      }
    } catch (error) {
      logger.error('Failed to train wake word model', error);
      notifications.error('Failed to train wake word model');
      return false;
    } finally {
      set({ isTraining: false });
    }
  },

  activateModel: async (modelId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/wakeword/models/${modelId}/activate`, {
        method: 'POST',
      });

      if (!response.ok) throw new Error('Failed to activate model');

      await get().fetchModels();
      await get().fetchActiveModel();

      notifications.success('Wake word model activated!');
      return true;
    } catch (error) {
      logger.error('Failed to activate wake word model', error);
      notifications.error('Failed to activate wake word model');
      return false;
    }
  },

  deleteModel: async (modelId) => {
    if (!confirm('Are you sure you want to delete this wake word model?')) {
      return false;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/wakeword/models/${modelId}`, {
        method: 'DELETE',
      });

      if (!response.ok) throw new Error('Failed to delete model');

      await get().fetchModels();
      await get().fetchActiveModel();

      notifications.success('Wake word model deleted!');
      return true;
    } catch (error) {
      logger.error('Failed to delete wake word model', error);
      notifications.error('Failed to delete wake word model');
      return false;
    }
  },

  fetchActiveModel: async () => {
    try {
      const response = await fetch(API_BASE_URL + '/api/wakeword/active');
      if (!response.ok) throw new Error('Failed to fetch active model');

      const result = await response.json();
      set({ activeModel: result.success ? result.model : null });
    } catch (error) {
      logger.error('Failed to fetch active wake word model', error);
    }
  },
}));
