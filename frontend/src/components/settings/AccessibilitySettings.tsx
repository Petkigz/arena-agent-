import { useAppearanceSettingsStore } from '../../stores';
import { Card } from '../ui/Card';
import { Eye, Type, Activity, Info } from 'lucide-react';
import { notifications } from '../services/notifications';

export function AccessibilitySettings() {
  const {
    highContrast,
    largeText,
    reducedMotion,
    setHighContrast,
    setLargeText,
    setReducedMotion,
  } = useAppearanceSettingsStore();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-text-primary mb-2">Accessibility</h2>
        <p className="text-text-secondary">
          Customize Arena to meet your accessibility needs
        </p>
      </div>

      {/* Visual Settings */}
      <Card>
        <div className="flex items-start gap-3 mb-4">
          <Eye className="w-5 h-5 text-accent-primary flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-text-primary mb-1">Visual Settings</h3>
            <p className="text-sm text-text-secondary">
              Adjust visual appearance for better readability
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {/* High Contrast Mode */}
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <label className="font-medium text-text-primary block mb-1">
                High Contrast Mode
              </label>
              <p className="text-sm text-text-secondary">
                Increase contrast between text and background for better visibility
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={highContrast}
                onChange={(e) => setHighContrast(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
            </label>
          </div>

          {/* Large Text Mode */}
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <label className="font-medium text-text-primary block mb-1">
                Large Text
              </label>
              <p className="text-sm text-text-secondary">
                Increase text size throughout the application
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={largeText}
                onChange={(e) => setLargeText(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
            </label>
          </div>
        </div>
      </Card>

      {/* Motion Settings */}
      <Card>
        <div className="flex items-start gap-3 mb-4">
          <Activity className="w-5 h-5 text-accent-primary flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-text-primary mb-1">Motion Settings</h3>
            <p className="text-sm text-text-secondary">
              Control animations and transitions
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {/* Reduced Motion */}
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <label className="font-medium text-text-primary block mb-1">
                Reduced Motion
              </label>
              <p className="text-sm text-text-secondary">
                Minimize animations and transitions for users sensitive to motion
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={reducedMotion}
                onChange={(e) => setReducedMotion(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
            </label>
          </div>
        </div>
      </Card>

      {/* Screen Reader Settings */}
      <Card>
        <div className="flex items-start gap-3 mb-4">
          <Type className="w-5 h-5 text-accent-primary flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-text-primary mb-1">Screen Reader</h3>
            <p className="text-sm text-text-secondary">
              Arena is optimized for screen readers
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-start gap-2 text-sm text-text-secondary">
            <span className="text-accent-primary mt-0.5">✓</span>
            <span>ARIA labels on all interactive elements</span>
          </div>
          <div className="flex items-start gap-2 text-sm text-text-secondary">
            <span className="text-accent-primary mt-0.5">✓</span>
            <span>Keyboard navigation support</span>
          </div>
          <div className="flex items-start gap-2 text-sm text-text-secondary">
            <span className="text-accent-primary mt-0.5">✓</span>
            <span>Focus indicators on all focusable elements</span>
          </div>
          <div className="flex items-start gap-2 text-sm text-text-secondary">
            <span className="text-accent-primary mt-0.5">✓</span>
            <span>Skip to main content link</span>
          </div>
          <div className="flex items-start gap-2 text-sm text-text-secondary">
            <span className="text-accent-primary mt-0.5">✓</span>
            <span>Live regions for dynamic content updates</span>
          </div>
        </div>
      </Card>

      {/* Info Box */}
      <div className="bg-accent-primary/10 border border-accent-primary/30 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <Info className="w-5 h-5 text-accent-primary flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-text-primary mb-1">
              Need More Accessibility Features?
            </h4>
            <p className="text-sm text-text-secondary mb-2">
              If you need additional accessibility features or have suggestions for improvement, please let us know.
            </p>
            <button
              onClick={() => {
                // In production, this would open a feedback form
                notifications.info('Accessibility feedback will be available in a future update.');
              }}
              className="text-sm text-accent-primary hover:underline"
            >
              Provide Feedback
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
