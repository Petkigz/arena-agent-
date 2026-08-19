import { Card } from '../ui/Card';
import { usePresenceStore, useMemoryBrowserStore, useKnowledgeGraphStore, useConversationStore } from '../../stores';
import { Brain, Database, MessageCircle, Target, Zap } from 'lucide-react';

export function ContextPanel() {
  const { presence } = usePresenceStore();
  const memories = useMemoryBrowserStore((s) => s.memories);
  const knowledgeNodes = useKnowledgeGraphStore((s) => s.nodes);
  const knowledgeEdges = useKnowledgeGraphStore((s) => s.edges);
  const conversations = useConversationStore((s) => s.conversations);
  const currentConversation = useConversationStore((s) => s.currentConversation);

  const totalMessages = conversations.reduce((sum, c) => sum + c.messages.length, 0);
  const recentMemories = memories.slice(0, 5);

  return (
    <aside className="w-80 bg-background-secondary border-l border-background-surface overflow-y-auto">
      <div className="p-4 space-y-4">
        {/* Current Goal */}
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-4 h-4 text-accent-primary" />
            <h3 className="text-sm font-semibold text-text-secondary">Current Goal</h3>
          </div>
          {presence.currentGoal ? (
            <p className="text-text-primary">{presence.currentGoal}</p>
          ) : (
            <p className="text-text-muted italic text-sm">No active goal</p>
          )}
          {presence.currentTask && (
            <div className="mt-2 pt-2 border-t border-background-surface">
              <p className="text-xs text-text-muted">
                <span className="font-medium">Task:</span> {presence.currentTask}
              </p>
            </div>
          )}
        </Card>

        {/* Progress */}
        {presence.progress !== undefined && (
          <Card>
            <div className="flex items-center gap-2 mb-2">
              <Zap className="w-4 h-4 text-accent-primary" />
              <h3 className="text-sm font-semibold text-text-secondary">Progress</h3>
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-text-secondary">{Math.round(presence.progress * 100)}%</span>
              </div>
              <div className="w-full bg-background-surface rounded-full h-2">
                <div
                  className="bg-accent-primary h-2 rounded-full transition-all duration-300"
                  style={{ width: `${presence.progress * 100}%` }}
                />
              </div>
            </div>
          </Card>
        )}

        {/* Stats */}
        <Card>
          <h3 className="text-sm font-semibold text-text-secondary mb-3">Statistics</h3>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex items-center gap-2">
              <MessageCircle className="w-4 h-4 text-blue-400" />
              <div>
                <p className="text-lg font-bold text-text-primary">{totalMessages}</p>
                <p className="text-xs text-text-muted">Messages</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-green-400" />
              <div>
                <p className="text-lg font-bold text-text-primary">{memories.length}</p>
                <p className="text-xs text-text-muted">Memories</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple-400" />
              <div>
                <p className="text-lg font-bold text-text-primary">{knowledgeNodes.length}</p>
                <p className="text-xs text-text-muted">Knowledge</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <MessageCircle className="w-4 h-4 text-amber-400" />
              <div>
                <p className="text-lg font-bold text-text-primary">{conversations.length}</p>
                <p className="text-xs text-text-muted">Chats</p>
              </div>
            </div>
          </div>
        </Card>

        {/* Recent Memories */}
        {recentMemories.length > 0 && (
          <Card>
            <h3 className="text-sm font-semibold text-text-secondary mb-2">Recent Memories</h3>
            <div className="space-y-1.5">
              {recentMemories.map((memory) => (
                <div key={memory.id} className="text-sm text-text-primary truncate">
                  • {memory.title}
                </div>
              ))}
            </div>
            <p className="text-xs text-text-muted mt-2">
              {memories.length} total • {memories.filter((m) => m.metadata.importance >= 7).length} high importance
            </p>
          </Card>
        )}

        {/* Knowledge */}
        {knowledgeNodes.length > 0 && (
          <Card>
            <h3 className="text-sm font-semibold text-text-secondary mb-2">Knowledge Graph</h3>
            <div className="space-y-1">
              <div className="text-sm text-text-primary">
                {knowledgeNodes.length} nodes • {knowledgeEdges.length} edges
              </div>
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {knowledgeNodes.slice(0, 5).map((node) => (
                <span
                  key={node.id}
                  className="px-2 py-0.5 bg-background-surface text-text-muted text-xs rounded"
                >
                  {node.label}
                </span>
              ))}
            </div>
          </Card>
        )}

        {/* Current Conversation */}
        {currentConversation && (
          <Card>
            <h3 className="text-sm font-semibold text-text-secondary mb-2">Current Chat</h3>
            <p className="text-sm text-text-primary font-medium">{currentConversation.title}</p>
            <p className="text-xs text-text-muted mt-1">
              {currentConversation.messages.length} messages
            </p>
          </Card>
        )}
      </div>
    </aside>
  );
}
