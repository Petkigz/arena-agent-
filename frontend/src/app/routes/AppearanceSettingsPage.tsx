import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../../components/ui';
import { useAppearanceSettingsStore } from '../../stores';
import { ArrowLeft, Palette, Type, Monitor, Layout, Bell } from 'lucide-react';
import { getSharedSettings, updateSharedSettings } from '../../services/api';

interface ToggleSwitchProps {
  checked: boolean;
  onChange: (v: boolean) => void;
}

function ToggleSwitch({ checked, onChange }: ToggleSwitchProps) {
  return (
    <label className="relative inline-flex items-center cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only peer"
      />
      <div className="relative w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-background-surface after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
    </label>
  );
}

export function AppearanceSettingsPage() {
  const navigate = useNavigate();
  const {
    theme,
    fontSize,
    fontFamily,
    compactMode,
    showAnimations,
    highContrast,
    sidebarCollapsed,
    contextPanelVisible,
    notifications,
    setTheme,
    setFontSize,
    setFontFamily,
    setCompactMode,
    setShowAnimations,
    setHighContrast,
    setSidebarCollapsed,
    setContextPanelVisible,
    updateNotificationSettings,
  } = useAppearanceSettingsStore();

  // F2 fix: sync backend theme (single source of truth) so web/desktop/Android stay in sync
  useEffect(() => {
    let cancelled = false;
    getSharedSettings().then((s) => {
      if (cancelled || !s) return;
      const backendTheme = (s as any).theme;
      if (backendTheme === 'dark' || backendTheme === 'light' || backendTheme === 'system') {
        if (backendTheme !== theme) {
          setTheme(backendTheme as any);
        }
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-background-primary">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => navigate('/settings')}
            className="flex items-center gap-2 text-text-secondary hover:text-text-primary mb-4"
          >
            <ArrowLeft className="w-5 h-5" />
            <span>Back to Settings</span>
          </button>
          <h1 className="text-3xl font-bold text-text-primary">Appearance & Notifications</h1>
          <p className="text-text-secondary mt-2">Customize the look and feel of Arena</p>
        </div>

        {/* Theme */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Palette className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Theme</h2>
          </div>
          <Card className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Color Theme</label>
              <div className="grid grid-cols-3 gap-3">
                {(['dark', 'light', 'system'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => {
                      setTheme(t);
                      updateSharedSettings({ theme: t } as any).catch(() => {});
                    }}
                    className={`px-4 py-3 rounded border-2 transition-all ${
                      theme === t
                        ? 'border-accent-primary bg-accent-primary/10'
                        : 'border-border hover:border-accent-primary/50'
                    }`}
                  >
                    <div className="text-center">
                      <div className="text-sm font-medium text-text-primary capitalize">{t}</div>
                      <div className="text-xs text-text-muted mt-1">
                        {t === 'dark' && 'Dark mode'}
                        {t === 'light' && 'Light mode'}
                        {t === 'system' && 'Follow system'}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">High Contrast</h3>
                <p className="text-xs text-text-muted mt-1">Increase contrast for better visibility</p>
              </div>
              <ToggleSwitch checked={highContrast} onChange={setHighContrast} />
            </div>
          </Card>
        </section>

        {/* Font */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Type className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Font</h2>
          </div>
          <Card className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Font Size</label>
              <div className="grid grid-cols-3 gap-3">
                {(['small', 'medium', 'large'] as const).map((size) => (
                  <button
                    key={size}
                    onClick={() => setFontSize(size)}
                    className={`px-4 py-3 rounded border-2 transition-all ${
                      fontSize === size
                        ? 'border-accent-primary bg-accent-primary/10'
                        : 'border-border hover:border-accent-primary/50'
                    }`}
                  >
                    <div className="text-center">
                      <div
                        className={`font-medium text-text-primary ${
                          size === 'small' ? 'text-xs' : size === 'medium' ? 'text-sm' : 'text-base'
                        }`}
                      >
                        {size.charAt(0).toUpperCase() + size.slice(1)}
                      </div>
                      <div className="text-xs text-text-muted mt-1">
                        {size === 'small' && '12px'}
                        {size === 'medium' && '14px'}
                        {size === 'large' && '16px'}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Font Family</label>
              <select
                value={fontFamily}
                onChange={(e) => setFontFamily(e.target.value)}
                className="w-full px-3 py-2 bg-background-surface border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
              >
                <option value="system-ui">System Default</option>
                <option value="Inter">Inter</option>
                <option value="Roboto">Roboto</option>
                <option value="monospace">Monospace</option>
              </select>
            </div>
          </Card>
        </section>

        {/* Display */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Monitor className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Display</h2>
          </div>
          <Card className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Compact Mode</h3>
                <p className="text-xs text-text-muted mt-1">Reduce spacing for more content on screen</p>
              </div>
              <ToggleSwitch checked={compactMode} onChange={setCompactMode} />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Show Animations</h3>
                <p className="text-xs text-text-muted mt-1">Enable smooth animations and transitions</p>
              </div>
              <ToggleSwitch checked={showAnimations} onChange={setShowAnimations} />
            </div>
          </Card>
        </section>

        {/* Layout */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Layout className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Layout</h2>
          </div>
          <Card className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Collapse Sidebar</h3>
                <p className="text-xs text-text-muted mt-1">Show sidebar in collapsed state by default</p>
              </div>
              <ToggleSwitch checked={sidebarCollapsed} onChange={setSidebarCollapsed} />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Show Context Panel</h3>
                <p className="text-xs text-text-muted mt-1">Show context panel on desktop by default</p>
              </div>
              <ToggleSwitch checked={contextPanelVisible} onChange={setContextPanelVisible} />
            </div>
          </Card>
        </section>

        {/* Notifications */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Bell className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Notifications</h2>
          </div>
          <Card className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Desktop Notifications</h3>
                <p className="text-xs text-text-muted mt-1">Show browser notifications</p>
              </div>
              <ToggleSwitch
                checked={notifications.enableDesktopNotifications}
                onChange={(v) => updateNotificationSettings({ enableDesktopNotifications: v })}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Sound Notifications</h3>
                <p className="text-xs text-text-muted mt-1">Play a sound for notifications</p>
              </div>
              <ToggleSwitch
                checked={notifications.enableSoundNotifications}
                onChange={(v) => updateNotificationSettings({ enableSoundNotifications: v })}
              />
            </div>

            <div className="border-t border-border pt-4">
              <h4 className="text-sm font-medium text-text-primary mb-3">Notify me about:</h4>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">Task completions</span>
                  <ToggleSwitch
                    checked={notifications.notifyOnTaskComplete}
                    onChange={(v) => updateNotificationSettings({ notifyOnTaskComplete: v })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">Errors and failures</span>
                  <ToggleSwitch
                    checked={notifications.notifyOnErrors}
                    onChange={(v) => updateNotificationSettings({ notifyOnErrors: v })}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">Mentions</span>
                  <ToggleSwitch
                    checked={notifications.notifyOnMentions}
                    onChange={(v) => updateNotificationSettings({ notifyOnMentions: v })}
                  />
                </div>
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="text-sm font-medium text-text-primary">Quiet Hours</h4>
                  <p className="text-xs text-text-muted mt-1">Mute notifications during set hours</p>
                </div>
                <ToggleSwitch
                  checked={notifications.quietHoursEnabled}
                  onChange={(v) => updateNotificationSettings({ quietHoursEnabled: v })}
                />
              </div>
              {notifications.quietHoursEnabled && (
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <label className="block text-xs text-text-muted mb-1">From</label>
                    <input
                      type="time"
                      value={notifications.quietHoursStart}
                      onChange={(e) =>
                        updateNotificationSettings({ quietHoursStart: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-background-surface border border-border rounded text-sm text-text-primary"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="block text-xs text-text-muted mb-1">To</label>
                    <input
                      type="time"
                      value={notifications.quietHoursEnd}
                      onChange={(e) =>
                        updateNotificationSettings({ quietHoursEnd: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-background-surface border border-border rounded text-sm text-text-primary"
                    />
                  </div>
                </div>
              )}
            </div>
          </Card>
        </section>
      </div>
    </div>
  );
}
