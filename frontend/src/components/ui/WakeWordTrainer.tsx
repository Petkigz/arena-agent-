import { logger } from '../../services/logger';
import { useState, useRef, useEffect } from 'react';
import { useWakeWordStore } from '../../stores/wakeWordStore';
import { Button } from './Button';
import { Mic, StopCircle, Trash2, Play, Zap } from 'lucide-react';
import { notifications } from '../../services/notifications';

interface WakeWordTrainerProps {
  onModelTrained?: () => void;
}

export function WakeWordTrainer({ onModelTrained }: WakeWordTrainerProps) {
  const {
    samples,
    isRecording,
    isTraining,
    addSample,
    removeSample,
    clearSamples,
    setRecording,
    trainModel,
  } = useWakeWordStore();

  const [wakeWord, setWakeWord] = useState('');
  const [sensitivity, setSensitivity] = useState(0.5);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [playingSample, setPlayingSample] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement>(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus',
      });

      const chunks: Blob[] = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunks.push(e.data);
        }
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(chunks, { type: 'audio/webm' });
        
        // Convert to base64
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64 = reader.result as string;
          const audioData = base64.split(',')[1];

          const sample = {
            id: `sample-${Date.now()}`,
            audio: audioData,
            timestamp: new Date().toISOString(),
            duration: 2.0, // Approximate duration
            sampleRate: 16000,
            channels: 1,
          };

          addSample(sample);
        };

        reader.readAsDataURL(audioBlob);

        // Stop all tracks
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start();
      setMediaRecorder(recorder);
      setRecording(true);

      // Auto-stop after 3 seconds
      setTimeout(() => {
        if (recorder.state === 'recording') {
          recorder.stop();
          setRecording(false);
        }
      }, 3000);
    } catch (error) {
      logger.error('Failed to start recording:', error);
      notifications.error('Failed to access microphone');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
      setRecording(false);
    }
  };

  const playSample = (sampleId: string, audioData: string) => {
    if (playingSample === sampleId) {
      // Stop playback
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
      }
      setPlayingSample(null);
      return;
    }

    const audio = new Audio(`data:audio/webm;base64,${audioData}`);
    audioRef.current = audio;

    audio.onended = () => {
      setPlayingSample(null);
    };

    audio.play();
    setPlayingSample(sampleId);
  };

  const handleTrain = async () => {
    if (!wakeWord.trim()) {
      notifications.warning('Please enter a wake word');
      return;
    }

    const success = await trainModel(wakeWord, sensitivity);
    if (success && onModelTrained) {
      onModelTrained();
    }
  };

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
      }
    };
  }, []);

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-accent-warning/50 bg-accent-warning/10 p-3 text-sm text-text-secondary">
        Custom wake-word training is not currently available because no verified ONNX training pipeline is configured. You may record samples, but Arena will not create a fake model or accuracy score.
      </div>
      {/* Wake word input */}
      <div>
        <label className="block text-sm font-medium text-text-primary mb-2">
          Wake Word
        </label>
        <input
          type="text"
          value={wakeWord}
          onChange={(e) => setWakeWord(e.target.value)}
          placeholder="e.g., Hey Arena, Computer, Jarvis"
          className="w-full px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
        />
        <p className="text-xs text-text-muted mt-1">
          Choose a phrase that's easy to say and unlikely to occur in normal conversation
        </p>
      </div>

      {/* Recording section */}
      <div className="p-4 bg-background-surface rounded-lg">
        <h3 className="font-medium text-text-primary mb-3">Record Samples</h3>
        <p className="text-sm text-text-secondary mb-4">
          Record yourself saying your wake word at least 5 times. Speak clearly and naturally.
        </p>

        <div className="flex items-center gap-3 mb-4">
          {!isRecording ? (
            <Button onClick={startRecording} variant="primary">
              <Mic className="w-4 h-4 mr-2" />
              Start Recording
            </Button>
          ) : (
            <Button onClick={stopRecording} variant="danger">
              <StopCircle className="w-4 h-4 mr-2" />
              Stop Recording
            </Button>
          )}

          {isRecording && (
            <div className="flex items-center gap-2 text-sm text-accent-error">
              <div className="w-2 h-2 bg-accent-error rounded-full animate-pulse" />
              <span>Recording... (3 seconds)</span>
            </div>
          )}
        </div>

        {/* Samples list */}
        {samples.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium text-text-primary">
                Samples ({samples.length})
              </h4>
              <Button onClick={clearSamples} variant="secondary" size="sm">
                <Trash2 className="w-4 h-4 mr-2" />
                Clear All
              </Button>
            </div>

            <div className="space-y-2 max-h-64 overflow-y-auto">
              {samples.map((sample, index) => (
                <div
                  key={sample.id}
                  className="flex items-center gap-3 p-3 bg-background-primary rounded-lg"
                >
                  <span className="text-sm font-medium text-text-primary w-8">
                    #{index + 1}
                  </span>
                  <button
                    onClick={() => playSample(sample.id, sample.audio)}
                    className="p-2 hover:bg-background-surface rounded-lg transition-colors"
                  >
                    <Play
                      className={`w-4 h-4 ${
                        playingSample === sample.id ? 'text-accent-primary' : 'text-text-muted'
                      }`}
                    />
                  </button>
                  <div className="flex-1">
                    <p className="text-sm text-text-secondary">
                      {new Date(sample.timestamp).toLocaleTimeString()}
                    </p>
                  </div>
                  <button
                    onClick={() => removeSample(sample.id)}
                    className="p-2 hover:bg-background-surface rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4 text-text-muted" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Sensitivity slider */}
      <div>
        <label className="block text-sm font-medium text-text-primary mb-2">
          Sensitivity: {Math.round(sensitivity * 100)}%
        </label>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={sensitivity}
          onChange={(e) => setSensitivity(parseFloat(e.target.value))}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-text-muted mt-1">
          <span>Less sensitive (fewer false positives)</span>
          <span>More sensitive (easier to trigger)</span>
        </div>
      </div>

      {/* Train button */}
      <Button
        onClick={handleTrain}
        disabled={samples.length < 5 || !wakeWord.trim() || isTraining}
        variant="primary"
        className="w-full"
      >
        <Zap className="w-4 h-4 mr-2" />
        {isTraining ? 'Training...' : `Train Model (${samples.length}/5 samples)`}
      </Button>

      {samples.length < 5 && (
        <p className="text-sm text-text-muted text-center">
          Record at least {5 - samples.length} more sample{5 - samples.length !== 1 ? 's' : ''} to train your model
        </p>
      )}
    </div>
  );
}
