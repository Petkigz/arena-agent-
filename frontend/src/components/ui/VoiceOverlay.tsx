import { useVoice } from '../../hooks/useVoice';
import { Mic, MicOff, X } from 'lucide-react';

interface VoiceOverlayProps {
  conversationId: string;
  onClose: () => void;
  onTranscript?: (text: string, isFinal: boolean) => void;
}

export function VoiceOverlay({ conversationId, onClose, onTranscript }: VoiceOverlayProps) {
  const {
    voiceState,
    isListening,
    startListening,
    stopListening,
    transcript,
    error,
  } = useVoice({ conversationId, onTranscript });

  const getStateLabel = () => {
    switch (voiceState) {
      case 'idle':
        return 'Ready';
      case 'listening':
        return 'Listening for wake word...';
      case 'recording':
        return 'Recording...';
      case 'processing':
        return 'Processing speech...';
      case 'thinking':
        return 'Thinking...';
      case 'speaking':
        return 'Speaking...';
      case 'stopped':
        return 'Stopped';
      default:
        return 'Unknown';
    }
  };

  const getStateColor = () => {
    switch (voiceState) {
      case 'recording':
        return 'bg-red-500';
      case 'listening':
        return 'bg-yellow-500';
      case 'processing':
      case 'thinking':
        return 'bg-blue-500';
      case 'speaking':
        return 'bg-green-500';
      default:
        return 'bg-background-surface';
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-background-secondary rounded-lg shadow-xl max-w-md w-full mx-4">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-text-primary">
              Voice Input
            </h2>
            <button
              onClick={onClose}
              className="p-2 hover:bg-background-surface rounded-full transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* State indicator */}
          <div className="mb-6">
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full ${getStateColor()} animate-pulse`} />
              <span className="text-text-secondary">{getStateLabel()}</span>
            </div>
          </div>

          {/* Transcript */}
          {transcript && (
            <div className="mb-6 p-4 bg-background-primary rounded-lg">
              <p className="text-text-primary">{transcript}</p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
              <p className="text-red-700 dark:text-red-400">{error}</p>
            </div>
          )}

          {/* Controls */}
          <div className="flex gap-3">
            {!isListening ? (
              <button
                onClick={startListening}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
              >
                <Mic className="w-5 h-5" />
                Start Listening
              </button>
            ) : (
              <button
                onClick={stopListening}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
              >
                <MicOff className="w-5 h-5" />
                Stop Listening
              </button>
            )}
          </div>

          {/* Instructions */}
          <div className="mt-6 text-sm text-text-muted">
            <p className="mb-2">
              <strong>Instructions:</strong>
            </p>
            <ul className="list-disc list-inside space-y-1">
              <li>Say "Hey Jarvis" to activate</li>
              <li>Speak your command after the wake word</li>
              <li>Wait for Arena to process and respond</li>
              <li>You can interrupt by saying "Hey Jarvis" again</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
