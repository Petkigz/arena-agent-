import { useState, useRef } from 'react';
import { Card, EmptyState } from '../../components/ui';
import { useMemoryBrowserStore, type Memory, type MemoryCategory } from '../../stores';
import { Database, Search, Calendar, Star, Trash2, Plus, Download, Upload, Clock, List, Edit, MessageCircle, X } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { highlightText } from '../../utils/searchHighlight';
import { MemoryTimeline } from './MemoryTimeline';
import { MemoryEditorModal } from './MemoryEditorModal';
import {
  exportMemoriesAsJSON,
  importMemoriesFromJSON,
  downloadFile,
} from '../../utils/graphExport';
import { notifications } from '../../services/notifications';

const categoryIcons: Record<MemoryCategory, string> = {
  episodic: '🎭',
  semantic: '🧠',
  procedural: '⚙️',
  conversation: '💬',
};

const categoryColors: Record<MemoryCategory, string> = {
  episodic: 'bg-accent-secondary text-accent-secondary',
  semantic: 'bg-accent-primary text-accent-primary',
  procedural: 'bg-accent-success text-accent-success',
  conversation: 'bg-accent-warning text-accent-warning',
};

type ViewMode = 'list' | 'timeline';

export function MemoryBrowser() {
  const {
    memories,
    searchMemories,
    getMemoriesByCategory,
    removeMemory,
    addMemory,
    updateMemory,
    importMemories,
    exportMemories,
  } = useMemoryBrowserStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<MemoryCategory | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [showEditor, setShowEditor] = useState(false);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const filteredMemories = searchQuery
    ? searchMemories(searchQuery)
    : selectedCategory
    ? getMemoriesByCategory(selectedCategory)
    : memories;

  const handleRemoveMemory = (id: string) => {
    if (confirm('Are you sure you want to delete this memory?')) {
      removeMemory(id);
    }
  };

  const handleSaveMemory = (memory: Memory) => {
    const existing = memories.find((m) => m.id === memory.id);
    if (existing) {
      updateMemory(memory.id, memory);
    } else {
      addMemory(memory);
    }
    setShowEditor(false);
    setEditingMemory(null);
  };

  const handleExportJSON = () => {
    const data = exportMemories();
    const json = exportMemoriesAsJSON(data);
    downloadFile(json, `memories-${new Date().toISOString().split('T')[0]}.json`, 'application/json');
    setShowExportMenu(false);
  };

  const handleImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const imported = importMemoriesFromJSON(content);
        importMemories(imported);
      } catch (err) {
        notifications.error('Failed to import memories: ' + (err instanceof Error ? err.message : 'Unknown error'));
      }
    };
    reader.readAsText(file);
    event.target.value = '';
    setShowExportMenu(false);
  };

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="flex-shrink-0 space-y-4 mb-6">
        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search memories..."
              className="w-full pl-10 pr-8 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-text-primary"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* View toggle */}
          <div className="flex bg-background-surface rounded-lg p-1">
            <button
              onClick={() => setViewMode('list')}
              className={`p-2 rounded transition-colors ${
                viewMode === 'list'
                  ? 'bg-accent-primary text-white'
                  : 'text-text-muted hover:text-text-primary'
              }`}
              title="List view"
            >
              <List className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('timeline')}
              className={`p-2 rounded transition-colors ${
                viewMode === 'timeline'
                  ? 'bg-accent-primary text-white'
                  : 'text-text-muted hover:text-text-primary'
              }`}
              title="Timeline view"
            >
              <Clock className="w-4 h-4" />
            </button>
          </div>

          {/* Add */}
          <button
            onClick={() => { setEditingMemory(null); setShowEditor(true); }}
            className="flex items-center gap-2 px-3 py-2 bg-accent-primary text-white rounded-lg text-sm font-medium hover:bg-accent-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Add Memory</span>
          </button>

          {/* Export/Import */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              className="flex items-center gap-2 px-3 py-2 bg-background-surface text-text-secondary rounded-lg text-sm font-medium hover:bg-background-surface/80 transition-colors"
            >
              <Download className="w-4 h-4" />
            </button>
            {showExportMenu && (
              <div className="absolute top-full mt-1 right-0 bg-background-primary border border-border rounded-lg shadow-lg z-30 min-w-[160px]">
                <button
                  onClick={handleExportJSON}
                  className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-background-surface flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  Export JSON
                </button>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-background-surface flex items-center gap-2"
                >
                  <Upload className="w-4 h-4" />
                  Import JSON
                </button>
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleImport}
              className="hidden"
            />
          </div>
        </div>

        {/* Category Filter (list view only) */}
        {viewMode === 'list' && (
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => setSelectedCategory(null)}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                selectedCategory === null
                  ? 'bg-accent-primary text-white'
                  : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
              }`}
            >
              All ({memories.length})
            </button>
            {(['episodic', 'semantic', 'procedural', 'conversation'] as MemoryCategory[]).map((category) => {
              const count = memories.filter(m => m.category === category).length;
              return (
                <button
                  key={category}
                  onClick={() => setSelectedCategory(category)}
                  className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                    selectedCategory === category
                      ? 'bg-accent-primary text-white'
                      : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
                  }`}
                >
                  {categoryIcons[category]} {category} ({count})
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {viewMode === 'timeline' ? (
          <MemoryTimeline
            memories={filteredMemories}
            searchQuery={searchQuery}
          />
        ) : (
          <div className="space-y-3">
            {filteredMemories.length === 0 ? (
              <EmptyState
                icon={<Database className="w-16 h-16" />}
                title="No Memories Found"
                description={
                  searchQuery
                    ? 'No memories match your search query.'
                    : 'No memories in this category yet.'
                }
                action={
                  !searchQuery && !selectedCategory ? (
                    <button
                      onClick={() => { setEditingMemory(null); setShowEditor(true); }}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-accent-primary text-white rounded-lg font-medium hover:bg-accent-primary/90 transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                      Create First Memory
                    </button>
                  ) : undefined
                }
              />
            ) : (
              filteredMemories.map((memory) => (
                <MemoryCard
                  key={memory.id}
                  memory={memory}
                  searchQuery={searchQuery}
                  onRemove={() => handleRemoveMemory(memory.id)}
                  onEdit={() => { setEditingMemory(memory); setShowEditor(true); }}
                />
              ))
            )}
          </div>
        )}
      </div>

      {/* Editor Modal */}
      {showEditor && (
        <MemoryEditorModal
          memory={editingMemory}
          onSave={handleSaveMemory}
          onClose={() => { setShowEditor(false); setEditingMemory(null); }}
        />
      )}
    </div>
  );
}

interface MemoryCardProps {
  memory: Memory;
  searchQuery: string;
  onRemove: () => void;
  onEdit: () => void;
}

function MemoryCard({ memory, searchQuery, onRemove, onEdit }: MemoryCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="hover:shadow-lg transition-shadow">
      <div className="space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${categoryColors[memory.category]}`}>
                {categoryIcons[memory.category]} {memory.category}
              </span>
              <div className="flex items-center gap-1 text-xs text-text-muted">
                <Calendar className="w-3 h-3" />
                <span>{formatDistanceToNow(new Date(memory.metadata.createdAt), { addSuffix: true })}</span>
              </div>
            </div>
            <h3 className="text-lg font-semibold text-text-primary">
              {highlightText(memory.title, searchQuery)}
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 text-xs text-text-muted">
              <Star className="w-3 h-3" />
              <span>{memory.metadata.importance}/10</span>
            </div>
            <button
              onClick={onEdit}
              className="p-1 text-text-muted hover:text-accent-primary transition-colors"
              title="Edit"
            >
              <Edit className="w-4 h-4" />
            </button>
            <button
              onClick={onRemove}
              className="p-1 text-text-muted hover:text-accent-error transition-colors"
              title="Delete"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="text-sm text-text-secondary">
          {expanded ? (
            <p className="whitespace-pre-wrap">{highlightText(memory.content, searchQuery)}</p>
          ) : (
            <p className="line-clamp-3">{highlightText(memory.content, searchQuery)}</p>
          )}
        </div>

        {/* Tags */}
        {memory.metadata.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {memory.metadata.tags.map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 bg-background-surface text-text-muted text-xs rounded"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* Conversation link */}
        {memory.metadata.conversationId && (
          <div className="flex items-center gap-1 text-xs text-accent-primary">
            <MessageCircle className="w-3 h-3" />
            <span>Linked to conversation {memory.metadata.conversationId}</span>
          </div>
        )}

        {/* Expand/Collapse */}
        {memory.content.length > 200 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm text-accent-primary hover:underline"
          >
            {expanded ? 'Show less' : 'Show more'}
          </button>
        )}
      </div>
    </Card>
  );
}
