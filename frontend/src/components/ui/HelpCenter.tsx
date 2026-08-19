import { useState } from 'react';
import { Modal } from './Modal';
import { InteractiveTutorial, FAQ } from './InteractiveTutorial';
import { mainTutorialSteps, faqItems, keyboardShortcuts, tips } from '../../utils/helpContent';
import { HelpCircle, Book, Keyboard, Lightbulb, MessageCircle } from 'lucide-react';
import { Button } from './Button';
import { notifications } from '../services/notifications';

interface HelpCenterProps {
  isOpen: boolean;
  onClose: () => void;
}

export function HelpCenter({ isOpen, onClose }: HelpCenterProps) {
  const [showTutorial, setShowTutorial] = useState(false);
  const [showFAQ, setShowFAQ] = useState(false);
  const [activeTab, setActiveTab] = useState<'shortcuts' | 'tips' | 'contact'>('shortcuts');

  const handleStartTutorial = () => {
    onClose();
    setTimeout(() => setShowTutorial(true), 300);
  };

  const handleShowFAQ = () => {
    onClose();
    setTimeout(() => setShowFAQ(true), 300);
  };

  return (
    <>
      <Modal isOpen={isOpen} onClose={onClose} title="Help Center">
        <div className="space-y-4">
          {/* Quick actions */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={handleStartTutorial}
              className="p-4 bg-background-surface hover:bg-background-surface/80 rounded-lg transition-colors text-left"
            >
              <Book className="w-6 h-6 text-accent-primary mb-2" />
              <h3 className="font-semibold text-text-primary mb-1">Interactive Tutorial</h3>
              <p className="text-xs text-text-secondary">Learn the basics with a guided tour</p>
            </button>

            <button
              onClick={handleShowFAQ}
              className="p-4 bg-background-surface hover:bg-background-surface/80 rounded-lg transition-colors text-left"
            >
              <HelpCircle className="w-6 h-6 text-accent-primary mb-2" />
              <h3 className="font-semibold text-text-primary mb-1">FAQ</h3>
              <p className="text-xs text-text-secondary">Find answers to common questions</p>
            </button>
          </div>

          {/* Tabs */}
          <div className="border-t border-border pt-4">
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setActiveTab('shortcuts')}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === 'shortcuts'
                    ? 'bg-accent-primary text-white'
                    : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
                }`}
              >
                <Keyboard className="w-4 h-4 inline mr-1" />
                Shortcuts
              </button>
              <button
                onClick={() => setActiveTab('tips')}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === 'tips'
                    ? 'bg-accent-primary text-white'
                    : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
                }`}
              >
                <Lightbulb className="w-4 h-4 inline mr-1" />
                Tips
              </button>
              <button
                onClick={() => setActiveTab('contact')}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === 'contact'
                    ? 'bg-accent-primary text-white'
                    : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
                }`}
              >
                <MessageCircle className="w-4 h-4 inline mr-1" />
                Contact
              </button>
            </div>

            {/* Tab content */}
            {activeTab === 'shortcuts' && (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {keyboardShortcuts.map((shortcut, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between py-2 border-b border-border last:border-0"
                  >
                    <span className="text-sm text-text-primary">{shortcut.description}</span>
                    <div className="flex items-center gap-1">
                      {shortcut.keys.map((key, keyIndex) => (
                        <span key={keyIndex}>
                          <kbd className="px-2 py-0.5 bg-background-surface border border-border rounded text-xs font-mono text-text-secondary">
                            {key}
                          </kbd>
                          {keyIndex < shortcut.keys.length - 1 && (
                            <span className="text-text-muted mx-0.5">+</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'tips' && (
              <div className="space-y-3 max-h-64 overflow-y-auto">
                {tips.map((tip, index) => (
                  <div key={index} className="flex items-start gap-2">
                    <Lightbulb className="w-4 h-4 text-accent-primary flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-text-secondary">{tip}</p>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'contact' && (
              <div className="space-y-4">
                <div>
                  <h3 className="font-semibold text-text-primary mb-2">Report an Issue</h3>
                  <p className="text-sm text-text-secondary mb-3">
                    Found a bug or something not working as expected?
                  </p>
                  <Button
                    onClick={() => {
                      // In production, this would open an issue reporting form
                      notifications.info('Issue reporting will be available in a future update.');
                    }}
                    variant="secondary"
                    size="sm"
                  >
                    Report Issue
                  </Button>
                </div>

                <div className="border-t border-border pt-4">
                  <h3 className="font-semibold text-text-primary mb-2">Request a Feature</h3>
                  <p className="text-sm text-text-secondary mb-3">
                    Have an idea for a new feature?
                  </p>
                  <Button
                    onClick={() => {
                      // In production, this would open a feature request form
                      notifications.info('Feature requests will be available in a future update.');
                    }}
                    variant="secondary"
                    size="sm"
                  >
                    Request Feature
                  </Button>
                </div>

                <div className="border-t border-border pt-4">
                  <h3 className="font-semibold text-text-primary mb-2">Documentation</h3>
                  <p className="text-sm text-text-secondary mb-3">
                    Read the full documentation for detailed information.
                  </p>
                  <Button
                    onClick={() => {
                      // In production, this would open documentation
                      window.open('https://arena-docs.example.com', '_blank');
                    }}
                    variant="secondary"
                    size="sm"
                  >
                    Open Documentation
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* Interactive tutorial */}
      <InteractiveTutorial
        steps={mainTutorialSteps}
        isOpen={showTutorial}
        onClose={() => setShowTutorial(false)}
        onComplete={() => {
          setShowTutorial(false);
          localStorage.setItem('arena-tutorial-completed', 'true');
        }}
      />

      {/* FAQ */}
      <FAQ items={faqItems} isOpen={showFAQ} onClose={() => setShowFAQ(false)} />
    </>
  );
}
