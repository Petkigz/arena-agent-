export type PresenceStatus = 'idle' | 'working' | 'listening' | 'speaking' | 'offline';

export interface PresenceState {
  status: PresenceStatus;
  currentTask?: string;
  currentGoal?: string;
  progress?: number;
  message?: string;
}

export interface QuickAction {
  id: string;
  label: string;
  icon?: string;
  action: string;
  context?: Record<string, string | number | boolean>;
}
