import { useState, memo } from 'react';
import { ChevronDown, ChevronRight, FileCode } from 'lucide-react';
import type { CodeChange as CodeChangeType } from '../../types';

interface CodeChangesProps {
  changes: CodeChangeType[];
}

export const CodeChanges = memo(function CodeChanges({ changes }: CodeChangesProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!changes || changes.length === 0) return null;

  return (
    <div className="mt-3 border border-background-surface rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-2 flex items-center gap-2 hover:bg-background-secondary transition-colors text-left"
      >
        <FileCode className="w-4 h-4 text-blue-500" />
        <span className="text-sm font-medium text-text-secondary">
          Code Changes ({changes.length} {changes.length === 1 ? 'file' : 'files'})
        </span>
        <div className="flex-1" />
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-text-muted" />
        ) : (
          <ChevronRight className="w-4 h-4 text-text-muted" />
        )}
      </button>
      
      {isExpanded && (
        <div className="border-t border-background-surface divide-y divide-slate-700">
          {changes.map((change, index) => (
            <div key={index} className="p-4 bg-background-primary">
              <div className="flex items-center gap-2 mb-2">
                <FileCode className="w-4 h-4 text-blue-500" />
                <span className="text-sm font-mono text-text-secondary">{change.file}</span>
              </div>
              
              {change.description && (
                <p className="text-xs text-text-muted mb-2">{change.description}</p>
              )}
              
              <pre className="text-xs font-mono bg-background-primary p-3 rounded overflow-x-auto">
                <code className="text-text-secondary whitespace-pre">
                  {change.diff}
                </code>
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
