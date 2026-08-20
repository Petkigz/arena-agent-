import { useState } from 'react';
import type { KnowledgeEdge, EdgeType } from '../../stores/knowledgeGraphStore';
import { X } from 'lucide-react';

interface EdgeEditorModalProps {
  sourceNodeId: string;
  targetNodeId: string;
  sourceLabel: string;
  targetLabel: string;
  onSave: (edge: KnowledgeEdge) => void;
  onClose: () => void;
}

const edgeTypes: { value: EdgeType; label: string }[] = [
  { value: 'relates_to', label: 'Relates to' },
  { value: 'depends_on', label: 'Depends on' },
  { value: 'created_from', label: 'Created from' },
  { value: 'references', label: 'References' },
];

export function EdgeEditorModal({
  sourceLabel,
  targetLabel,
  sourceNodeId,
  targetNodeId,
  onSave,
  onClose,
}: EdgeEditorModalProps) {
  const [edgeType, setEdgeType] = useState<EdgeType>('relates_to');
  const [label, setLabel] = useState('');
  const [weight, setWeight] = useState(5);
  const [context, setContext] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const newEdge: KnowledgeEdge = {
      id: `edge-${Date.now()}`,
      source: sourceNodeId,
      target: targetNodeId,
      type: edgeType,
      label: label || undefined,
      metadata: {
        createdAt: new Date().toISOString(),
        weight,
        context: context || undefined,
      },
    };

    onSave(newEdge);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background-primary rounded-xl shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold text-text-primary">Create Connection</h2>
          <button
            onClick={onClose}
            className="p-1 text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Connection info */}
          <div className="bg-background-surface rounded-lg p-3 text-sm text-text-secondary">
            <span className="font-medium text-text-primary">{sourceLabel}</span>
            <span className="mx-2">→</span>
            <span className="font-medium text-text-primary">{targetLabel}</span>
          </div>

          {/* Edge type */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Relationship Type
            </label>
            <select
              value={edgeType}
              onChange={(e) => setEdgeType(e.target.value as EdgeType)}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
            >
              {edgeTypes.map((et) => (
                <option key={et.value} value={et.value}>
                  {et.label}
                </option>
              ))}
            </select>
          </div>

          {/* Label */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Label (optional)
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
              placeholder="Connection label"
            />
          </div>

          {/* Weight */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Strength: {weight}/10
            </label>
            <input
              type="range"
              min={1}
              max={10}
              value={weight}
              onChange={(e) => setWeight(Number(e.target.value))}
              className="w-full"
            />
          </div>

          {/* Context */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Context (optional)
            </label>
            <textarea
              value={context}
              onChange={(e) => setContext(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary resize-none"
              placeholder="Why are these connected?"
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 px-4 bg-background-surface text-text-secondary rounded-lg font-medium hover:bg-background-surface/80 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 py-2 px-4 bg-accent-primary text-white rounded-lg font-medium hover:bg-accent-primary/90 transition-colors"
            >
              Create Connection
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
