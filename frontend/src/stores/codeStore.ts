import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import * as api from '../services/api';

export interface CodeSnippet {
  id: string;
  title: string;
  language: string;
  code: string;
  createdAt: string;
  updatedAt: string;
  conversationId?: string;
  executionResult?: ExecutionResult;
}

export interface ExecutionResult {
  success: boolean;
  output: string;
  error?: string;
  executionTime: number; // ms
  timestamp: string;
}

export interface SandboxSession {
  id: string;
  name: string;
  status: 'idle' | 'running' | 'completed' | 'error';
  createdAt: string;
  snippets: CodeSnippet[];
}

interface CodeStoreState {
  sessions: SandboxSession[];
  currentSession: SandboxSession | null;
  currentSnippet: CodeSnippet | null;
  isLoading: boolean;
  isExecuting: boolean;
  error: string | null;

  // Session actions
  createSession: (name?: string) => string;
  deleteSession: (id: string) => void;
  setCurrentSession: (session: SandboxSession | null) => void;

  // Snippet actions
  addSnippet: (snippet: Omit<CodeSnippet, 'id' | 'createdAt' | 'updatedAt'>) => string;
  updateSnippet: (id: string, updates: Partial<CodeSnippet>) => void;
  deleteSnippet: (id: string) => void;
  setCurrentSnippet: (snippet: CodeSnippet | null) => void;
  executeSnippet: (snippetId: string, timeout?: number) => Promise<boolean>;

  // Utility
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
}

export const useCodeStore = create<CodeStoreState>()(
  persist(
    (set, get) => ({
      sessions: [],
      currentSession: null,
      currentSnippet: null,
      isLoading: false,
      isExecuting: false,
      error: null,

      createSession: (name) => {
        const session: SandboxSession = {
          id: crypto.randomUUID(),
          name: name || `Session ${get().sessions.length + 1}`,
          status: 'idle',
          createdAt: new Date().toISOString(),
          snippets: [],
        };

        set((state) => ({
          sessions: [session, ...state.sessions],
          currentSession: session,
        }));

        return session.id;
      },

      deleteSession: (id) =>
        set((state) => ({
          sessions: state.sessions.filter((s) => s.id !== id),
          currentSession: state.currentSession?.id === id ? null : state.currentSession,
        })),

      setCurrentSession: (session) => set({ currentSession: session }),

      addSnippet: (snippetData) => {
        const snippet: CodeSnippet = {
          ...snippetData,
          id: crypto.randomUUID(),
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };

        set((state) => {
          if (!state.currentSession) return state;

          const updatedSession = {
            ...state.currentSession,
            snippets: [snippet, ...state.currentSession.snippets],
          };

          return {
            currentSession: updatedSession,
            sessions: state.sessions.map((s) =>
              s.id === updatedSession.id ? updatedSession : s
            ),
            currentSnippet: snippet,
          };
        });

        return snippet.id;
      },

      updateSnippet: (id, updates) =>
        set((state) => {
          if (!state.currentSession) return state;

          const updatedSession = {
            ...state.currentSession,
            snippets: state.currentSession.snippets.map((s) =>
              s.id === id ? { ...s, ...updates, updatedAt: new Date().toISOString() } : s
            ),
          };

          return {
            currentSession: updatedSession,
            sessions: state.sessions.map((s) =>
              s.id === updatedSession.id ? updatedSession : s
            ),
            currentSnippet:
              state.currentSnippet?.id === id
                ? { ...state.currentSnippet, ...updates, updatedAt: new Date().toISOString() }
                : state.currentSnippet,
          };
        }),

      deleteSnippet: (id) =>
        set((state) => {
          if (!state.currentSession) return state;

          const updatedSession = {
            ...state.currentSession,
            snippets: state.currentSession.snippets.filter((s) => s.id !== id),
          };

          return {
            currentSession: updatedSession,
            sessions: state.sessions.map((s) =>
              s.id === updatedSession.id ? updatedSession : s
            ),
            currentSnippet: state.currentSnippet?.id === id ? null : state.currentSnippet,
          };
        }),

      setCurrentSnippet: (snippet) => set({ currentSnippet: snippet }),

      executeSnippet: async (snippetId, timeout = 30) => {
        const state = get();
        const snippet = state.currentSession?.snippets.find((s) => s.id === snippetId);
        
        if (!snippet) {
          set({ error: 'Snippet not found' });
          return false;
        }

        set({ isExecuting: true, error: null });

        const result = await api.executeCode(snippet.code, snippet.language, timeout);

        if (result.success && result.data) {
          set((state) => {
            if (!state.currentSession) return state;

            const updatedSession = {
              ...state.currentSession,
              snippets: state.currentSession.snippets.map((s) =>
                s.id === snippetId ? { ...s, executionResult: result.data! } : s
              ),
            };

            return {
              currentSession: updatedSession,
              sessions: state.sessions.map((s) =>
                s.id === updatedSession.id ? updatedSession : s
              ),
              isExecuting: false,
            };
          });
          return true;
        } else {
          set({ isExecuting: false, error: result.error || 'Execution failed' });
          return false;
        }
      },

      setLoading: (loading) => set({ isLoading: loading }),
      setError: (error) => set({ error }),
      clearError: () => set({ error: null }),
    }),
    {
      name: 'arena-code',
    }
  )
);
