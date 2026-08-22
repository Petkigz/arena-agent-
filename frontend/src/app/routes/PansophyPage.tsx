import { useState, useEffect } from 'react';
import { KnowledgeGraphView } from '../../components/knowledge/KnowledgeGraphView';
import { MemoryBrowser } from '../../components/memory/MemoryBrowser';
import { ConversationHistory } from '../../components/exploration/ConversationHistory';
import { LearningPatterns } from '../../components/exploration/LearningPatterns';
import { useMemoryBrowserStore, useConversationStore, useKnowledgeGraphStore } from '../../stores';
import type { KnowledgeNode, KnowledgeEdge, NodeType, EdgeType } from '../../stores/knowledgeGraphStore';
import { fetchKnowledgeGraph } from '../../services/api';
import { Brain, Database, MessageCircle, TrendingUp } from 'lucide-react';

type TabType = 'knowledge' | 'memory' | 'conversations' | 'patterns';

// Map backend entity_type / predicate onto the frontend's graph vocabulary.
function mapNodeType(t: string): NodeType {
  switch (t) {
    case 'file': return 'file';
    case 'concept': return 'concept';
    case 'memory': return 'memory';
    case 'conversation': return 'conversation';
    default: return 'entity';
  }
}

function mapEdgeType(p: string): EdgeType {
  switch (p) {
    case 'depends_on': return 'depends_on';
    case 'references': return 'references';
    case 'created_from': return 'created_from';
    default: return 'relates_to';
  }
}

function clamp1to10(n: number): number {
  return Math.max(1, Math.min(10, Math.round(n)));
}

export function PansophyPage() {
  const [activeTab, setActiveTab] = useState<TabType>('knowledge');

  const memories = useMemoryBrowserStore((s) => s.memories);
  const conversations = useConversationStore((s) => s.conversations);
  const knowledgeNodes = useKnowledgeGraphStore((s) => s.nodes);
  const importGraph = useKnowledgeGraphStore((s) => s.importGraph);

  // Load the knowledge graph from the backend into the store on mount.
  useEffect(() => {
    let cancelled = false;
    fetchKnowledgeGraph().then((graph) => {
      if (cancelled || !graph) return;
      const nodes: KnowledgeNode[] = graph.entities.map((e) => ({
        id: e.id,
        type: mapNodeType(e.type),
        label: e.name,
        description: e.type,
        metadata: {
          createdAt: e.first_seen,
          updatedAt: e.last_seen,
          importance: clamp1to10(e.confidence * 10),
          tags: [e.type],
        },
      }));
      const edges: KnowledgeEdge[] = graph.relationships.map((r) => ({
        id: r.id,
        source: r.subject_id,
        target: r.object_id,
        type: mapEdgeType(r.predicate),
        label: r.predicate,
        metadata: {
          createdAt: r.created_at,
          weight: clamp1to10(r.confidence * 10),
        },
      }));
      importGraph(nodes, edges);
    });
    return () => {
      cancelled = true;
    };
  }, [importGraph]);

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
