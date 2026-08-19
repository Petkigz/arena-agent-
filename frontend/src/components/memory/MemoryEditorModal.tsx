import { useForm } from 'react-hook-form';
import type { Memory, MemoryCategory } from '../../stores/memoryBrowserStore';
import { X } from 'lucide-react';
import { FormField } from '../ui/FormField';

interface MemoryEditorModalProps {
  memory?: Memory | null;
  onSave: (memory: Memory) => void;
  onClose: () => void;
}

interface MemoryFormData {
  title: string;
  category: MemoryCategory;
  content: string;
  importance: number;
  tagsInput: string;
  conversationId: string;
}

const categories: { value: MemoryCategory; label: string; icon: string }[] = [
  { value: 'episodic', label: 'Episodic', icon: '🎭' },
  { value: 'semantic', label: 'Semantic', icon: '🧠' },
  { value: 'procedural', label: 'Procedural', icon: '⚙️' },
  { value: 'conversation', label: 'Conversation', icon: '💬' },
];

export function MemoryEditorModal({ memory, onSave, onClose }: MemoryEditorModalProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<MemoryFormData>({
    defaultValues: {
      title: memory?.title || '',
      category: memory?.category || 'semantic',
      content: memory?.content || '',
      importance: memory?.metadata.importance || 5,
      tagsInput: memory?.metadata.tags.join(', ') || '',
      conversationId: memory?.metadata.conversationId || '',
    },
  });

  const onSubmit = (data: MemoryFormData) => {
    const now = new Date().toISOString();
    const tags = data.tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const newMemory: Memory = {
      id: memory?.id || crypto.randomUUID(),
      category: data.category,
      title: data.title,
      content: data.content,
      metadata: {
        createdAt: memory?.metadata.createdAt || now,
        updatedAt: now,
        importance: data.importance,
        tags,
        conversationId: data.conversationId || undefined,
      },
    };

    onSave(newMemory);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-background-primary rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold text-text-primary">
            {memory ? 'Edit Memory' : 'Create Memory'}
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-4 space-y-4">
          {/* Title */}
          <FormField label="Title" required error={errors.title}>
            <input
              {...register('title', {
                required: 'Title is required',
                minLength: { value: 3, message: 'Title must be at least 3 characters' },
                maxLength: { value: 200, message: 'Title must be less than 200 characters' },
              })}
              className={`w-full px-3 py-2 bg-background-surface border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary ${
                errors.title ? 'border-accent-error' : 'border-border'
              }`}
              placeholder="Memory title"
            />
          </FormField>

          {/* Category */}
          <FormField label="Category">
            <div className="grid grid-cols-2 gap-2">
              {categories.map((cat) => (
                <label
                  key={cat.value}
                  className={`flex items-center gap-2 p-3 rounded-lg border-2 cursor-pointer transition-colors ${
                    memory?.category === cat.value
                      ? 'border-accent-primary bg-accent-primary/10'
                      : 'border-border hover:border-accent-primary/50'
                  }`}
                >
                  <input
                    type="radio"
                    value={cat.value}
                    {...register('category')}
                    className="sr-only"
                  />
                  <span className="text-lg">{cat.icon}</span>
                  <span className="text-sm font-medium text-text-primary">{cat.label}</span>
                </label>
              ))}
            </div>
          </FormField>

          {/* Content */}
          <FormField label="Content" required error={errors.content}>
            <textarea
              {...register('content', {
                required: 'Content is required',
                minLength: { value: 10, message: 'Content must be at least 10 characters' },
                maxLength: { value: 5000, message: 'Content must be less than 5000 characters' },
              })}
              rows={6}
              className={`w-full px-3 py-2 bg-background-surface border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary resize-none ${
                errors.content ? 'border-accent-error' : 'border-border'
              }`}
              placeholder="What do you want to remember?"
            />
          </FormField>

          {/* Importance */}
          <FormField label={`Importance: ${5}`} helpText="Rate the importance of this memory (1-10)">
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
              {memory ? 'Save Changes' : 'Create Memory'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
