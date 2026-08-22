import { usePresenceStore } from '../../stores/presenceStore';
import { ReactiveBeanieOrb, type BeanieOrbStatus } from './ReactiveBeanieOrb';
import { cn } from '../../utils/cn';
import type { Message } from '../../types';

interface BeanieAvatarProps {
  /** The assistant message's status — drives per-message orb states. */
  messageStatus?: Message['status'];
  className?: string;
}

/**
 * BeanieAvatar — the assistant's avatar in chat. It is the same living orb as
 * the expanded voice presence, but small and reading the global presence state
 * (falling back to per-message states when streaming or errored).
 *
 * It subscribes to the presence store itself so it re-renders on state changes
 * independently of any memoized parent (e.g. MessageBubble).
 */
export function BeanieAvatar({ messageStatus, className }: BeanieAvatarProps) {
  const { presence } = usePresenceStore();

  let status: BeanieOrbStatus = presence.status;
  if (messageStatus === 'streaming') status = 'thinking';
  else if (messageStatus === 'error') status = 'error';

  return (
    <div className={cn('flex-shrink-0', className)}>
      <ReactiveBeanieOrb status={status} size="sm" />
    </div>
  );
}
