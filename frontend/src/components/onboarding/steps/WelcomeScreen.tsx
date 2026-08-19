import { Button } from '../../ui/Button';
import { Sparkles, ArrowRight, SkipForward } from 'lucide-react';

interface WelcomeScreenProps {
  onNext: () => void;
  onSkip: () => void;
}

export function WelcomeScreen({ onNext, onSkip }: WelcomeScreenProps) {
  return (
    <div className="max-w-2xl mx-auto px-6 py-12 text-center">
      {/* Logo/Icon */}
      <div className="mb-8">
        <div className="inline-flex items-center justify-center w-24 h-24 bg-accent-primary/10 rounded-full mb-6">
          <Sparkles className="w-12 h-12 text-accent-primary" />
        </div>
      </div>

      {/* Title */}
      <h1 className="text-4xl font-bold text-text-primary mb-4">
        Welcome to Arena
      </h1>

      {/* Description */}
      <p className="text-lg text-text-secondary mb-8 leading-relaxed">
        Your personal AI assistant with voice interaction, knowledge management,
        and powerful tools to help you work smarter.
      </p>

      {/* Features list */}
      <div className="grid gap-4 mb-12 text-left">
        <div className="flex items-start gap-3 p-4 bg-background-secondary rounded-lg">
          <div className="flex-shrink-0 w-8 h-8 bg-accent-primary/10 rounded-full flex items-center justify-center">
            <span className="text-accent-primary font-bold">1</span>
          </div>
          <div>
            <h3 className="font-semibold text-text-primary mb-1">Voice Interaction</h3>
            <p className="text-sm text-text-secondary">
              Talk to Arena naturally with wake word detection and full-duplex conversation
            </p>
          </div>
        </div>

        <div className="flex items-start gap-3 p-4 bg-background-secondary rounded-lg">
          <div className="flex-shrink-0 w-8 h-8 bg-accent-primary/10 rounded-full flex items-center justify-center">
            <span className="text-accent-primary font-bold">2</span>
          </div>
          <div>
            <h3 className="font-semibold text-text-primary mb-1">Knowledge Management</h3>
            <p className="text-sm text-text-secondary">
              Build a visual knowledge graph and organize your memories
            </p>
          </div>
        </div>

        <div className="flex items-start gap-3 p-4 bg-background-secondary rounded-lg">
          <div className="flex-shrink-0 w-8 h-8 bg-accent-primary/10 rounded-full flex items-center justify-center">
            <span className="text-accent-primary font-bold">3</span>
          </div>
          <div>
            <h3 className="font-semibold text-text-primary mb-1">Powerful Tools</h3>
            <p className="text-sm text-text-secondary">
              Execute code, manage files, and analyze documents with AI assistance
            </p>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-3">
        <Button onClick={onNext} size="lg" className="w-full">
          Get Started
          <ArrowRight className="w-5 h-5 ml-2" />
        </Button>

        <button
          onClick={onSkip}
          className="flex items-center justify-center gap-2 text-text-muted hover:text-text-secondary transition-colors"
        >
          <SkipForward className="w-4 h-4" />
          <span className="text-sm">Skip setup</span>
        </button>
      </div>
    </div>
  );
}
