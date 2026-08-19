import { useState } from 'react';
import type { Memory, MemoryCategory } from '../../stores/memoryBrowserStore';
import { X } from 'lucide-react';

interface MemoryEditorModalProps {
  memory?: Memory | null;
  onSave: (memory: Memory) => void;
  onClose: () => void;
}

const categories: { value: MemoryCategory; label: string; icon: string }[] = [
  { value: 'episodic', label: 'Episodic', icon: '🎭' },
  { value: 'semantic', label: 'Semantic', icon: '🧠' },
  { value: 'procedural', label: 'Procedural', icon: '⚙️' },
  { value: 'conversation', label: 'Conversation', icon: '💬' },
];

export function MemoryEditorModal({ memory, onSave, onClose }: MemoryEditorModalProps) {
  const [title, setTitle] = useState(memory?.title || '');
  const [category, setCategory] = useState<MemoryCategory>(memory?.category || 'semantic');
  const [content, setContent] = useState(memory?.content || '');
  const [importance, setImportance] = useState(memory?.metadata.importance || 5);
  const [tagsInput, setTagsInput] = useState(memory?.metadata.tags.join(', ') || '');
  const [conversationId, setConversationId] = useState(memory?.metadata.conversationId || '');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const now = new Date().toISOString();
    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const newMemory: Memory = {
      id: memory?.id || `mem-${Date.now()}`,
      category,
      title,
      content,
      metadata: {
        createdAt: memory?.metadata.createdAt || now,
        updatedAt: now,
        importance,
        tags,
        conversationId: conversationId || undefined,
        sourceType: memory?.metadata.sourceType || 'user',
        relatedMemoryIds: memory?.metadata.relatedMemoryIds,
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

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Title *
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
              placeholder="Memory title"
            />
          </div>

          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-2">
              Category
            </label>
            <div className="grid grid-cols-2 gap-2">
              {categories.map((cat) => (
                <button
                  key={cat.value}
                  type="button"
                  onClick={() => setCategory(cat.value)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    category === cat.value
                      ? 'bg-accent-primary text-white'
                      : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
                  }`}
                >
                  <span>{cat.icon}</span>
                  <span>{cat.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Content */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Content *
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              required
              rows={5}
              className="w-full px-3 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary resize-none"
              placeholder="What do you want to remember?"
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
              {memory ? 'Save Changes' : 'Create Memory'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
