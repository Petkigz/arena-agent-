import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type NodeType = 'concept' | 'entity' | 'memory' | 'conversation' | 'file';
export type EdgeType = 'relates_to' | 'depends_on' | 'created_from' | 'references';

export interface NodeMetadata {
  createdAt: string;
  updatedAt: string;
  importance: number; // 1-10
  tags: string[];
  conversationId?: string;
  sourceUrl?: string;
  summary?: string;
}

export interface EdgeMetadata {
  createdAt: string;
  weight: number; // 1-10
  context?: string;
}

export interface KnowledgeNode {
  id: string;
  type: NodeType;
  label: string;
  description?: string;
  metadata: NodeMetadata;
}

export interface KnowledgeEdge {
  id: string;
  source: string; // node id
  target: string; // node id
  type: EdgeType;
  label?: string;
  metadata: EdgeMetadata;
}

interface KnowledgeGraphState {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  
  // Actions
  addNode: (node: KnowledgeNode) => void;
  updateNode: (id: string, updates: Partial<KnowledgeNode>) => void;
  removeNode: (id: string) => void;
  addEdge: (edge: KnowledgeEdge) => void;
  updateEdge: (id: string, updates: Partial<KnowledgeEdge>) => void;
  removeEdge: (id: string) => void;
  
  // Bulk operations
  importGraph: (nodes: KnowledgeNode[], edges: KnowledgeEdge[]) => void;
  exportGraph: () => { nodes: KnowledgeNode[]; edges: KnowledgeEdge[] };
  clearGraph: () => void;
  
  // Search and filter
  searchNodes: (query: string) => KnowledgeNode[];
  getNodesByType: (type: NodeType) => KnowledgeNode[];
  getConnectedNodes: (nodeId: string) => KnowledgeNode[];
}

export const useKnowledgeGraphStore = create<KnowledgeGraphState>()(
  persist(
    (set, get) => ({
      nodes: [],
      edges: [],
      
      addNode: (node) => set((state) => ({
        nodes: [...state.nodes, node],
      })),
      
      updateNode: (id, updates) => set((state) => ({
        nodes: state.nodes.map(n =>
          n.id === id ? { ...n, ...updates, metadata: { ...n.metadata, ...updates.metadata, updatedAt: new Date().toISOString() } } : n
        ),
      })),
      
      removeNode: (id) => set((state) => ({
        nodes: state.nodes.filter(n => n.id !== id),
        edges: state.edges.filter(e => e.source !== id && e.target !== id),
      })),
      
      addEdge: (edge) => set((state) => ({
        edges: [...state.edges, edge],
      })),
      
      updateEdge: (id, updates) => set((state) => ({
        edges: state.edges.map(e =>
          e.id === id ? { ...e, ...updates, metadata: { ...e.metadata, ...updates.metadata } } : e
        ),
      })),
      
      removeEdge: (id) => set((state) => ({
        edges: state.edges.filter(e => e.id !== id),
      })),
      
      importGraph: (nodes, edges) => set({ nodes, edges }),
      
      exportGraph: () => {
        const state = get();
        return { nodes: state.nodes, edges: state.edges };
      },
      
      clearGraph: () => set({ nodes: [], edges: [] }),
      
      searchNodes: (query) => {
        const state = get();
        const queryLower = query.toLowerCase();
        return state.nodes.filter(node =>
          node.label.toLowerCase().includes(queryLower) ||
          node.description?.toLowerCase().includes(queryLower) ||
          node.metadata.tags.some(tag => tag.toLowerCase().includes(queryLower))
        );
      },
      
      getNodesByType: (type) => {
        const state = get();
        return state.nodes.filter(n => n.type === type);
      },
      
      getConnectedNodes: (nodeId) => {
        const state = get();
        const connectedIds = new Set<string>();
        
        state.edges.forEach(edge => {
          if (edge.source === nodeId) connectedIds.add(edge.target);
          if (edge.target === nodeId) connectedIds.add(edge.source);
        });
        
        return state.nodes.filter(n => connectedIds.has(n.id));
      },
    }),
    {
      name: 'arena-knowledge-graph',
    }
  )
);
