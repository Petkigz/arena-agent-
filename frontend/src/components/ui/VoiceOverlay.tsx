import { useVoice } from '../../hooks/useVoice';
import { X } from 'lucide-react';
import { PresenceOrb } from '../presence/PresenceOrb';

interface VoiceOverlayProps {
  conversationId: string;
  onClose: () => void;
  onTranscript?: (text: string, isFinal: boolean) => void;
}

export function VoiceOverlay({ conversationId, onClose, onTranscript }: VoiceOverlayProps) {
  const { voiceState, isListening, startListening, stopListening, transcript, error, audioLevel } = useVoice({ conversationId, onTranscript });

  const status = voiceState === 'listening' || voiceState === 'recording'
    ? 'listening'
    : voiceState === 'speaking'
      ? 'speaking'
      : voiceState === 'thinking' || voiceState === 'processing'
        ? 'working'
        : 'idle';

  const label = voiceState === 'speaking'
    ? 'Beanie is speaking...'
    : voiceState === 'thinking' || voiceState === 'processing'
      ? 'Beanie is thinking...'
      : voiceState === 'recording'
        ? 'Listening to you...'
        : voiceState === 'listening'
          ? 'Listening...'
          : 'Ready';

  return (
    <div className="fixed inset-0 bg-background-primary/80 backdrop-blur-xl flex items-center justify-center z-50">
      <div className="relative w-full max-w-lg mx-4 rounded-3xl border border-background-surface bg-background-secondary/90 shadow-2xl p-8 text-center">
        <button onClick={onClose} className="absolute top-4 right-4 p-2 rounded-full text-text-muted hover:text-text-primary hover:bg-background-surface" aria-label="Close voice interaction">
          <X className="w-5 h-5" />
        </button>

        <p className="text-xs uppercase tracking-[0.2em] text-text-muted mb-2">Beanie</p>
        <h2 className="text-2xl font-semibold text-text-primary mb-1">{label}</h2>
        <p className="text-sm text-text-muted">Your conversation stays in the same ChatGPT-style workspace.</p>

        <div className="flex justify-center my-5">
          <PresenceOrb status={status} size="lg" activity={audioLevel} />
        </div>

        {transcript && <div className="mb-5 px-5 py-3 rounded-2xl bg-background-primary border border-background-surface text-left"><p className="text-text-primary leading-relaxed">{transcript}</p></div>}
        {error && <div className="mb-5 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-sm">{error}</div>}

        <button onClick={isListening ? stopListening : startListening} className="w-full px-5 py-3 rounded-2xl bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors">
          {isListening ? 'Stop listening' : 'Start listening'}
        </button>
      </div>
    </div>
  );
}
