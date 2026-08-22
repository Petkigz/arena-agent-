import { ReactiveBeanieOrb, type BeanieOrbStatus } from '../presence/ReactiveBeanieOrb';
import { Button } from '../ui/Button';
import { useVoice } from '../../hooks/useVoice';
import { usePresenceStore } from '../../stores/presenceStore';
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

interface BeanieOrbPanelProps {
  conversationId: string;
  onTranscript?: (text: string, isFinal: boolean) => void;
}

/**
 * BeanieOrbPanel — the centered floating orb that replaces the chat content when
 * the user presses the Beanie button. Talking is real: it uses `useVoice` (mic
 * capture → PCM stream → backend STT → cognitive runtime → spoken reply). The
 * orb's voice-field rings react to the live mic (listening) and TTS (speaking)
 * amplitude.
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

  return (
    <div className="h-full flex flex-col items-center justify-center p-6" role="region" aria-label="Beanie">
      {/* Floating presence orb — voice field reacts to mic/TTS amplitude */}
      <ReactiveBeanieOrb status={orbStatus} level={level} size="lg" className="mb-8" />

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
