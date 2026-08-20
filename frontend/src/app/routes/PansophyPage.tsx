import { useState } from 'react';
import { KnowledgeGraphView } from '../../components/knowledge/KnowledgeGraphView';
import { MemoryBrowser } from '../../components/memory/MemoryBrowser';
import { ConversationHistory } from '../../components/exploration/ConversationHistory';
import { LearningPatterns } from '../../components/exploration/LearningPatterns';
import { useMemoryBrowserStore, useConversationStore, useKnowledgeGraphStore } from '../../stores';
import { Brain, Database, MessageCircle, TrendingUp } from 'lucide-react';

type TabType = 'knowledge' | 'memory' | 'conversations' | 'patterns';

export function PansophyPage() {
  const [activeTab, setActiveTab] = useState<TabType>('knowledge');

  const memories = useMemoryBrowserStore((s) => s.memories);
  const conversations = useConversationStore((s) => s.conversations);
  const knowledgeNodes = useKnowledgeGraphStore((s) => s.nodes);

  const tabs = [
    { id: 'knowledge' as TabType, label: 'Knowledge Graph', icon: Brain },
    { id: 'memory' as TabType, label: 'Memory Browser', icon: Database },
    { id: 'conversations' as TabType, label: 'Conversations', icon: MessageCircle },
    { id: 'patterns' as TabType, label: 'Learning Patterns', icon: TrendingUp },
  ];

  return (
    <div className="h-full flex flex-col bg-background-primary">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border">
        <h1 className="text-2xl font-bold text-text-primary">Pansophy</h1>
        <p className="text-text-secondary mt-1">
          Explore your knowledge, memories, and conversations
        </p>
      </div>

      {/* Tabs */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border">
        <div className="flex gap-2 flex-wrap">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'bg-accent-primary text-white'
                    : 'bg-background-surface text-text-secondary hover:bg-background-surface/80'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden px-6 py-6">
        {activeTab === 'knowledge' && <KnowledgeGraphView />}
        {activeTab === 'memory' && <MemoryBrowser />}
        {activeTab === 'conversations' && <ConversationHistory />}
        {activeTab === 'patterns' && (
          <div className="h-full overflow-y-auto">
            <LearningPatterns
              memories={memories}
              conversations={conversations}
              knowledgeNodes={knowledgeNodes}
            />
          </div>
        )}
      </div>
    </div>
  );
}
