import { useState } from 'react';
import type { KnowledgeNode, NodeType } from '../../stores/knowledgeGraphStore';
import { X } from 'lucide-react';

interface NodeEditorModalProps {
  node?: KnowledgeNode | null;
  onSave: (node: KnowledgeNode) => void;
  onClose: () => void;
}

const nodeTypes: { value: NodeType; label: string }[] = [
  { value: 'concept', label: 'Concept' },
  { value: 'entity', label: 'Entity' },
  { value: 'memory', label: 'Memory' },
  { value: 'conversation', label: 'Conversation' },
  { value: 'file', label: 'File' },
];

export function NodeEditorModal({ node, onSave, onClose }: NodeEditorModalProps) {
  const [label, setLabel] = useState(node?.label || '');
  const [type, setType] = useState<NodeType>(node?.type || 'concept');
  const [description, setDescription] = useState(node?.description || '');
  const [importance, setImportance] = useState(node?.metadata.importance || 5);
  const [tagsInput, setTagsInput] = useState(node?.metadata.tags.join(', ') || '');
  const [sourceUrl, setSourceUrl] = useState(node?.metadata.sourceUrl || '');
  const [conversationId, setConversationId] = useState(node?.metadata.conversationId || '');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const now = new Date().toISOString();
    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const newNode: KnowledgeNode = {
      id: node?.id || `node-${Date.now()}`,
      type,
      label,
      description: description || undefined,
      metadata: {
        createdAt: node?.metadata.createdAt || now,
        updatedAt: now,
        importance,
        tags,
        sourceUrl: sourceUrl || undefined,
        conversationId: conversationId || undefined,
      },
    };

    onSave(newNode);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background-primary rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold text-text-primary">
            {node ? 'Edit Node' : 'Create Node'}
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Label */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Label *
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              required
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
              placeholder="Node label"
            />
          </div>

          {/* Type */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Type
            </label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value as NodeType)}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
            >
              {nodeTypes.map((nt) => (
                <option key={nt.value} value={nt.value}>
                  {nt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary resize-none"
              placeholder="Describe this node..."
            />
          </div>

          {/* Importance */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Importance: {importance}/10
            </label>
            <input
              type="range"
              min={1}
              max={10}
              value={importance}
              onChange={(e) => setImportance(Number(e.target.value))}
              className="w-full"
            />
          </div>

          {/* Tags */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Tags (comma-separated)
            </label>
            <input
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
              placeholder="tag1, tag2, tag3"
            />
          </div>

          {/* Source URL */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Source URL
            </label>
            <input
              type="url"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
              placeholder="https://..."
            />
          </div>

          {/* Conversation ID */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Linked Conversation ID
            </label>
            <input
              type="text"
              value={conversationId}
              onChange={(e) => setConversationId(e.target.value)}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
              placeholder="conv-..."
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
              {node ? 'Save Changes' : 'Create Node'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
