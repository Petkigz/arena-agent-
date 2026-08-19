import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeMode = 'dark' | 'light' | 'system';
export type FontSize = 'small' | 'medium' | 'large';

export interface NotificationSettings {
  enableDesktopNotifications: boolean;
  enableSoundNotifications: boolean;
  notifyOnTaskComplete: boolean;
  notifyOnErrors: boolean;
  notifyOnMentions: boolean;
  quietHoursEnabled: boolean;
  quietHoursStart: string; // "HH:mm" format
  quietHoursEnd: string; // "HH:mm" format
}

interface AppearanceSettingsState {
  // Theme
  theme: ThemeMode;

  // Font
  fontSize: FontSize;
  fontFamily: string;

  // Display
  compactMode: boolean;
  showAnimations: boolean;
  highContrast: boolean;
  largeText: boolean;
  reducedMotion: boolean;

  // Layout
  sidebarCollapsed: boolean;
  contextPanelVisible: boolean;

  // Notifications
  notifications: NotificationSettings;

  // Actions
  setTheme: (theme: ThemeMode) => void;
  setFontSize: (size: FontSize) => void;
  setFontFamily: (family: string) => void;
  setCompactMode: (enabled: boolean) => void;
  setShowAnimations: (enabled: boolean) => void;
  setHighContrast: (enabled: boolean) => void;
  setLargeText: (enabled: boolean) => void;
  setReducedMotion: (enabled: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setContextPanelVisible: (visible: boolean) => void;
  updateNotificationSettings: (updates: Partial<NotificationSettings>) => void;
}

const defaultNotifications: NotificationSettings = {
  enableDesktopNotifications: true,
  enableSoundNotifications: false,
  notifyOnTaskComplete: true,
  notifyOnErrors: true,
  notifyOnMentions: true,
  quietHoursEnabled: false,
  quietHoursStart: '22:00',
  quietHoursEnd: '08:00',
};

export const useAppearanceSettingsStore = create<AppearanceSettingsState>()(
  persist(
    (set) => ({
      // Theme
      theme: 'dark',

      // Font
      fontSize: 'medium',
      fontFamily: 'system-ui',

      // Display
      compactMode: false,
      showAnimations: true,
      highContrast: false,
      largeText: false,
      reducedMotion: false,

      // Layout
      sidebarCollapsed: false,
      contextPanelVisible: true,

      // Notifications
      notifications: { ...defaultNotifications },

      // Actions
      setTheme: (theme) => set({ theme }),
      setFontSize: (size) => set({ fontSize: size }),
      setFontFamily: (family) => set({ fontFamily: family }),
      setCompactMode: (enabled) => set({ compactMode: enabled }),
      setShowAnimations: (enabled) => set({ showAnimations: enabled }),
      setHighContrast: (enabled) => set({ highContrast: enabled }),
      setLargeText: (enabled) => set({ largeText: enabled }),
      setReducedMotion: (enabled) => set({ reducedMotion: enabled }),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      setContextPanelVisible: (visible) => set({ contextPanelVisible: visible }),
      updateNotificationSettings: (updates) =>
        set((state) => ({
          notifications: { ...state.notifications, ...updates },
        })),
    }),
    {
      name: 'arena-appearance-settings',
    }
  )
);
