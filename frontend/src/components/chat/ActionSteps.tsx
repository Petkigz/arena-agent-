import { memo } from 'react';
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';
import type { ActionStep as ActionStepType } from '../../types';

interface ActionStepsProps {
  steps: ActionStepType[];
}

function ActionStepsComponent({ steps }: ActionStepsProps) {
  if (!steps || steps.length === 0) return null;

  return (
    <div className="mt-3 space-y-1.5">
      {steps.map((step, index) => (
        <div key={step.id || index} className="flex items-start gap-2 text-sm">
          <div className="mt-0.5 flex-shrink-0">
            {step.status === 'complete' && (
              <CheckCircle2 className="w-4 h-4 text-accent-success" />
            )}
            {step.status === 'in_progress' && (
              <Loader2 className="w-4 h-4 text-accent-primary animate-spin drop-shadow-glow" />
            )}
            {step.status === 'pending' && (
              <Circle className="w-4 h-4 text-text-muted" />
            )}
            {step.status === 'error' && (
              <Circle className="w-4 h-4 text-accent-error" />
            )}
          </div>
          <div className="flex-1">
            <div className={
              step.status === 'complete' ? 'text-accent-success' :
              step.status === 'in_progress' ? 'text-accent-primary' :
              step.status === 'error' ? 'text-accent-error' :
              'text-text-muted'
            }>
              {step.description}
            </div>
            {step.details && (
              <div className="text-xs text-text-muted mt-0.5">
                {step.details}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export const ActionSteps = memo(ActionStepsComponent);
