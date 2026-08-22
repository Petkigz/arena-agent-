import type { VoiceState } from '../../services/websocket';

const LABELS: Partial<Record<VoiceState, string>> = {
  listening: 'Listening…',
  recording: 'Listening…',
  processing: 'Thinking…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
};

const COLORS: Partial<Record<VoiceState, string>> = {
  listening: '#10B981',
  recording: '#10B981',
  processing: '#F59E0B',
  thinking: '#F59E0B',
  speaking: '#8B5CF6',
};

/**
 * A small floating pill that appears while Beanie is listening / thinking /
 * speaking, so the user always knows the voice state — even outside the orb.
 */
export function ListeningIndicator({ state }: { state: VoiceState }) {
  const label = LABELS[state];
  const color = COLORS[state];
  if (!label) return null;

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-24 z-10 flex justify-center" role="status" aria-live="polite">
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-background-secondary border border-background-surface shadow-lg">
        <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: color }} aria-hidden="true" />
        <span className="text-sm text-text-primary">{label}</span>
      </div>
    </div>
  );
}
