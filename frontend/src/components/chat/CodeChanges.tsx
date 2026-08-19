import { useState } from 'react';
import { ChevronDown, ChevronRight, FileCode } from 'lucide-react';
import type { CodeChange as CodeChangeType } from '../../types';

interface CodeChangesProps {
  changes: CodeChangeType[];
}

export function CodeChanges({ changes }: CodeChangesProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!changes || changes.length === 0) return null;

  return (
    <div className="mt-3 border border-slate-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-2 flex items-center gap-2 hover:bg-slate-800 transition-colors text-left"
      >
        <FileCode className="w-4 h-4 text-blue-500" />
        <span className="text-sm font-medium text-slate-300">
          Code Changes ({changes.length} {changes.length === 1 ? 'file' : 'files'})
        </span>
        <div className="flex-1" />
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-slate-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-400" />
        )}
      </button>
      
      {isExpanded && (
        <div className="border-t border-slate-700 divide-y divide-slate-700">
          {changes.map((change, index) => (
            <div key={index} className="p-4 bg-slate-900">
              <div className="flex items-center gap-2 mb-2">
                <FileCode className="w-4 h-4 text-blue-500" />
                <span className="text-sm font-mono text-slate-300">{change.file}</span>
              </div>
              
              {change.description && (
                <p className="text-xs text-slate-400 mb-2">{change.description}</p>
              )}
              
              <pre className="text-xs font-mono bg-slate-950 p-3 rounded overflow-x-auto">
                <code className="text-slate-300 whitespace-pre">
                  {change.diff}
                </code>
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
