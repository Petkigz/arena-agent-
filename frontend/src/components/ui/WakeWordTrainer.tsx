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

/**
 * Convert a recorded audio blob (webm/opus from MediaRecorder) into 16 kHz
 * mono 16-bit PCM WAV base64 — the backend trainer decodes WAV, not webm
 * (owner live test 2026-09-08: "voice model failed to train" because the
 * server received an undecodable container).
 */
async function blobToWavBase64(blob: Blob): Promise<{ base64: string; duration: number }> {
  const arrayBuffer = await blob.arrayBuffer();
  const decodeCtx = new AudioContext();
  const decoded = await decodeCtx.decodeAudioData(arrayBuffer);
  await decodeCtx.close();

  const targetRate = 16000;
  const frames = Math.max(1, Math.ceil(decoded.duration * targetRate));
  const offline = new OfflineAudioContext(1, frames, targetRate);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  const samples = rendered.getChannelData(0);

  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, targetRate, true);
  view.setUint32(28, targetRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }

  let binary = '';
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return { base64: window.btoa(binary), duration: decoded.duration };
}

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

        try {
          // Decode + resample to real 16 kHz mono WAV so the backend can
          // actually train on it (webm/opus is not decodable server-side).
          const { base64, duration } = await blobToWavBase64(audioBlob);
          addSample({
            id: `sample-${Date.now()}`,
            audio: base64,
            timestamp: new Date().toISOString(),
            duration: Number(duration.toFixed(2)),
            sampleRate: 16000,
            channels: 1,
          });
        } catch (err) {
          console.error('Could not convert recording to WAV:', err);
        }

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
