import { describe, it, expect } from 'vitest';
import { exportGraphAsJSON, exportGraphAsGraphML, importGraphFromJSON, exportMemoriesAsJSON, importMemoriesFromJSON, exportConversationAsMarkdown } from '../../utils/graphExport';
import type { KnowledgeNode, KnowledgeEdge } from '../../stores/knowledgeGraphStore';
import type { Memory } from '../../stores/memoryBrowserStore';
import type { Conversation } from '../../types';

describe('graphExport', () => {
  const sampleNodes: KnowledgeNode[] = [
    {
      id: 'n1',
      type: 'concept',
      label: 'TypeScript',
      description: 'A typed superset of JavaScript',
      metadata: {
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-02T00:00:00Z',
        importance: 8,
        tags: ['programming', 'typescript'],
      },
    },
    {
      id: 'n2',
      type: 'entity',
      label: 'React',
      metadata: {
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
        importance: 9,
        tags: ['framework'],
      },
    },
  ];

  const sampleEdges: KnowledgeEdge[] = [
    {
      id: 'e1',
      source: 'n1',
      target: 'n2',
      type: 'relates_to',
      label: 'used with',
      metadata: {
        createdAt: '2026-01-01T00:00:00Z',
        weight: 7,
      },
    },
  ];

  describe('exportGraphAsJSON', () => {
    it('exports valid JSON', () => {
      const json = exportGraphAsJSON(sampleNodes, sampleEdges);
      const parsed = JSON.parse(json);

      expect(parsed.nodes).toHaveLength(2);
      expect(parsed.edges).toHaveLength(1);
      expect(parsed.nodes[0].label).toBe('TypeScript');
    });
  });

  describe('exportGraphAsGraphML', () => {
    it('exports valid GraphML XML', () => {
      const graphml = exportGraphAsGraphML(sampleNodes, sampleEdges);

      expect(graphml).toContain('<?xml version="1.0"');
      expect(graphml).toContain('<graphml');
      expect(graphml).toContain('<node id="n1"');
      expect(graphml).toContain('<node id="n2"');
      expect(graphml).toContain('<edge id="e1"');
      expect(graphml).toContain('source="n1"');
      expect(graphml).toContain('target="n2"');
      expect(graphml).toContain('TypeScript');
      expect(graphml).toContain('used with');
    });

    it('escapes XML special characters', () => {
      const nodesWithSpecialChars: KnowledgeNode[] = [
        {
          id: 'n1',
          type: 'concept',
          label: 'A & B <C>',
          metadata: {
            createdAt: '',
            updatedAt: '',
            importance: 5,
            tags: [],
          },
        },
      ];

      const graphml = exportGraphAsGraphML(nodesWithSpecialChars, []);
      expect(graphml).toContain('A &amp; B &lt;C&gt;');
    });
  });

  describe('importGraphFromJSON', () => {
    it('imports valid JSON', () => {
      const json = JSON.stringify({ nodes: sampleNodes, edges: sampleEdges });
      const result = importGraphFromJSON(json);

      expect(result.nodes).toHaveLength(2);
      expect(result.edges).toHaveLength(1);
    });

    it('throws on invalid JSON', () => {
      expect(() => importGraphFromJSON('{"bad": true}')).toThrow('Invalid graph JSON format');
    });

    it('round-trips correctly', () => {
      const json = exportGraphAsJSON(sampleNodes, sampleEdges);
      const result = importGraphFromJSON(json);

      expect(result.nodes).toEqual(sampleNodes);
      expect(result.edges).toEqual(sampleEdges);
    });
  });

  describe('memory export/import', () => {
    const sampleMemories: Memory[] = [
      {
        id: 'm1',
        category: 'semantic',
        title: 'Test',
        content: 'Content',
        metadata: {
          createdAt: '2026-01-01T00:00:00Z',
          updatedAt: '2026-01-01T00:00:00Z',
          importance: 5,
          tags: ['test'],
        },
      },
    ];

    it('exports memories as JSON', () => {
      const json = exportMemoriesAsJSON(sampleMemories);
      const parsed = JSON.parse(json);
      expect(parsed).toHaveLength(1);
      expect(parsed[0].title).toBe('Test');
    });

    it('imports memories from JSON', () => {
      const json = JSON.stringify(sampleMemories);
      const result = importMemoriesFromJSON(json);
      expect(result).toHaveLength(1);
    });

    it('throws on non-array JSON', () => {
      expect(() => importMemoriesFromJSON('{"bad": true}')).toThrow('Invalid memories JSON format');
    });
  });

  describe('exportConversationAsMarkdown', () => {
    it('exports a conversation as Markdown', () => {
      const conversation: Conversation = {
        id: 'conv-1',
        title: 'Test Conversation',
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
        messages: [
          {
            id: 'msg-1',
            role: 'user',
            content: 'Hello!',
            timestamp: '2026-01-01T00:00:00Z',
          },
          {
            id: 'msg-2',
            role: 'assistant',
            content: 'Hi there!',
            timestamp: '2026-01-01T00:01:00Z',
          },
        ],
      };

      const md = exportConversationAsMarkdown(conversation);
      expect(md).toContain('# Test Conversation');
      expect(md).toContain('**You**');
      expect(md).toContain('**Arena**');
      expect(md).toContain('Hello!');
      expect(md).toContain('Hi there!');
    });
  });
});
