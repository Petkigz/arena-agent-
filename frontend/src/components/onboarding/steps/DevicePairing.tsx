import { useState } from 'react';
import { Button } from '../../ui/Button';
import { Smartphone, ArrowRight, ArrowLeft, SkipForward, QrCode, Wifi } from 'lucide-react';
import { useOnboardingStore } from '../../../stores/onboardingStore';

interface DevicePairingProps {
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}

export function DevicePairing({ onNext, onBack, onSkip }: DevicePairingProps) {
  const { pairedDevices } = useOnboardingStore();
  const [pairingMethod, setPairingMethod] = useState<'qr' | 'manual' | null>(null);
  const [pairingCode, setPairingCode] = useState('');
  const [isPairing, setIsPairing] = useState(false);
  const [pairingError, setPairingError] = useState('');

  const handlePairDevice = async () => {
    if (!pairingCode.trim()) return;
    setIsPairing(true);
    setPairingError(
      'Device pairing verification is not implemented. No device was added or marked connected.'
    );
    setIsPairing(false);
  };

  const generateQRCode = () => {
    setPairingError(
      'Verified QR pairing is not implemented. Arena will not display a placeholder pairing code.'
    );
  };

  return (
    <div className="max-w-2xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-accent-primary/10 rounded-full mb-6">
          <Smartphone className="w-10 h-10 text-accent-primary" />
        </div>
        <h2 className="text-3xl font-bold text-text-primary mb-3">
          Pair Your Devices
        </h2>
        <p className="text-text-secondary">
          Connect your phone to Arena for voice interaction on the go
        </p>
      </div>

      {/* Paired devices */}
      {pairedDevices.length > 0 && (
        <div className="mb-8">
          <h3 className="font-semibold text-text-primary mb-3">Paired Devices</h3>
          <div className="space-y-2">
            {pairedDevices.map((device, index) => (
              <div
                key={device}
                className="flex items-center gap-3 p-4 bg-background-secondary rounded-lg"
              >
                <Smartphone className="w-5 h-5 text-accent-success" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-text-primary">
                    Device {index + 1}
                  </p>
                  <p className="text-xs text-text-muted">{device}</p>
                </div>
                <div className="flex items-center gap-2 text-xs text-accent-success">
                  <Wifi className="w-3 h-3" />
                  <span>Saved (connection not verified)</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pairing methods */}
      {!pairingMethod && (
        <div className="space-y-4 mb-8">
          <h3 className="font-semibold text-text-primary mb-3">Add a Device</h3>

          {/* QR Code method */}
          <button
            onClick={generateQRCode}
            className="w-full p-6 bg-background-secondary hover:bg-background-secondary/80 rounded-lg transition-colors text-left"
          >
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-accent-primary/10 rounded-full flex items-center justify-center">
                <QrCode className="w-6 h-6 text-accent-primary" />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-text-primary mb-1">Scan QR Code</h4>
                <p className="text-sm text-text-secondary">
                  Open the Arena mobile app and scan the QR code to pair instantly
                </p>
              </div>
              <ArrowRight className="w-5 h-5 text-text-muted" />
            </div>
          </button>

          {/* Manual method */}
          <button
            onClick={() => setPairingMethod('manual')}
            className="w-full p-6 bg-background-secondary hover:bg-background-secondary/80 rounded-lg transition-colors text-left"
          >
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-accent-primary/10 rounded-full flex items-center justify-center">
                <span className="text-accent-primary font-bold text-lg">123</span>
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-text-primary mb-1">Enter Pairing Code</h4>
                <p className="text-sm text-text-secondary">
                  Manually enter the 6-digit code shown in the mobile app
                </p>
              </div>
              <ArrowRight className="w-5 h-5 text-text-muted" />
            </div>
          </button>
        </div>
      )}

      {pairingError && (
        <div className="mb-6 rounded-lg border border-accent-warning/50 bg-accent-warning/10 p-4 text-sm text-text-secondary">
          {pairingError}
        </div>
      )}

      {/* Manual pairing */}
      {pairingMethod === 'manual' && (
        <div className="bg-background-secondary rounded-lg p-6 mb-8">
          <h3 className="font-semibold text-text-primary mb-4">Enter Pairing Code</h3>
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              value={pairingCode}
              onChange={(e) => setPairingCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="123456"
              className="flex-1 px-4 py-3 bg-background-primary border border-border rounded-lg text-center text-2xl font-mono tracking-widest"
              maxLength={6}
            />
          </div>
          <div className="flex gap-3">
            <Button
              onClick={handlePairDevice}
              disabled={pairingCode.length !== 6 || isPairing}
              className="flex-1"
            >
              {isPairing ? 'Pairing...' : 'Pair Device'}
            </Button>
            <Button
              onClick={() => {
                setPairingMethod(null);
                setPairingCode('');
              }}
              variant="secondary"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Info box */}
      <div className="bg-background-secondary/50 rounded-lg p-6 mb-8">
        <h3 className="font-semibold text-text-primary mb-3">About Device Pairing:</h3>
        <ul className="space-y-2 text-sm text-text-secondary">
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span>Use Arena on your phone with voice interaction</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span>Sync conversations and knowledge across devices</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span>Both devices must be on the same network</span>
          </li>
        </ul>
        <p className="text-xs text-text-muted mt-4">
          You can pair more devices later in Settings → Devices
        </p>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-3">
        <Button onClick={onNext} size="lg" className="w-full">
          Continue
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
            <span className="text-sm">Skip pairing</span>
          </button>
        </div>
      </div>
    </div>
  );
}
