import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { AccessibilitySettings } from '../../components/settings/AccessibilitySettings';

export function AccessibilitySettingsPage() {
  const navigate = useNavigate();

  return (
    <div className="h-full overflow-y-auto bg-background-primary">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Back button */}
        <button
          onClick={() => navigate('/settings')}
          className="flex items-center gap-2 text-text-secondary hover:text-text-primary mb-6 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
          <span>Back to Settings</span>
        </button>

        {/* Accessibility Settings */}
        <AccessibilitySettings />
      </div>
    </div>
  );
}
