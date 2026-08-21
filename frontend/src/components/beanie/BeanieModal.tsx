import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { PresenceOrb } from '../presence/PresenceOrb';
import { usePresenceStore } from '../../stores/presenceStore';

/**
 * BeanieModal — a centered floating orb panel, opened from the chat composer's
 * "Beanie" button (like the voice button in other AI assistants). Purely the
 * orb + identity + a "Talk to Beanie" affordance; it does not change any layout.
 */
export interface BeanieModalProps {
  isOpen: boolean;
  onClose: () => void;
  onTalk?: () => void;
}

export function BeanieModal({ isOpen, onClose, onTalk }: BeanieModalProps) {
  const { presence } = usePresenceStore();

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="sm">
      <div className="flex flex-col items-center py-4">
        {/* Floating presence orb */}
        <PresenceOrb status={presence.status} size="lg" className="mb-6" />

        {/* Identity */}
        <h2 className="text-2xl font-bold text-text-primary mb-1">BEANIE</h2>
        <p className="text-text-secondary mb-1">Personal AI</p>
        <p className="text-text-muted italic mb-6">{presence.message}</p>

        {/* Talk to Beanie */}
        <Button size="lg" className="w-full" onClick={onTalk}>
          🎙 Talk to Beanie
        </Button>
      </div>
    </Modal>
  );
}
