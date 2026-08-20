import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type OnboardingStep = 
  | 'welcome'
  | 'wake-word'
  | 'permissions'
  | 'pairing'
  | 'tutorial'
  | 'complete';

interface OnboardingState {
  completed: boolean;
  currentStep: OnboardingStep;
  completedSteps: OnboardingStep[];
  wakeWordSamples: string[];
  permissionsGranted: {
    microphone: boolean;
    notifications: boolean;
  };
  pairedDevices: string[];
  
  // Actions
  startOnboarding: () => void;
  completeStep: (step: OnboardingStep) => void;
  setCurrentStep: (step: OnboardingStep) => void;
  addWakeWordSample: (sample: string) => void;
  setPermissionGranted: (permission: 'microphone' | 'notifications', granted: boolean) => void;
  addPairedDevice: (deviceId: string) => void;
  finishOnboarding: () => void;
  resetOnboarding: () => void;
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      completed: false,
      currentStep: 'welcome',
      completedSteps: [],
      wakeWordSamples: [],
      permissionsGranted: {
        microphone: false,
        notifications: false,
      },
      pairedDevices: [],

      startOnboarding: () =>
        set({
          completed: false,
          currentStep: 'welcome',
          completedSteps: [],
        }),

      completeStep: (step) =>
        set((state) => ({
          completedSteps: [...state.completedSteps, step],
        })),

      setCurrentStep: (step) => set({ currentStep: step }),

      addWakeWordSample: (sample) =>
        set((state) => ({
          wakeWordSamples: [...state.wakeWordSamples, sample],
        })),

      setPermissionGranted: (permission, granted) =>
        set((state) => ({
          permissionsGranted: {
            ...state.permissionsGranted,
            [permission]: granted,
          },
        })),

      addPairedDevice: (deviceId) =>
        set((state) => ({
          pairedDevices: [...state.pairedDevices, deviceId],
        })),

      finishOnboarding: () =>
        set({
          completed: true,
          currentStep: 'complete',
        }),

      resetOnboarding: () =>
        set({
          completed: false,
          currentStep: 'welcome',
          completedSteps: [],
          wakeWordSamples: [],
          permissionsGranted: {
            microphone: false,
            notifications: false,
          },
          pairedDevices: [],
        }),
    }),
    {
      name: 'arena-onboarding',
    }
  )
);
