import { useState } from 'react';
import { Card } from '../../components/ui';
import { useConversationStore } from '../../stores';
import { MessageCircle, Search, Calendar, Trash2, FileText, FileJson } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import {
  exportConversationAsMarkdown,
  downloadFile,
} from '../../utils/graphExport';

export function ConversationHistory() {
  const { conversations, removeConversation, exportConversation } = useConversationStore();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedConversation, setSelectedConversation] = useState<string | null>(null);

  const filteredConversations = searchQuery
    ? conversations.filter(conv =>
        conv.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        conv.messages.some(m => m.content.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : conversations;

  const handleRemoveConversation = (id: string) => {
    if (confirm('Are you sure you want to delete this conversation?')) {
      removeConversation(id);
    }
  };

  const handleExportJSON = (id: string) => {
    const conversation = conversations.find(c => c.id === id);
    if (conversation) {
      const data = exportConversation(id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `conversation-${conversation.title}-${new Date().toISOString().split('T')[0]}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const handleExportMarkdown = (id: string) => {
    const conversation = conversations.find(c => c.id === id);
    if (conversation) {
      const md = exportConversationAsMarkdown(conversation);
      downloadFile(
        md,
        `conversation-${conversation.title}-${new Date().toISOString().split('T')[0]}.md`,
        'text/markdown'
      );
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Search Bar */}
      <div className="flex-shrink-0 mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className="w-full pl-10 pr-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
          />
        </div>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto space-y-3">
        {filteredConversations.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <Card className="max-w-md">
              <div className="text-center">
                <MessageCircle className="w-16 h-16 text-text-muted mx-auto mb-4" />
                <h3 className="text-xl font-semibold text-text-primary mb-2">
                  No Conversations Found
                </h3>
                <p className="text-text-secondary">
                  {searchQuery
                    ? 'No conversations match your search query.'
                    : 'No conversations yet.'}
                </p>
              </div>
            </Card>
          </div>
        ) : (
          filteredConversations.map((conversation) => (
            <Card
              key={conversation.id}
              className="hover:shadow-lg transition-shadow cursor-pointer"
              onClick={() => setSelectedConversation(
                selectedConversation === conversation.id ? null : conversation.id
              )}
            >
              <div className="space-y-3">
                {/* Header */}
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <MessageCircle className="w-4 h-4 text-accent-primary" />
                      <div className="flex items-center gap-1 text-xs text-text-muted">
                        <Calendar className="w-3 h-3" />
                        <span>{formatDistanceToNow(new Date(conversation.updatedAt), { addSuffix: true })}</span>
                      </div>
                    </div>
                    <h3 className="text-lg font-semibold text-text-primary">{conversation.title}</h3>
                    <p className="text-sm text-text-muted mt-1">
                      {conversation.messages.length} messages
                    </p>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleExportMarkdown(conversation.id);
                      }}
                      className="p-1.5 text-text-muted hover:text-accent-primary transition-colors"
                      title="Export as Markdown"
                    >
                      <FileText className="w-4 h-4" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleExportJSON(conversation.id);
                      }}
                      className="p-1.5 text-text-muted hover:text-accent-primary transition-colors"
                      title="Export as JSON"
                    >
                      <FileJson className="w-4 h-4" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemoveConversation(conversation.id);
                      }}
                      className="p-1.5 text-text-muted hover:text-accent-error transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Preview */}
                {conversation.messages.length > 0 && (
                  <div className="text-sm text-text-secondary line-clamp-2">
                    {conversation.messages[conversation.messages.length - 1].content}
                  </div>
                )}

                {/* Expanded View */}
                {selectedConversation === conversation.id && (
                  <div className="border-t border-border pt-3 space-y-2">
                    <h4 className="text-sm font-semibold text-text-primary">Messages</h4>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {conversation.messages.map((message) => (
                        <div
                          key={message.id}
                          className={`p-2 rounded ${
                            message.role === 'user'
                              ? 'bg-accent-primary/10 text-text-primary'
                              : 'bg-background-surface text-text-secondary'
                          }`}
                        >
                          <div className="text-xs text-text-muted mb-1">
                            {message.role === 'user' ? 'You' : 'Assistant'} •{' '}
                            {formatDistanceToNow(new Date(message.timestamp), { addSuffix: true })}
                          </div>
                          <p className="text-sm">{message.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
