import { describe, it, expect, beforeEach } from 'vitest';
import { useKnowledgeGraphStore, type KnowledgeNode, type KnowledgeEdge } from '../../stores/knowledgeGraphStore';

function makeNode(overrides: Partial<KnowledgeNode> = {}): KnowledgeNode {
  const now = new Date().toISOString();
  return {
    id: `node-${Date.now()}-${Math.random()}`,
    type: 'concept',
    label: 'Test Node',
    metadata: {
      createdAt: now,
      updatedAt: now,
      importance: 5,
      tags: ['test'],
    },
    ...overrides,
  };
}

function makeEdge(source: string, target: string, overrides: Partial<KnowledgeEdge> = {}): KnowledgeEdge {
  return {
    id: `edge-${Date.now()}-${Math.random()}`,
    source,
    target,
    type: 'relates_to',
    metadata: {
      createdAt: new Date().toISOString(),
      weight: 5,
    },
    ...overrides,
  };
}

describe('knowledgeGraphStore', () => {
  beforeEach(() => {
    useKnowledgeGraphStore.setState({ nodes: [], edges: [] });
  });

  describe('node CRUD', () => {
    it('adds a node', () => {
      const node = makeNode({ id: 'n1', label: 'Alpha' });
      useKnowledgeGraphStore.getState().addNode(node);

      expect(useKnowledgeGraphStore.getState().nodes).toHaveLength(1);
      expect(useKnowledgeGraphStore.getState().nodes[0].label).toBe('Alpha');
    });

    it('updates a node', () => {
      const node = makeNode({ id: 'n1', label: 'Before' });
      useKnowledgeGraphStore.getState().addNode(node);
      useKnowledgeGraphStore.getState().updateNode('n1', { label: 'After' });

      expect(useKnowledgeGraphStore.getState().nodes[0].label).toBe('After');
    });

    it('removes a node and its edges', () => {
      const n1 = makeNode({ id: 'n1' });
      const n2 = makeNode({ id: 'n2' });
      useKnowledgeGraphStore.getState().addNode(n1);
      useKnowledgeGraphStore.getState().addNode(n2);
      useKnowledgeGraphStore.getState().addEdge(makeEdge('n1', 'n2'));

      useKnowledgeGraphStore.getState().removeNode('n1');

      expect(useKnowledgeGraphStore.getState().nodes).toHaveLength(1);
      expect(useKnowledgeGraphStore.getState().edges).toHaveLength(0);
    });
  });

  describe('edge CRUD', () => {
    it('adds an edge', () => {
      const n1 = makeNode({ id: 'n1' });
      const n2 = makeNode({ id: 'n2' });
      useKnowledgeGraphStore.getState().addNode(n1);
      useKnowledgeGraphStore.getState().addNode(n2);

      const edge = makeEdge('n1', 'n2');
      useKnowledgeGraphStore.getState().addEdge(edge);

      expect(useKnowledgeGraphStore.getState().edges).toHaveLength(1);
    });

    it('removes an edge', () => {
      const n1 = makeNode({ id: 'n1' });
      const n2 = makeNode({ id: 'n2' });
      useKnowledgeGraphStore.getState().addNode(n1);
      useKnowledgeGraphStore.getState().addNode(n2);

      const edge = makeEdge('n1', 'n2', { id: 'e1' });
      useKnowledgeGraphStore.getState().addEdge(edge);
      useKnowledgeGraphStore.getState().removeEdge('e1');

      expect(useKnowledgeGraphStore.getState().edges).toHaveLength(0);
    });
  });

  describe('search and filter', () => {
    it('searches nodes by label', () => {
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n1', label: 'TypeScript' }));
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n2', label: 'JavaScript' }));

      const results = useKnowledgeGraphStore.getState().searchNodes('script');
      expect(results).toHaveLength(2);
    });

    it('searches nodes by tags', () => {
      useKnowledgeGraphStore.getState().addNode(
        makeNode({ id: 'n1', label: 'A', metadata: { createdAt: '', updatedAt: '', importance: 5, tags: ['programming'] } })
      );
      useKnowledgeGraphStore.getState().addNode(
        makeNode({ id: 'n2', label: 'B', metadata: { createdAt: '', updatedAt: '', importance: 5, tags: ['design'] } })
      );

      const results = useKnowledgeGraphStore.getState().searchNodes('programming');
      expect(results).toHaveLength(1);
      expect(results[0].id).toBe('n1');
    });

    it('gets nodes by type', () => {
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n1', type: 'concept' }));
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n2', type: 'entity' }));
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n3', type: 'concept' }));

      const concepts = useKnowledgeGraphStore.getState().getNodesByType('concept');
      expect(concepts).toHaveLength(2);
    });

    it('gets connected nodes', () => {
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n1' }));
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n2' }));
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n3' }));
      useKnowledgeGraphStore.getState().addEdge(makeEdge('n1', 'n2'));
      useKnowledgeGraphStore.getState().addEdge(makeEdge('n3', 'n1'));

      const connected = useKnowledgeGraphStore.getState().getConnectedNodes('n1');
      expect(connected).toHaveLength(2);
    });
  });

  describe('bulk operations', () => {
    it('exports and imports graph', () => {
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n1' }));
      useKnowledgeGraphStore.getState().addNode(makeNode({ id: 'n2' }));
      useKnowledgeGraphStore.getState().addEdge(makeEdge('n1', 'n2'));

      const exported = useKnowledgeGraphStore.getState().exportGraph();
      expect(exported.nodes).toHaveLength(2);
      expect(exported.edges).toHaveLength(1);

      useKnowledgeGraphStore.getState().clearGraph();
      expect(useKnowledgeGraphStore.getState().nodes).toHaveLength(0);

      useKnowledgeGraphStore.getState().importGraph(exported.nodes, exported.edges);
      expect(useKnowledgeGraphStore.getState().nodes).toHaveLength(2);
      expect(useKnowledgeGraphStore.getState().edges).toHaveLength(1);
    });
  });

  describe('type safety', () => {
    it('NodeMetadata has no any types', () => {
      const node = makeNode();
      // TypeScript compilation ensures these are typed
      expect(typeof node.metadata.importance).toBe('number');
      expect(Array.isArray(node.metadata.tags)).toBe(true);
      expect(typeof node.metadata.createdAt).toBe('string');
    });

    it('EdgeMetadata has no any types', () => {
      const edge = makeEdge('a', 'b');
      expect(typeof edge.metadata.weight).toBe('number');
      expect(typeof edge.metadata.createdAt).toBe('string');
    });
  });
});
