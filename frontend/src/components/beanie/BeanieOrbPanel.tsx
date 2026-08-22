import { ReactiveBeanieOrb, type BeanieOrbStatus } from '../presence/ReactiveBeanieOrb';
import { Button } from '../ui/Button';
import { useVoice } from '../../hooks/useVoice';
import { usePresenceStore } from '../../stores/presenceStore';
import { webSocketService } from '../../services/websocket';
import { Mic, MicOff } from 'lucide-react';

// Map the voice state machine onto the orb's presence states.
const VOICE_TO_ORB: Record<string, BeanieOrbStatus> = {
  idle: 'idle',
  stopped: 'idle',
  listening: 'listening',
  recording: 'listening',
  processing: 'thinking',
  thinking: 'thinking',
  speaking: 'speaking',
};

const STATE_LABELS: Record<string, string> = {
  idle: "I'm here. Talk to me.",
  stopped: "I'm here. Talk to me.",
  listening: 'Listening for wake word…',
  recording: 'Listening…',
  processing: 'Thinking…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
};

const QUICK_ACTIONS: { label: string; action: string }[] = [
  { label: 'Continue project', action: 'continue_project' },
  { label: "What's new?", action: 'whats_new' },
  { label: 'Research', action: 'research' },
  { label: 'Talk to me', action: 'talk' },
];

interface BeanieOrbPanelProps {
  conversationId: string;
  onTranscript?: (text: string, isFinal: boolean) => void;
}

/**
 * BeanieOrbPanel — the centered floating orb that replaces the chat content when
 * the user presses the Beanie button. Fully interactive, mirroring the Android
 * Beanie home: a clickable reactive orb, quick actions, and talk-to-Beanie.
 */
export function BeanieOrbPanel({ conversationId, onTranscript }: BeanieOrbPanelProps) {
  const { presence } = usePresenceStore();
  const {
    voiceState,
    isListening,
    startListening,
    stopListening,
    transcript,
    error,
    inputLevel,
    outputLevel,
  } = useVoice({ conversationId, onTranscript });

  const orbStatus: BeanieOrbStatus = VOICE_TO_ORB[voiceState] ?? 'idle';
  const stateLabel = STATE_LABELS[voiceState] ?? presence.message;
  // Speaking → react to TTS audio; otherwise react to the microphone.
  const level = orbStatus === 'speaking' ? outputLevel : inputLevel;

  const handleQuickAction = (action: string) => {
    if (action === 'talk') {
      if (isListening) stopListening();
      else startListening();
      return;
    }
    const prompt =
      action === 'continue_project'
        ? 'What were we working on? Continue the project.'
        : action === 'whats_new'
          ? "What's new in my system?"
          : action === 'research'
            ? 'Research the latest on my current project.'
            : null;
    if (prompt) {
      webSocketService.sendMessage(conversationId, prompt);
    }
  };

  return (
    <div className="h-full flex flex-col items-center justify-center p-6" role="region" aria-label="Beanie">
      {/* Clickable presence orb — tap to talk, voice field reacts to audio */}
      <button
        onClick={isListening ? stopListening : startListening}
        className="rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
        aria-label={isListening ? 'Stop talking' : 'Talk to Beanie'}
      >
        <ReactiveBeanieOrb status={orbStatus} level={level} size="lg" className="mb-2" />
      </button>

      {/* Identity */}
      <h2 className="text-2xl font-bold text-text-primary mb-1">BEANIE</h2>
      <p className="text-text-secondary mb-1">Personal AI</p>
      <p className="text-text-muted italic mb-6">{stateLabel}</p>

      {/* Live transcript while talking */}
      {transcript && (
        <p className="max-w-md text-center text-text-primary bg-background-secondary rounded-lg px-4 py-2 mb-4">
          “{transcript}”
        </p>
      )}

      {error && (
        <p className="max-w-md text-center text-accent-error text-sm mb-4">{error}</p>
      )}

      {/* Quick actions */}
      <div className="w-full max-w-sm grid grid-cols-2 gap-3 mb-6">
        {QUICK_ACTIONS.map((qa) => (
          <Button
            key={qa.action}
            variant="secondary"
            className="h-16"
            onClick={() => handleQuickAction(qa.action)}
          >
            {qa.label}
          </Button>
        ))}
      </div>

      {/* Talk to Beanie */}
      <Button
        size="lg"
        variant={isListening ? 'danger' : 'primary'}
        onClick={isListening ? stopListening : startListening}
        className="w-full max-w-sm"
        aria-label={isListening ? 'Stop talking' : 'Talk to Beanie'}
      >
        {isListening ? (
          <MicOff className="w-5 h-5 mr-2" aria-hidden="true" />
        ) : (
          <Mic className="w-5 h-5 mr-2" aria-hidden="true" />
        )}
        {isListening ? 'Stop' : '🎙 Talk to Beanie'}
      </Button>
    </div>
  );
}
