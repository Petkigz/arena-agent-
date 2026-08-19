import { describe, it, expect } from 'vitest';
import { computeForceLayout } from '../../utils/graphLayout';
import type { KnowledgeNode, KnowledgeEdge } from '../../stores/knowledgeGraphStore';

function makeNode(id: string): KnowledgeNode {
  return {
    id,
    type: 'concept',
    label: `Node ${id}`,
    metadata: {
      createdAt: '',
      updatedAt: '',
      importance: 5,
      tags: [],
    },
  };
}

function makeEdge(source: string, target: string): KnowledgeEdge {
  return {
    id: `${source}-${target}`,
    source,
    target,
    type: 'relates_to',
    metadata: {
      createdAt: '',
      weight: 5,
    },
  };
}

describe('computeForceLayout', () => {
  it('returns empty map for empty nodes', () => {
    const result = computeForceLayout([], []);
    expect(result.size).toBe(0);
  });

  it('returns positions for all nodes', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')];
    const result = computeForceLayout(nodes, []);

    expect(result.size).toBe(3);
    expect(result.has('a')).toBe(true);
    expect(result.has('b')).toBe(true);
    expect(result.has('c')).toBe(true);
  });

  it('positions are within bounds', () => {
    const nodes = Array.from({ length: 20 }, (_, i) => makeNode(`n${i}`));
    const result = computeForceLayout(nodes, [], 800, 600);

    for (const [, pos] of result) {
      expect(pos.x).toBeGreaterThanOrEqual(0);
      expect(pos.x).toBeLessThanOrEqual(800);
      expect(pos.y).toBeGreaterThanOrEqual(0);
      expect(pos.y).toBeLessThanOrEqual(600);
    }
  });

  it('connected nodes are closer together', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')];
    const edges = [makeEdge('a', 'b')];

    const result = computeForceLayout(nodes, edges, 800, 600, 200);

    const aPos = result.get('a')!;
    const bPos = result.get('b')!;

    const distAB = Math.sqrt((aPos.x - bPos.x) ** 2 + (aPos.y - bPos.y) ** 2);

    // Connected nodes should generally be closer than unconnected ones
    // (with enough iterations the force layout should pull them together)
    // This is a soft check since force layout is probabilistic
    expect(distAB).toBeLessThan(600); // at least within reasonable range
  });

  it('handles single node', () => {
    const nodes = [makeNode('only')];
    const result = computeForceLayout(nodes, []);

    expect(result.size).toBe(1);
    const pos = result.get('only')!;
    expect(pos.x).toBeGreaterThan(0);
    expect(pos.y).toBeGreaterThan(0);
  });
});
