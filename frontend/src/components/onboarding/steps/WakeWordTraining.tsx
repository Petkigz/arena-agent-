import { useState } from 'react';
import { Button } from '../../ui/Button';
import { Mic, ArrowRight, ArrowLeft, SkipForward, Check } from 'lucide-react';
import { useOnboardingStore } from '../../../stores/onboardingStore';

interface WakeWordTrainingProps {
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}

export function WakeWordTraining({ onNext, onBack, onSkip }: WakeWordTrainingProps) {
  const { addWakeWordSample, wakeWordSamples } = useOnboardingStore();
  const [isRecording, setIsRecording] = useState(false);
  const [currentSample, setCurrentSample] = useState(0);
  const [wakeWord] = useState('Hey Arena');
  const requiredSamples = 5;

  const handleRecord = async () => {
    if (isRecording) {
      // Stop recording
      setIsRecording(false);
      
      // Simulate recording completion
      setTimeout(() => {
        addWakeWordSample(`sample_${currentSample + 1}`);
        setCurrentSample(prev => prev + 1);
      }, 500);
    } else {
      // Start recording
      setIsRecording(true);
      
      // In production, this would use the Web Audio API to record
      // For now, simulate a 2-second recording
      setTimeout(() => {
        setIsRecording(false);
        addWakeWordSample(`sample_${currentSample + 1}`);
        setCurrentSample(prev => prev + 1);
      }, 2000);
    }
  };

  const progress = (wakeWordSamples.length / requiredSamples) * 100;
  const isComplete = wakeWordSamples.length >= requiredSamples;

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
          Record yourself saying "<span className="font-semibold text-text-primary">{wakeWord}</span>" {requiredSamples} times
        </p>
      </div>

      {/* Progress */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-text-secondary">
            {wakeWordSamples.length} of {requiredSamples} samples
          </span>
          <span className="text-sm text-text-secondary">{Math.round(progress)}%</span>
        </div>
        <div className="h-2 bg-background-surface rounded-full overflow-hidden">
          <div
            className="h-full bg-accent-primary transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Recording interface */}
      <div className="bg-background-secondary rounded-lg p-8 mb-8">
        <div className="text-center">
          {/* Microphone button */}
          <button
            onClick={handleRecord}
            disabled={isComplete}
            className={`
              inline-flex items-center justify-center w-24 h-24 rounded-full mb-4 transition-all
              ${isRecording 
                ? 'bg-accent-error animate-pulse' 
                : isComplete
                  ? 'bg-accent-success cursor-not-allowed'
                  : 'bg-accent-primary hover:bg-accent-primary/90'
              }
            `}
          >
            {isComplete ? (
              <Check className="w-12 h-12 text-white" />
            ) : (
              <Mic className="w-12 h-12 text-white" />
            )}
          </button>

          {/* Status text */}
          <p className="text-text-primary font-medium mb-2">
            {isRecording
              ? 'Recording... Say the wake word'
              : isComplete
                ? 'Training complete!'
                : 'Tap to record'
            }
          </p>

          {!isRecording && !isComplete && (
            <p className="text-sm text-text-muted">
              Speak clearly and naturally
            </p>
          )}
        </div>
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
          disabled={!isComplete}
          size="lg"
          className="w-full"
        >
          {isComplete ? 'Continue' : `Complete ${requiredSamples - wakeWordSamples.length} more samples`}
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
