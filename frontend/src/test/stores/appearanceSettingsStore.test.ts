import { describe, it, expect, beforeEach } from 'vitest';
import { useAppearanceSettingsStore } from '../../stores/appearanceSettingsStore';

describe('appearanceSettingsStore', () => {
  beforeEach(() => {
    useAppearanceSettingsStore.setState({
      theme: 'dark',
      fontSize: 'medium',
      fontFamily: 'system-ui',
      compactMode: false,
      showAnimations: true,
      highContrast: false,
      sidebarCollapsed: false,
      contextPanelVisible: true,
      notifications: {
        enableDesktopNotifications: true,
        enableSoundNotifications: false,
        notifyOnTaskComplete: true,
        notifyOnErrors: true,
        notifyOnMentions: true,
        quietHoursEnabled: false,
        quietHoursStart: '22:00',
        quietHoursEnd: '08:00',
      },
    });
  });

  describe('theme', () => {
    it('sets theme to light', () => {
      useAppearanceSettingsStore.getState().setTheme('light');
      expect(useAppearanceSettingsStore.getState().theme).toBe('light');
    });

    it('sets theme to system', () => {
      useAppearanceSettingsStore.getState().setTheme('system');
      expect(useAppearanceSettingsStore.getState().theme).toBe('system');
    });
  });

  describe('font', () => {
    it('sets font size', () => {
      useAppearanceSettingsStore.getState().setFontSize('large');
      expect(useAppearanceSettingsStore.getState().fontSize).toBe('large');
    });

    it('sets font family', () => {
      useAppearanceSettingsStore.getState().setFontFamily('Inter');
      expect(useAppearanceSettingsStore.getState().fontFamily).toBe('Inter');
    });
  });

  describe('display', () => {
    it('toggles compact mode', () => {
      useAppearanceSettingsStore.getState().setCompactMode(true);
      expect(useAppearanceSettingsStore.getState().compactMode).toBe(true);
    });

    it('toggles animations', () => {
      useAppearanceSettingsStore.getState().setShowAnimations(false);
      expect(useAppearanceSettingsStore.getState().showAnimations).toBe(false);
    });

    it('toggles high contrast', () => {
      useAppearanceSettingsStore.getState().setHighContrast(true);
      expect(useAppearanceSettingsStore.getState().highContrast).toBe(true);
    });
  });

  describe('layout', () => {
    it('toggles sidebar collapsed', () => {
      useAppearanceSettingsStore.getState().setSidebarCollapsed(true);
      expect(useAppearanceSettingsStore.getState().sidebarCollapsed).toBe(true);
    });

    it('toggles context panel visible', () => {
      useAppearanceSettingsStore.getState().setContextPanelVisible(false);
      expect(useAppearanceSettingsStore.getState().contextPanelVisible).toBe(false);
    });
  });

  describe('notifications', () => {
    it('has default notification settings', () => {
      const { notifications } = useAppearanceSettingsStore.getState();
      expect(notifications.enableDesktopNotifications).toBe(true);
      expect(notifications.enableSoundNotifications).toBe(false);
      expect(notifications.notifyOnTaskComplete).toBe(true);
      expect(notifications.notifyOnErrors).toBe(true);
      expect(notifications.quietHoursEnabled).toBe(false);
    });

    it('updates notification settings partially', () => {
      useAppearanceSettingsStore.getState().updateNotificationSettings({
        enableSoundNotifications: true,
        notifyOnMentions: false,
      });

      const { notifications } = useAppearanceSettingsStore.getState();
      expect(notifications.enableSoundNotifications).toBe(true);
      expect(notifications.notifyOnMentions).toBe(false);
      // Unchanged values remain
      expect(notifications.enableDesktopNotifications).toBe(true);
      expect(notifications.notifyOnTaskComplete).toBe(true);
    });

    it('updates quiet hours', () => {
      useAppearanceSettingsStore.getState().updateNotificationSettings({
        quietHoursEnabled: true,
        quietHoursStart: '23:00',
        quietHoursEnd: '07:00',
      });

      const { notifications } = useAppearanceSettingsStore.getState();
      expect(notifications.quietHoursEnabled).toBe(true);
      expect(notifications.quietHoursStart).toBe('23:00');
      expect(notifications.quietHoursEnd).toBe('07:00');
    });
  });
});
