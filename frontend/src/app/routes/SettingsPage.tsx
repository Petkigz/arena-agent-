import { useNavigate } from 'react-router-dom';
import { Card } from '../../components/ui';
import { useSettingsStore, useModelSettingsStore, useAppearanceSettingsStore } from '../../stores';
import { Settings, Mic, Brain, Shield, Palette, ChevronRight, Accessibility, Sparkles } from 'lucide-react';

export function SettingsPage() {
  const navigate = useNavigate();
  const { voiceEnabled, wakeWord, selectedVoice } = useSettingsStore();
  const { selectedLLM, selectedSTT, selectedTTS, llmModels, sttModels, ttsModels } = useModelSettingsStore();
  const { theme, fontSize, highContrast, largeText, reducedMotion } = useAppearanceSettingsStore();

  const getLLMName = () => llmModels.find((m) => m.id === selectedLLM)?.name || selectedLLM;
  const getSTTName = () => sttModels.find((m) => m.id === selectedSTT)?.name || selectedSTT;
  const getTTSName = () => ttsModels.find((m) => m.id === selectedTTS)?.name || selectedTTS;

  const accessibilityFeatures = [
    highContrast && 'High contrast',
    largeText && 'Large text',
    reducedMotion && 'Reduced motion',
  ].filter(Boolean).join(' • ') || 'Default settings';

  const settingsSections = [
    {
      id: 'voice',
      title: 'Voice Settings',
      description: 'Configure wake word, voice selection, and speech settings',
      icon: Mic,
      route: '/settings/voice',
      color: 'text-accent-primary',
      summary: voiceEnabled
        ? `Wake: "${wakeWord}" • Voice: ${selectedVoice}`
        : 'Voice disabled',
    },
    {
      id: 'models',
      title: 'Model Configuration',
      description: 'Select LLM, STT, and TTS models',
      icon: Brain,
      route: '/settings/models',
      color: 'text-accent-secondary',
      summary: `LLM: ${getLLMName()} • STT: ${getSTTName()} • TTS: ${getTTSName()}`,
    },
    {
      id: 'privacy',
      title: 'Privacy & Security',
      description: 'Data retention, telemetry, and security settings',
      icon: Shield,
      route: '/settings/privacy',
      color: 'text-accent-success',
      summary: null,
    },
    {
      id: 'cognition',
      title: 'Cognition',
      description: 'Charter, uncertainty questions, induced skills, learning progress',
      icon: Sparkles,
      route: '/settings/cognition',
      color: 'text-accent-warning',
      summary: null,
    },
    {
      id: 'appearance',
      title: 'Appearance & Notifications',
      description: 'Theme, font, display, and notification preferences',
      icon: Palette,
      route: '/settings/appearance',
      color: 'text-accent-secondary',
      summary: `Theme: ${theme} • Font: ${fontSize}`,
    },
    {
      id: 'accessibility',
      title: 'Accessibility',
      description: 'Visual settings, motion preferences, and screen reader support',
      icon: Accessibility,
      route: '/settings/accessibility',
      color: 'text-accent-warning',
      summary: accessibilityFeatures,
    },
  ];

  return (
    <div className="h-full overflow-y-auto bg-background-primary">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Settings className="w-8 h-8 text-accent-primary" />
            <h1 className="text-3xl font-bold text-text-primary">Settings</h1>
          </div>
          <p className="text-text-secondary">
            Configure Arena's behavior, appearance, and integrations
          </p>
        </div>

        {/* Settings Sections */}
        <div className="grid gap-4">
          {settingsSections.map((section) => {
            const Icon = section.icon;

            return (
              <div
                key={section.id}
                className="cursor-pointer"
                onClick={() => navigate(section.route)}
              >
                <Card className="transition-all hover:border-accent-primary hover:shadow-lg">
                  <div className="flex items-start gap-4">
                    <div className={`p-3 rounded-lg bg-background-surface ${section.color}`}>
                      <Icon className="w-6 h-6" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-lg font-semibold text-text-primary">{section.title}</h3>
                      <p className="text-sm text-text-secondary mt-1">{section.description}</p>
                      {section.summary && (
                        <p className="text-xs text-text-muted mt-2 truncate">{section.summary}</p>
                      )}
                    </div>
                    <ChevronRight className="w-5 h-5 text-text-muted flex-shrink-0 mt-1" />
                  </div>
                </Card>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-sm text-text-muted">
          <p>Arena v0.1.0 • Built with ❤️ for productivity</p>
        </div>
      </div>
    </div>
  );
}
