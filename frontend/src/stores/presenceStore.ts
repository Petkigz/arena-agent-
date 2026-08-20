import { create } from 'zustand';
import type { PresenceState, QuickAction } from '../types';

interface PresenceStoreState {
  presence: PresenceState;
  quickActions: QuickAction[];

  // Actions
  setPresence: (presence: PresenceState) => void;
  setQuickActions: (actions: QuickAction[]) => void;
}

export const usePresenceStore = create<PresenceStoreState>((set) => ({
  presence: {
    status: 'idle',
    message: "I'm here.",
  },
  quickActions: [
    { id: 'continue', label: 'Continue project', action: 'continue_project' },
    { id: 'whats-new', label: "What's new?", action: 'whats_new' },
    { id: 'research', label: 'Research', action: 'research' },
    { id: 'talk', label: 'Talk to me', action: 'talk' },
  ],

  setPresence: (presence) => set({ presence }),
  setQuickActions: (actions) => set({ quickActions: actions }),
}));
