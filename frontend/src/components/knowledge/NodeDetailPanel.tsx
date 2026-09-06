import type { KnowledgeNode, KnowledgeEdge } from '../../stores/knowledgeGraphStore';
import { X, Brain, Database, MessageCircle, FileText, Link, Star, Calendar, Tag, ExternalLink } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { Card } from '../ui';
import { KNOWLEDGE_NODE_TYPE_COLORS } from '../../design/tokens';

const nodeTypeIcons = {
  concept: Brain,
  entity: Database,
  memory: Database,
  conversation: MessageCircle,
  file: FileText,
};

// Taxonomy colors come from the shared design system (design/tokens.json) —
// the same file KnowledgeGraphView uses, so the two views cannot diverge.
const nodeTypeColors = KNOWLEDGE_NODE_TYPE_COLORS;

interface NodeDetailPanelProps {
  node: KnowledgeNode;
  edges: KnowledgeEdge[];
  allNodes: KnowledgeNode[];
  onClose: () => void;
  onEdit: () => void;
  onNavigateToConversation?: (conversationId: string) => void;
}

export function NodeDetailPanel({
  node,
  edges,
  allNodes,
  onClose,
  onEdit,
  onNavigateToConversation,
}: NodeDetailPanelProps) {
  const Icon = nodeTypeIcons[node.type];
  const color = nodeTypeColors[node.type];

  // Find connected nodes
  const connectedEdges = edges.filter(
    (e) => e.source === node.id || e.target === node.id
  );

  const connections = connectedEdges.map((edge) => {
    const otherNodeId = edge.source === node.id ? edge.target : edge.source;
    const otherNode = allNodes.find((n) => n.id === otherNodeId);
    const direction = edge.source === node.id ? 'outgoing' : 'incoming';
    return { edge, otherNode, direction };
  });

  return (
    <div className="w-80 h-full border-l border-border bg-background-primary overflow-y-auto flex-shrink-0">
      <div className="p-4 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div
              className="w-10 h-10 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: `${color}20` }}
            >
              <Icon className="w-5 h-5" style={{ color }} />
            </div>
            <div>
              <span
                className="text-xs font-medium uppercase tracking-wide"
                style={{ color }}
              >
                {node.type}
              </span>
              <h3 className="text-lg font-semibold text-text-primary">{node.label}</h3>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Description */}
        {node.description && (
          <div>
            <h4 className="text-sm font-medium text-text-secondary mb-1">Description</h4>
            <p className="text-sm text-text-primary">{node.description}</p>
          </div>
        )}

        {/* Metadata */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <Star className="w-4 h-4" />
            <span>Importance: {node.metadata.importance}/10</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <Calendar className="w-4 h-4" />
            <span>Created {formatDistanceToNow(new Date(node.metadata.createdAt), { addSuffix: true })}</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <Calendar className="w-4 h-4" />
            <span>Updated {formatDistanceToNow(new Date(node.metadata.updatedAt), { addSuffix: true })}</span>
          </div>
        </div>

        {/* Tags */}
        {node.metadata.tags.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-1">
              <Tag className="w-4 h-4" />
              Tags
            </h4>
            <div className="flex flex-wrap gap-1">
              {node.metadata.tags.map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 bg-background-surface text-text-muted text-xs rounded"
                >
                  #{tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Conversation Link */}
        {node.metadata.conversationId && (
          <div>
            <h4 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-1">
              <MessageCircle className="w-4 h-4" />
              Linked Conversation
            </h4>
            <button
              onClick={() => onNavigateToConversation?.(node.metadata.conversationId!)}
              className="flex items-center gap-2 text-sm text-accent-primary hover:underline"
            >
              <ExternalLink className="w-3 h-3" />
              View conversation
            </button>
          </div>
        )}

        {/* Source URL */}
        {node.metadata.sourceUrl && (
          <div>
            <h4 className="text-sm font-medium text-text-secondary mb-1">Source</h4>
            <a
              href={node.metadata.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-accent-primary hover:underline break-all"
            >
              {node.metadata.sourceUrl}
            </a>
          </div>
        )}

        {/* Connections */}
        {connections.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-text-secondary mb-2 flex items-center gap-1">
              <Link className="w-4 h-4" />
              Connections ({connections.length})
            </h4>
            <div className="space-y-2">
              {connections.map(({ edge, otherNode, direction }) => (
                <Card key={edge.id} className="p-2">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-text-muted">
                      {direction === 'outgoing' ? '→' : '←'}
                    </span>
                    <span className="text-text-muted text-xs">{edge.type}</span>
                    {edge.label && (
                      <span className="text-text-muted text-xs italic">({edge.label})</span>
                    )}
                  </div>
                  <div className="text-sm text-text-primary font-medium">
                    {otherNode?.label || 'Unknown'}
                  </div>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Edit button */}
        <button
          onClick={onEdit}
          className="w-full py-2 px-4 bg-accent-primary text-white rounded-lg font-medium hover:bg-accent-primary/90 transition-colors"
        >
          Edit Node
        </button>
      </div>
    </div>
  );
}
