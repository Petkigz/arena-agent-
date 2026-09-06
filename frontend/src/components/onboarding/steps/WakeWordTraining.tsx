import { Button } from '../../ui/Button';
import { Mic, ArrowRight, ArrowLeft, SkipForward } from 'lucide-react';

interface WakeWordTrainingProps {
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}

export function WakeWordTraining({ onNext, onBack, onSkip }: WakeWordTrainingProps) {
  const wakeWord = 'Hey Arena';

  return (
    <div className="max-w-2xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-accent-primary/10 rounded-full mb-6">
          <Mic className="w-10 h-10 text-accent-primary" />
        </div>
        <h2 className="text-3xl font-bold text-text-primary mb-3">
          Train Your Wake Word
        </h2>
        <p className="text-text-secondary">
          Built-in phrase: "<span className="font-semibold text-text-primary">{wakeWord}</span>"
        </p>
      </div>

      {/* Training availability */}
      <div className="bg-accent-warning/10 border border-accent-warning/50 rounded-lg p-8 mb-8 text-center">
        <Mic className="w-12 h-12 text-accent-warning mx-auto mb-3" />
        <p className="text-text-primary font-medium mb-2">Custom training is currently unavailable</p>
        <p className="text-sm text-text-secondary">
          Arena does not have a verified custom wake-word ONNX training pipeline configured. No sample or accuracy will be simulated. You can continue with a built-in wake word.
        </p>
      </div>

      {/* Tips */}
      <div className="bg-background-secondary/50 rounded-lg p-6 mb-8">
        <h3 className="font-semibold text-text-primary mb-3">Tips for better accuracy:</h3>
        <ul className="space-y-2 text-sm text-text-secondary">
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span>Speak at a normal volume and pace</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span>Record in a quiet environment</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span>Vary your distance from the microphone</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span>Use different tones and expressions</span>
          </li>
        </ul>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-3">
        <Button
          onClick={onNext}
          size="lg"
          className="w-full"
        >
          Continue with built-in wake word
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
            <span className="text-sm">Skip training</span>
          </button>
        </div>
      </div>

      {/* Note about skipping */}
      <p className="text-xs text-text-muted text-center mt-6">
        You can train a custom wake word later in Settings → Voice
      </p>
    </div>
  );
}
