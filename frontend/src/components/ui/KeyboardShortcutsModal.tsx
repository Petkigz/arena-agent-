import { Modal } from './Modal';
import { Keyboard } from 'lucide-react';
import type { KeyboardShortcut } from '../../hooks/useKeyboardShortcuts';

interface KeyboardShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
  shortcuts: KeyboardShortcut[];
}

export function KeyboardShortcutsModal({ isOpen, onClose, shortcuts }: KeyboardShortcutsModalProps) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Keyboard Shortcuts">
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-text-secondary">
          <Keyboard className="w-5 h-5" />
          <p className="text-sm">Use these shortcuts to navigate Arena faster</p>
        </div>

        <div className="space-y-2">
          {shortcuts.map((shortcut, index) => (
            <div
              key={index}
              className="flex items-center justify-between py-2 border-b border-border last:border-0"
            >
              <span className="text-text-primary">{shortcut.description}</span>
              <div className="flex items-center gap-1">
                {shortcut.keys.map((key, keyIndex) => (
                  <span key={keyIndex}>
                    <kbd className="px-2 py-1 bg-background-surface border border-border rounded text-xs font-mono text-text-secondary">
                      {key}
                    </kbd>
                    {keyIndex < shortcut.keys.length - 1 && (
                      <span className="text-text-muted mx-1">+</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="pt-4 border-t border-border">
          <p className="text-xs text-text-muted">
            Tip: Press <kbd className="px-1 py-0.5 bg-background-surface border border-border rounded text-xs font-mono">?</kbd> anywhere to show this dialog
          </p>
        </div>
      </div>
    </Modal>
  );
}
