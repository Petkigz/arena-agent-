import { useState, memo } from 'react';
import { ChevronDown, ChevronRight, Brain } from 'lucide-react';

interface ReasoningTraceProps {
  trace: string;
}

export const ReasoningTrace = memo(function ReasoningTrace({ trace }: ReasoningTraceProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!trace) return null;

  return (
    <div className="mt-3 border border-background-surface rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-2 flex items-center gap-2 hover:bg-background-secondary transition-colors text-left"
      >
        <Brain className="w-4 h-4 text-purple-500" />
        <span className="text-sm font-medium text-text-secondary">Reasoning Trace</span>
        <div className="flex-1" />
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-text-muted" />
        ) : (
          <ChevronRight className="w-4 h-4 text-text-muted" />
        )}
      </button>
      
      {isExpanded && (
        <div className="px-4 py-3 bg-background-primary border-t border-background-surface">
          <pre className="text-xs text-text-secondary whitespace-pre-wrap font-mono leading-relaxed">
            {trace}
          </pre>
        </div>
      )}
    </div>
  );
});
