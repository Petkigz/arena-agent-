import { useState, useEffect } from 'react';
import { Button } from './Button';
import { Modal } from './Modal';
import { HelpCircle, X, ChevronRight, ChevronLeft, Check } from 'lucide-react';

interface TutorialStep {
  id: string;
  target: string; // CSS selector
  title: string;
  content: string;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

interface InteractiveTutorialProps {
  steps: TutorialStep[];
  isOpen: boolean;
  onClose: () => void;
  onComplete: () => void;
}

export function InteractiveTutorial({ steps, isOpen, onClose, onComplete }: InteractiveTutorialProps) {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [highlightedElement, setHighlightedElement] = useState<HTMLElement | null>(null);

  const currentStep = steps[currentStepIndex];
  const isFirstStep = currentStepIndex === 0;
  const isLastStep = currentStepIndex === steps.length - 1;

  useEffect(() => {
    if (!isOpen || !currentStep) return;

    // Find the target element
    const element = document.querySelector(currentStep.target) as HTMLElement;
    if (element) {
      setHighlightedElement(element);
      
      // Scroll element into view
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      
      // Add highlight class
      element.classList.add('tutorial-highlight');
      
      return () => {
        element.classList.remove('tutorial-highlight');
      };
    }
  }, [isOpen, currentStep]);

  const handleNext = () => {
    if (isLastStep) {
      onComplete();
    } else {
      setCurrentStepIndex(prev => prev + 1);
    }
  };

  const handlePrevious = () => {
    if (!isFirstStep) {
      setCurrentStepIndex(prev => prev - 1);
    }
  };

  const handleSkip = () => {
    onClose();
  };

  if (!isOpen || !currentStep || !highlightedElement) return null;

  // Calculate tooltip position
  const rect = highlightedElement.getBoundingClientRect();
  const position = currentStep.position || 'bottom';
  
  let tooltipStyle: React.CSSProperties = {
    position: 'fixed',
    zIndex: 9999,
    maxWidth: '400px',
  };

  switch (position) {
    case 'top':
      tooltipStyle = {
        ...tooltipStyle,
        bottom: `${window.innerHeight - rect.top + 10}px`,
        left: `${rect.left + rect.width / 2}px`,
        transform: 'translateX(-50%)',
      };
      break;
    case 'bottom':
      tooltipStyle = {
        ...tooltipStyle,
        top: `${rect.bottom + 10}px`,
        left: `${rect.left + rect.width / 2}px`,
        transform: 'translateX(-50%)',
      };
      break;
    case 'left':
      tooltipStyle = {
        ...tooltipStyle,
        top: `${rect.top + rect.height / 2}px`,
        right: `${window.innerWidth - rect.left + 10}px`,
        transform: 'translateY(-50%)',
      };
      break;
    case 'right':
      tooltipStyle = {
        ...tooltipStyle,
        top: `${rect.top + rect.height / 2}px`,
        left: `${rect.right + 10}px`,
        transform: 'translateY(-50%)',
      };
      break;
  }

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black/50 z-[9998]"
        onClick={handleSkip}
      />

      {/* Tooltip */}
      <div style={tooltipStyle} className="bg-background-primary border border-border rounded-lg shadow-xl p-4">
        {/* Progress */}
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-text-muted">
            Step {currentStepIndex + 1} of {steps.length}
          </span>
          <button onClick={handleSkip} className="text-text-muted hover:text-text-primary">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <h3 className="text-lg font-semibold text-text-primary mb-2">{currentStep.title}</h3>
        <p className="text-sm text-text-secondary mb-4">{currentStep.content}</p>

        {/* Actions */}
        <div className="flex items-center justify-between">
          <Button
            onClick={handlePrevious}
            disabled={isFirstStep}
            variant="secondary"
            size="sm"
          >
            <ChevronLeft className="w-4 h-4 mr-1" />
            Previous
          </Button>

          <Button onClick={handleNext} size="sm">
            {isLastStep ? (
              <>
                <Check className="w-4 h-4 mr-1" />
                Finish
              </>
            ) : (
              <>
                Next
                <ChevronRight className="w-4 h-4 ml-1" />
              </>
            )}
          </Button>
        </div>
      </div>
    </>
  );
}

/**
 * Help tooltip component for individual elements
 */
interface HelpTooltipProps {
  content: string;
  children: React.ReactNode;
}

export function HelpTooltip({ content, children }: HelpTooltipProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div className="relative inline-block">
      <div
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        {children}
      </div>

      {showTooltip && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-background-primary border border-border rounded-lg shadow-lg text-xs text-text-secondary whitespace-nowrap">
          {content}
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-border" />
        </div>
      )}
    </div>
  );
}

/**
 * FAQ component
 */
interface FAQItem {
  question: string;
  answer: string;
}

interface FAQProps {
  items: FAQItem[];
  isOpen: boolean;
  onClose: () => void;
}

export function FAQ({ items, isOpen, onClose }: FAQProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Frequently Asked Questions">
      <div className="space-y-3 max-h-96 overflow-y-auto">
        {items.map((item, index) => (
          <div key={index} className="border border-border rounded-lg">
            <button
              onClick={() => setExpandedIndex(expandedIndex === index ? null : index)}
              className="w-full px-4 py-3 text-left hover:bg-background-surface transition-colors"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-text-primary">{item.question}</span>
                <ChevronRight
                  className={`w-4 h-4 text-text-muted transition-transform ${
                    expandedIndex === index ? 'rotate-90' : ''
                  }`}
                />
              </div>
            </button>

            {expandedIndex === index && (
              <div className="px-4 py-3 border-t border-border bg-background-surface">
                <p className="text-sm text-text-secondary">{item.answer}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </Modal>
  );
}

/**
 * Help button component
 */
interface HelpButtonProps {
  onClick: () => void;
}

export function HelpButton({ onClick }: HelpButtonProps) {
  return (
    <button
      onClick={onClick}
      className="p-2 text-text-muted hover:text-text-primary hover:bg-background-surface rounded-lg transition-colors"
      title="Help & Tutorial"
    >
      <HelpCircle className="w-5 h-5" />
    </button>
  );
}
