import { useState } from 'react';
import { ChevronDown, ChevronRight, Brain } from 'lucide-react';

interface ReasoningTraceProps {
  trace: string;
}

export function ReasoningTrace({ trace }: ReasoningTraceProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!trace) return null;

  return (
    <div className="mt-3 border border-slate-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-2 flex items-center gap-2 hover:bg-slate-800 transition-colors text-left"
      >
        <Brain className="w-4 h-4 text-purple-500" />
        <span className="text-sm font-medium text-slate-300">Reasoning Trace</span>
        <div className="flex-1" />
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-400" />
        )}
      </button>
      
      {isExpanded && (
        <div className="px-4 py-3 bg-slate-900 border-t border-slate-700">
          <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">
            {trace}
          </pre>
        </div>
      )}
    </div>
  );
}
