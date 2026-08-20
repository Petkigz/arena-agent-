import { Button } from '../../ui/Button';
import { CheckCircle, Sparkles, ArrowRight, MessageCircle } from 'lucide-react';

interface OnboardingCompleteProps {
  onFinish: () => void;
}

export function OnboardingComplete({ onFinish }: OnboardingCompleteProps) {
  return (
    <div className="max-w-2xl mx-auto px-6 py-12 text-center">
      {/* Success icon */}
      <div className="mb-8">
        <div className="inline-flex items-center justify-center w-24 h-24 bg-accent-success/10 rounded-full mb-6">
          <CheckCircle className="w-12 h-12 text-accent-success" />
        </div>
      </div>

      {/* Title */}
      <h1 className="text-4xl font-bold text-text-primary mb-4">
        You're All Set!
      </h1>

      {/* Description */}
      <p className="text-lg text-text-secondary mb-8 leading-relaxed">
        Arena is ready to help you work smarter. Here's what you can do next:
      </p>

      {/* Quick start guide */}
      <div className="grid gap-4 mb-12 text-left">
        <div className="flex items-start gap-3 p-4 bg-background-secondary rounded-lg">
          <div className="flex-shrink-0 w-8 h-8 bg-accent-primary/10 rounded-full flex items-center justify-center">
            <MessageCircle className="w-5 h-5 text-accent-primary" />
          </div>
          <div>
            <h3 className="font-semibold text-text-primary mb-1">Start a Conversation</h3>
            <p className="text-sm text-text-secondary">
              Say "Hey Arena" or click the chat icon to start talking
            </p>
          </div>
        </div>

        <div className="flex items-start gap-3 p-4 bg-background-secondary rounded-lg">
          <div className="flex-shrink-0 w-8 h-8 bg-accent-primary/10 rounded-full flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-accent-primary" />
          </div>
          <div>
            <h3 className="font-semibold text-text-primary mb-1">Explore Pansophy</h3>
            <p className="text-sm text-text-secondary">
              Build your knowledge graph and organize memories
            </p>
          </div>
        </div>

        <div className="flex items-start gap-3 p-4 bg-background-secondary rounded-lg">
          <div className="flex-shrink-0 w-8 h-8 bg-accent-primary/10 rounded-full flex items-center justify-center">
            <ArrowRight className="w-5 h-5 text-accent-primary" />
          </div>
          <div>
            <h3 className="font-semibold text-text-primary mb-1">Try the Tools</h3>
            <p className="text-sm text-text-secondary">
              Execute code, manage files, and analyze documents
            </p>
          </div>
        </div>
      </div>

      {/* Keyboard shortcuts reminder */}
      <div className="bg-background-secondary/50 rounded-lg p-6 mb-8">
        <h3 className="font-semibold text-text-primary mb-3">Quick Tips:</h3>
        <ul className="space-y-2 text-sm text-text-secondary text-left">
          <li className="flex items-start gap-2">
            <kbd className="px-2 py-0.5 bg-background-surface border border-border rounded text-xs font-mono flex-shrink-0">?</kbd>
            <span>Press <strong>?</strong> anytime to see keyboard shortcuts</span>
          </li>
          <li className="flex items-start gap-2">
            <kbd className="px-2 py-0.5 bg-background-surface border border-border rounded text-xs font-mono flex-shrink-0">Ctrl+1</kbd>
            <span>Quick navigation: <strong>Ctrl+1-4</strong> to jump between sections</span>
          </li>
          <li className="flex items-start gap-2">
            <kbd className="px-2 py-0.5 bg-background-surface border border-border rounded text-xs font-mono flex-shrink-0">Ctrl+,</kbd>
            <span>Open <strong>Settings</strong> to customize Arena</span>
          </li>
        </ul>
      </div>

      {/* Action */}
      <Button onClick={onFinish} size="lg" className="w-full">
        Start Using Arena
        <ArrowRight className="w-5 h-5 ml-2" />
      </Button>

      {/* Footer note */}
      <p className="text-xs text-text-muted mt-6">
        You can revisit this setup anytime in Settings → Onboarding
      </p>
    </div>
  );
}
