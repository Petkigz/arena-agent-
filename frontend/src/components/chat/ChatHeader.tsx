import { Share2 } from 'lucide-react';
import { ReactiveBeanieOrb } from '../presence/ReactiveBeanieOrb';
import type { BeanieOrbStatus } from '../../design/tokens';

export type ChatConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

interface ChatHeaderProps {
  conversationTitle: string;
  connectionStatus: ChatConnectionStatus;
  presenceStatus?: string;
  onShare: () => void;
}

const CONNECTION_LABELS: Record<ChatConnectionStatus, string> = {
  connected: 'Online',
  connecting: 'Connecting',
  reconnecting: 'Reconnecting',
  disconnected: 'Offline',
};

const CONNECTION_COLORS: Record<ChatConnectionStatus, string> = {
  connected: 'bg-accent-success',
  connecting: 'bg-accent-warning',
  reconnecting: 'bg-accent-warning',
  disconnected: 'bg-accent-error',
};

function toOrbStatus(status: string | undefined, connected: boolean): BeanieOrbStatus {
  if (!connected) return 'offline';
  if (status === 'processing') return 'thinking';
  if (status === 'recording') return 'listening';
  if (status === 'stopped') return 'idle';
  return (status as BeanieOrbStatus) || 'idle';
}

/** Beanie-first identity header shared by desktop and web chat surfaces. */
export function ChatHeader({ conversationTitle, connectionStatus, presenceStatus, onShare }: ChatHeaderProps) {
  const isConnected = connectionStatus === 'connected';
  const label = CONNECTION_LABELS[connectionStatus];

  return (
    <header className="flex-shrink-0 px-5 py-3 border-b border-border-subtle bg-background-panel/80 backdrop-blur-xl">
      <div className="max-w-5xl mx-auto flex items-center gap-3">
        <ReactiveBeanieOrb
          status={toOrbStatus(presenceStatus, isConnected)}
          size="sm"
          className="flex-shrink-0"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <h1 className="text-base font-semibold text-text-primary">Beanie</h1>
            <span className="text-xs text-text-muted">Personal AI Assistant</span>
          </div>
          <div className="flex items-center gap-2 min-w-0">
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${CONNECTION_COLORS[connectionStatus]}`} aria-hidden="true" />
            <span className="text-xs text-text-muted">{label}</span>
            <span className="text-text-muted/50" aria-hidden="true">·</span>
            <span className="text-xs text-text-secondary truncate" title={conversationTitle}>{conversationTitle}</span>
          </div>
        </div>
        <button
          onClick={onShare}
          className="p-2 text-text-muted hover:text-text-primary hover:bg-background-surface rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-accent-primary"
          title="Share conversation"
          aria-label="Share conversation"
        >
          <Share2 className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
