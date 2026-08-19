import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type MemoryCategory = 'episodic' | 'semantic' | 'procedural' | 'conversation';

export interface MemoryMetadata {
  createdAt: string;
  updatedAt: string;
  importance: number; // 1-10
  tags: string[];
  conversationId?: string;
  sourceType?: 'user' | 'system' | 'conversation';
  relatedMemoryIds?: string[];
}

export interface Memory {
  id: string;
  category: MemoryCategory;
  title: string;
  content: string;
  metadata: MemoryMetadata;
}

interface MemoryBrowserState {
  memories: Memory[];
  
  // Actions
  addMemory: (memory: Memory) => void;
  updateMemory: (id: string, updates: Partial<Memory>) => void;
  removeMemory: (id: string) => void;
  
  // Bulk operations
  importMemories: (memories: Memory[]) => void;
  exportMemories: () => Memory[];
  clearMemories: () => void;
  
  // Search and filter
  searchMemories: (query: string) => Memory[];
  getMemoriesByCategory: (category: MemoryCategory) => Memory[];
  getMemoriesByDateRange: (start: string, end: string) => Memory[];
  getMemoriesByImportance: (minImportance: number) => Memory[];
}

export const useMemoryBrowserStore = create<MemoryBrowserState>()(
  persist(
    (set, get) => ({
      memories: [],
      
      addMemory: (memory) => set((state) => ({
        memories: [...state.memories, memory],
      })),
      
      updateMemory: (id, updates) => set((state) => ({
        memories: state.memories.map(m =>
          m.id === id ? { ...m, ...updates, metadata: { ...m.metadata, ...updates.metadata, updatedAt: new Date().toISOString() } } : m
        ),
      })),
      
      removeMemory: (id) => set((state) => ({
        memories: state.memories.filter(m => m.id !== id),
      })),
      
      importMemories: (memories) => set({ memories }),
      
      exportMemories: () => {
        const state = get();
        return state.memories;
      },
      
      clearMemories: () => set({ memories: [] }),
      
      searchMemories: (query) => {
        const state = get();
        const queryLower = query.toLowerCase();
        return state.memories.filter(memory =>
          memory.title.toLowerCase().includes(queryLower) ||
          memory.content.toLowerCase().includes(queryLower) ||
          memory.metadata.tags.some(tag => tag.toLowerCase().includes(queryLower))
        );
      },
      
      getMemoriesByCategory: (category) => {
        const state = get();
        return state.memories.filter(m => m.category === category);
      },
      
      getMemoriesByDateRange: (start, end) => {
        const state = get();
        const startDate = new Date(start);
        const endDate = new Date(end);
        
        return state.memories.filter(memory => {
          const memoryDate = new Date(memory.metadata.createdAt);
          return memoryDate >= startDate && memoryDate <= endDate;
        });
      },
      
      getMemoriesByImportance: (minImportance) => {
        const state = get();
        return state.memories.filter(m => m.metadata.importance >= minImportance);
      },
    }),
    {
      name: 'arena-memory-browser',
    }
  )
);
