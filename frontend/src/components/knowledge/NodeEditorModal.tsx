import { useForm } from 'react-hook-form';
import type { KnowledgeNode, NodeType } from '../../stores/knowledgeGraphStore';
import { X } from 'lucide-react';
import { FormField } from '../ui/FormField';

interface NodeEditorModalProps {
  node?: KnowledgeNode | null;
  onSave: (node: KnowledgeNode) => void;
  onClose: () => void;
}

interface NodeFormData {
  label: string;
  type: NodeType;
  description: string;
  importance: number;
  tagsInput: string;
  sourceUrl: string;
  conversationId: string;
}

const nodeTypes: { value: NodeType; label: string }[] = [
  { value: 'concept', label: 'Concept' },
  { value: 'entity', label: 'Entity' },
  { value: 'memory', label: 'Memory' },
  { value: 'conversation', label: 'Conversation' },
  { value: 'file', label: 'File' },
];

export function NodeEditorModal({ node, onSave, onClose }: NodeEditorModalProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<NodeFormData>({
    defaultValues: {
      label: node?.label || '',
      type: node?.type || 'concept',
      description: node?.description || '',
      importance: node?.metadata.importance || 5,
      tagsInput: node?.metadata.tags.join(', ') || '',
      sourceUrl: node?.metadata.sourceUrl || '',
      conversationId: node?.metadata.conversationId || '',
    },
  });

  const onSubmit = (data: NodeFormData) => {
    const now = new Date().toISOString();
    const tags = data.tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const newNode: KnowledgeNode = {
      id: node?.id || `node-${Date.now()}`,
      type: data.type,
      label: data.label,
      description: data.description || undefined,
      metadata: {
        createdAt: node?.metadata.createdAt || now,
        updatedAt: now,
        importance: data.importance,
        tags,
        sourceUrl: data.sourceUrl || undefined,
        conversationId: data.conversationId || undefined,
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

        <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
          {/* Label */}
          <FormField label="Label" required error={errors.label}>
            <input
              {...register('label', {
                required: 'Label is required',
                minLength: { value: 2, message: 'Label must be at least 2 characters' },
                maxLength: { value: 100, message: 'Label must be less than 100 characters' },
              })}
              className={`w-full px-3 py-2 bg-background-surface border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary ${
                errors.label ? 'border-accent-error' : 'border-border'
              }`}
              placeholder="Node label"
            />
          </FormField>

          {/* Type */}
          <FormField label="Type">
            <select
              {...register('type')}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
            >
              {nodeTypes.map((nt) => (
                <option key={nt.value} value={nt.value}>
                  {nt.label}
                </option>
              ))}
            </select>
          </FormField>

          {/* Description */}
          <FormField label="Description" helpText="Optional description of the node">
            <textarea
              {...register('description', {
                maxLength: { value: 500, message: 'Description must be less than 500 characters' },
              })}
              rows={3}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary resize-none"
              placeholder="Describe this node..."
            />
          </FormField>

          {/* Importance */}
          <FormField label={`Importance: ${5}`} helpText="Rate the importance of this node (1-10)">
            <input
              type="range"
              min={1}
              max={10}
              {...register('importance', { valueAsNumber: true })}
              className="w-full"
            />
          </FormField>

          {/* Tags */}
          <FormField label="Tags" helpText="Comma-separated tags">
            <input
              type="text"
              {...register('tagsInput')}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
              placeholder="tag1, tag2, tag3"
            />
          </FormField>

          {/* Source URL */}
          <FormField label="Source URL" helpText="Optional URL source">
            <input
              type="url"
              {...register('sourceUrl', {
                validate: (value) => {
                  if (!value) return true;
                  try {
                    new URL(value);
                    return true;
                  } catch {
                    return 'Please enter a valid URL';
                  }
                },
              })}
              className={`w-full px-3 py-2 bg-background-surface border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary ${
                errors.sourceUrl ? 'border-accent-error' : 'border-border'
              }`}
              placeholder="https://example.com"
            />
            {errors.sourceUrl && (
              <p className="mt-1 text-sm text-accent-error">{errors.sourceUrl.message}</p>
            )}
          </FormField>

          {/* Conversation ID */}
          <FormField label="Conversation ID" helpText="Optional conversation ID to link">
            <input
              type="text"
              {...register('conversationId')}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
              placeholder="conv-123"
            />
          </FormField>

          {/* Actions */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-background-surface text-text-secondary rounded-lg font-medium hover:bg-background-surface/80 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2 bg-accent-primary text-white rounded-lg font-medium hover:bg-accent-primary/90 transition-colors"
            >
              {node ? 'Save Changes' : 'Create Node'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
