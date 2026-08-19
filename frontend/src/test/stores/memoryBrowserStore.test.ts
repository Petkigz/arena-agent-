import { describe, it, expect, beforeEach } from 'vitest';
import { useMemoryBrowserStore, type Memory } from '../../stores/memoryBrowserStore';

function makeMemory(overrides: Partial<Memory> = {}): Memory {
  const now = new Date().toISOString();
  return {
    id: `mem-${Date.now()}-${Math.random()}`,
    category: 'semantic',
    title: 'Test Memory',
    content: 'Test content for memory',
    metadata: {
      createdAt: now,
      updatedAt: now,
      importance: 5,
      tags: ['test'],
    },
    ...overrides,
  };
}

describe('memoryBrowserStore', () => {
  beforeEach(() => {
    useMemoryBrowserStore.setState({ memories: [] });
  });

  describe('CRUD', () => {
    it('adds a memory', () => {
      const memory = makeMemory({ id: 'm1', title: 'First Memory' });
      useMemoryBrowserStore.getState().addMemory(memory);

      expect(useMemoryBrowserStore.getState().memories).toHaveLength(1);
      expect(useMemoryBrowserStore.getState().memories[0].title).toBe('First Memory');
    });

    it('updates a memory', () => {
      useMemoryBrowserStore.getState().addMemory(makeMemory({ id: 'm1', title: 'Before' }));
      useMemoryBrowserStore.getState().updateMemory('m1', { title: 'After' });

      expect(useMemoryBrowserStore.getState().memories[0].title).toBe('After');
    });

    it('removes a memory', () => {
      useMemoryBrowserStore.getState().addMemory(makeMemory({ id: 'm1' }));
      useMemoryBrowserStore.getState().removeMemory('m1');

      expect(useMemoryBrowserStore.getState().memories).toHaveLength(0);
    });
  });

  describe('search and filter', () => {
    it('searches by title', () => {
      useMemoryBrowserStore.getState().addMemory(makeMemory({ id: 'm1', title: 'TypeScript tips' }));
      useMemoryBrowserStore.getState().addMemory(makeMemory({ id: 'm2', title: 'CSS tricks' }));

      const results = useMemoryBrowserStore.getState().searchMemories('TypeScript');
      expect(results).toHaveLength(1);
      expect(results[0].id).toBe('m1');
    });

    it('searches by content', () => {
      useMemoryBrowserStore.getState().addMemory(
        makeMemory({ id: 'm1', title: 'A', content: 'Learning about React hooks' })
      );
      useMemoryBrowserStore.getState().addMemory(
        makeMemory({ id: 'm2', title: 'B', content: 'CSS grid layout' })
      );

      const results = useMemoryBrowserStore.getState().searchMemories('hooks');
      expect(results).toHaveLength(1);
    });

    it('searches by tags', () => {
      useMemoryBrowserStore.getState().addMemory(
        makeMemory({ id: 'm1', metadata: { createdAt: '', updatedAt: '', importance: 5, tags: ['programming'] } })
      );
      useMemoryBrowserStore.getState().addMemory(
        makeMemory({ id: 'm2', metadata: { createdAt: '', updatedAt: '', importance: 5, tags: ['design'] } })
      );

      const results = useMemoryBrowserStore.getState().searchMemories('programming');
      expect(results).toHaveLength(1);
    });

    it('gets memories by category', () => {
      useMemoryBrowserStore.getState().addMemory(makeMemory({ id: 'm1', category: 'episodic' }));
      useMemoryBrowserStore.getState().addMemory(makeMemory({ id: 'm2', category: 'semantic' }));
      useMemoryBrowserStore.getState().addMemory(makeMemory({ id: 'm3', category: 'episodic' }));

      const episodic = useMemoryBrowserStore.getState().getMemoriesByCategory('episodic');
      expect(episodic).toHaveLength(2);
    });

    it('gets memories by importance', () => {
      useMemoryBrowserStore.getState().addMemory(
        makeMemory({ id: 'm1', metadata: { createdAt: '', updatedAt: '', importance: 3, tags: [] } })
      );
      useMemoryBrowserStore.getState().addMemory(
        makeMemory({ id: 'm2', metadata: { createdAt: '', updatedAt: '', importance: 8, tags: [] } })
      );

      const important = useMemoryBrowserStore.getState().getMemoriesByImportance(5);
      expect(important).toHaveLength(1);
      expect(important[0].id).toBe('m2');
    });

    it('gets memories by date range', () => {
      useMemoryBrowserStore.getState().addMemory(
        makeMemory({
          id: 'm1',
          metadata: { createdAt: '2026-01-01T00:00:00Z', updatedAt: '', importance: 5, tags: [] },
        })
      );
      useMemoryBrowserStore.getState().addMemory(
        makeMemory({
          id: 'm2',
          metadata: { createdAt: '2026-06-15T00:00:00Z', updatedAt: '', importance: 5, tags: [] },
        })
      );

      const results = useMemoryBrowserStore.getState().getMemoriesByDateRange(
        '2026-06-01',
        '2026-12-31'
      );
      expect(results).toHaveLength(1);
      expect(results[0].id).toBe('m2');
    });
  });

  describe('bulk operations', () => {
    it('exports and imports memories', () => {
      useMemoryBrowserStore.getState().addMemory(makeMemory({ id: 'm1' }));
      useMemoryBrowserStore.getState().addMemory(makeMemory({ id: 'm2' }));

      const exported = useMemoryBrowserStore.getState().exportMemories();
      expect(exported).toHaveLength(2);

      useMemoryBrowserStore.getState().clearMemories();
      expect(useMemoryBrowserStore.getState().memories).toHaveLength(0);

      useMemoryBrowserStore.getState().importMemories(exported);
      expect(useMemoryBrowserStore.getState().memories).toHaveLength(2);
    });
  });

  describe('conversation linking', () => {
    it('stores conversationId in metadata', () => {
      useMemoryBrowserStore.getState().addMemory(
        makeMemory({
          id: 'm1',
          metadata: {
            createdAt: '',
            updatedAt: '',
            importance: 5,
            tags: [],
            conversationId: 'conv-123',
          },
        })
      );

      const memory = useMemoryBrowserStore.getState().memories[0];
      expect(memory.metadata.conversationId).toBe('conv-123');
    });
  });
});
