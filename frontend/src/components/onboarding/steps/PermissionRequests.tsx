import { logger } from '../../../services/logger';
import { useState } from 'react';
import { Button } from '../../ui/Button';
import { Mic, Bell, ArrowRight, ArrowLeft, SkipForward, Check, X } from 'lucide-react';
import { useOnboardingStore } from '../../../stores/onboardingStore';

interface PermissionRequestsProps {
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}

export function PermissionRequests({ onNext, onBack, onSkip }: PermissionRequestsProps) {
  const { setPermissionGranted, permissionsGranted } = useOnboardingStore();
  const [requestingMic, setRequestingMic] = useState(false);
  const [requestingNotif, setRequestingNotif] = useState(false);

  const requestMicrophonePermission = async () => {
    setRequestingMic(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(track => track.stop());
      setPermissionGranted('microphone', true);
    } catch (error) {
      logger.error('Microphone permission denied:', error);
      setPermissionGranted('microphone', false);
    } finally {
      setRequestingMic(false);
    }
  };

  const requestNotificationPermission = async () => {
    setRequestingNotif(true);
    try {
      if ('Notification' in window) {
        const permission = await Notification.requestPermission();
        setPermissionGranted('notifications', permission === 'granted');
      } else {
        setPermissionGranted('notifications', false);
      }
    } catch (error) {
      logger.error('Notification permission error:', error);
      setPermissionGranted('notifications', false);
    } finally {
      setRequestingNotif(false);
    }
  };

  const allGranted = permissionsGranted.microphone && permissionsGranted.notifications;

  return (
    <div className="max-w-2xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="text-center mb-8">
        <h2 className="text-3xl font-bold text-text-primary mb-3">
          Permissions
        </h2>
        <p className="text-text-secondary">
          Arena needs access to certain features to work properly
        </p>
      </div>

      {/* Permissions list */}
      <div className="space-y-4 mb-8">
        {/* Microphone permission */}
        <div className="bg-background-secondary rounded-lg p-6">
          <div className="flex items-start gap-4">
            <div className={`
              flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center
              ${permissionsGranted.microphone 
                ? 'bg-accent-success/10' 
                : 'bg-accent-primary/10'
              }
            `}>
              {permissionsGranted.microphone ? (
                <Check className="w-6 h-6 text-accent-success" />
              ) : (
                <Mic className="w-6 h-6 text-accent-primary" />
              )}
            </div>

            <div className="flex-1">
              <h3 className="font-semibold text-text-primary mb-1">Microphone Access</h3>
              <p className="text-sm text-text-secondary mb-3">
                Required for voice interaction. Arena will listen for your wake word and process your speech.
              </p>

              {permissionsGranted.microphone ? (
                <div className="flex items-center gap-2 text-sm text-accent-success">
                  <Check className="w-4 h-4" />
                  <span>Permission granted</span>
                </div>
              ) : (
                <Button
                  onClick={requestMicrophonePermission}
                  disabled={requestingMic}
                  variant="secondary"
                  size="sm"
                >
                  {requestingMic ? 'Requesting...' : 'Grant Permission'}
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Notification permission */}
        <div className="bg-background-secondary rounded-lg p-6">
          <div className="flex items-start gap-4">
            <div className={`
              flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center
              ${permissionsGranted.notifications 
                ? 'bg-accent-success/10' 
                : 'bg-accent-primary/10'
              }
            `}>
              {permissionsGranted.notifications ? (
                <Check className="w-6 h-6 text-accent-success" />
              ) : (
                <Bell className="w-6 h-6 text-accent-primary" />
              )}
            </div>

            <div className="flex-1">
              <h3 className="font-semibold text-text-primary mb-1">Notifications</h3>
              <p className="text-sm text-text-secondary mb-3">
                Optional. Get notified when tasks complete or when Arena needs your attention.
              </p>

              {permissionsGranted.notifications ? (
                <div className="flex items-center gap-2 text-sm text-accent-success">
                  <Check className="w-4 h-4" />
                  <span>Permission granted</span>
                </div>
              ) : (
                <Button
                  onClick={requestNotificationPermission}
                  disabled={requestingNotif}
                  variant="secondary"
                  size="sm"
                >
                  {requestingNotif ? 'Requesting...' : 'Enable Notifications'}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Info box */}
      <div className="bg-background-secondary/50 rounded-lg p-6 mb-8">
        <h3 className="font-semibold text-text-primary mb-3">Why we need these permissions:</h3>
        <ul className="space-y-2 text-sm text-text-secondary">
          <li className="flex items-start gap-2">
            <Mic className="w-4 h-4 text-accent-primary mt-0.5 flex-shrink-0" />
            <span>
              <strong>Microphone:</strong> Enables voice commands and natural conversation with Arena
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Bell className="w-4 h-4 text-accent-primary mt-0.5 flex-shrink-0" />
            <span>
              <strong>Notifications:</strong> Alerts you when long-running tasks complete or when approval is needed
            </span>
          </li>
        </ul>
        <p className="text-xs text-text-muted mt-4">
          You can change these permissions anytime in your browser settings or in Arena Settings → Privacy
        </p>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-3">
        <Button
          onClick={onNext}
          disabled={!permissionsGranted.microphone}
          size="lg"
          className="w-full"
        >
          {allGranted ? 'Continue' : permissionsGranted.microphone ? 'Continue (notifications optional)' : 'Grant microphone permission to continue'}
          <ArrowRight className="w-5 h-5 ml-2" />
        </Button>

        <div className="flex gap-3">
          <Button onClick={onBack} variant="secondary" size="lg" className="flex-1">
            <ArrowLeft className="w-5 h-5 mr-2" />
            Back
          </Button>

          <button
            onClick={onSkip}
            className="flex items-center justify-center gap-2 text-text-muted hover:text-text-secondary transition-colors flex-1"
          >
            <SkipForward className="w-4 h-4" />
            <span className="text-sm">Skip setup</span>
          </button>
        </div>
      </div>

      {/* Warning if microphone not granted */}
      {!permissionsGranted.microphone && (
        <div className="mt-6 p-4 bg-accent-warning/10 border border-accent-warning/30 rounded-lg">
          <div className="flex items-start gap-3">
            <X className="w-5 h-5 text-accent-warning flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-accent-warning mb-1">
                Microphone access required
              </p>
              <p className="text-xs text-text-secondary">
                Voice features won't work without microphone permission. You can still use Arena with text input only.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
