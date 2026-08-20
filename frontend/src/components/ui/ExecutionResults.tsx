import { CheckCircle, XCircle, Clock, Terminal } from 'lucide-react';
import type { ExecutionResult } from '../../stores/codeStore';

interface ExecutionResultsProps {
  result: ExecutionResult;
}

export function ExecutionResults({ result }: ExecutionResultsProps) {
  const { success, output, error, executionTime, timestamp } = result;

  return (
    <div className="border border-border rounded-lg overflow-hidden bg-background-surface">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-background-primary border-b border-border">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-text-muted" />
          <span className="text-sm font-medium text-text-primary">Execution Results</span>
        </div>

        <div className="flex items-center gap-3 text-xs">
          {success ? (
            <div className="flex items-center gap-1 text-accent-success">
              <CheckCircle className="w-4 h-4" />
              <span>Success</span>
            </div>
          ) : (
            <div className="flex items-center gap-1 text-accent-error">
              <XCircle className="w-4 h-4" />
              <span>Failed</span>
            </div>
          )}

          <div className="flex items-center gap-1 text-text-muted">
            <Clock className="w-3 h-3" />
            <span>{executionTime}ms</span>
          </div>
        </div>
      </div>

      {/* Output */}
      <div className="p-4 space-y-3">
        {output && (
          <div>
            <div className="text-xs text-text-muted mb-2 font-medium">Output:</div>
            <pre className="p-3 bg-background-primary rounded text-sm text-text-primary font-mono whitespace-pre-wrap overflow-x-auto">
              {output}
            </pre>
          </div>
        )}

        {error && (
          <div>
            <div className="text-xs text-accent-error mb-2 font-medium">Error:</div>
            <pre className="p-3 bg-accent-error/10 border border-accent-error/30 rounded text-sm text-accent-error font-mono whitespace-pre-wrap overflow-x-auto">
              {error}
            </pre>
          </div>
        )}

        {!output && !error && (
          <div className="text-center py-8 text-text-muted">
            <Terminal className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No output</p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-background-primary border-t border-border text-xs text-text-muted">
        Executed at {new Date(timestamp).toLocaleString()}
      </div>
    </div>
  );
}
