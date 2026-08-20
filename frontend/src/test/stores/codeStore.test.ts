import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useCodeStore } from '../../stores/codeStore';
import * as api from '../../services/api';

// Mock the API service
vi.mock('../../services/api', () => ({
  executeCode: vi.fn(),
}));

describe('codeStore', () => {
  beforeEach(() => {
    useCodeStore.setState({
      sessions: [],
      currentSession: null,
      currentSnippet: null,
      isLoading: false,
      isExecuting: false,
      error: null,
    });
    vi.clearAllMocks();
  });

  describe('session management', () => {
    it('creates a new session', () => {
      const sessionId = useCodeStore.getState().createSession('Test Session');

      expect(sessionId).toBeDefined();
      expect(useCodeStore.getState().sessions).toHaveLength(1);
      expect(useCodeStore.getState().sessions[0].name).toBe('Test Session');
      expect(useCodeStore.getState().sessions[0].status).toBe('idle');
      expect(useCodeStore.getState().currentSession?.id).toBe(sessionId);
    });

    it('creates session with default name', () => {
      useCodeStore.getState().createSession();

      expect(useCodeStore.getState().sessions[0].name).toBe('Session 1');
    });

    it('deletes a session', () => {
      const sessionId = useCodeStore.getState().createSession('Test Session');

      useCodeStore.getState().deleteSession(sessionId);

      expect(useCodeStore.getState().sessions).toHaveLength(0);
      expect(useCodeStore.getState().currentSession).toBe(null);
    });

    it('sets current session', () => {
      const session1Id = useCodeStore.getState().createSession('Session 1');
      useCodeStore.getState().createSession('Session 2');

      const session1 = useCodeStore.getState().sessions.find((s) => s.id === session1Id);
      useCodeStore.getState().setCurrentSession(session1!);

      expect(useCodeStore.getState().currentSession?.id).toBe(session1Id);
    });
  });

  describe('snippet management', () => {
    beforeEach(() => {
      useCodeStore.getState().createSession('Test Session');
    });

    it('adds a snippet to current session', () => {
      const snippetId = useCodeStore.getState().addSnippet({
        title: 'Test Snippet',
        language: 'python',
        code: 'print("hello")',
      });

      expect(snippetId).toBeDefined();
      expect(useCodeStore.getState().currentSession?.snippets).toHaveLength(1);
      expect(useCodeStore.getState().currentSession?.snippets[0].title).toBe('Test Snippet');
      expect(useCodeStore.getState().currentSession?.snippets[0].language).toBe('python');
      expect(useCodeStore.getState().currentSnippet?.id).toBe(snippetId);
    });

    it('updates a snippet', () => {
      const snippetId = useCodeStore.getState().addSnippet({
        title: 'Test Snippet',
        language: 'python',
        code: 'print("hello")',
      });

      useCodeStore.getState().updateSnippet(snippetId, {
        code: 'print("world")',
        language: 'javascript',
      });

      const snippet = useCodeStore.getState().currentSession?.snippets.find((s) => s.id === snippetId);
      expect(snippet?.code).toBe('print("world")');
      expect(snippet?.language).toBe('javascript');
    });

    it('deletes a snippet', () => {
      const snippetId = useCodeStore.getState().addSnippet({
        title: 'Test Snippet',
        language: 'python',
        code: 'print("hello")',
      });

      useCodeStore.getState().deleteSnippet(snippetId);

      expect(useCodeStore.getState().currentSession?.snippets).toHaveLength(0);
      expect(useCodeStore.getState().currentSnippet).toBe(null);
    });

    it('sets current snippet', () => {
      const snippet1Id = useCodeStore.getState().addSnippet({
        title: 'Snippet 1',
        language: 'python',
        code: 'print("1")',
      });
      useCodeStore.getState().addSnippet({
        title: 'Snippet 2',
        language: 'javascript',
        code: 'console.log("2")',
      });

      const snippet1 = useCodeStore.getState().currentSession?.snippets.find((s) => s.id === snippet1Id);
      useCodeStore.getState().setCurrentSnippet(snippet1!);

      expect(useCodeStore.getState().currentSnippet?.id).toBe(snippet1Id);
    });
  });

  describe('executeSnippet', () => {
    beforeEach(() => {
      useCodeStore.getState().createSession('Test Session');
    });

    it('executes snippet successfully', async () => {
      const snippetId = useCodeStore.getState().addSnippet({
        title: 'Test Snippet',
        language: 'python',
        code: 'print("hello")',
      });

      const mockResponse = {
        success: true,
        data: {
          success: true,
          output: 'hello\n',
          executionTime: 150,
          timestamp: '2026-08-19T10:00:00Z',
        },
      };

      vi.mocked(api.executeCode).mockResolvedValue(mockResponse);

      const result = await useCodeStore.getState().executeSnippet(snippetId);

      expect(result).toBe(true);
      expect(api.executeCode).toHaveBeenCalledWith('print("hello")', 'python', 30);
      
      const snippet = useCodeStore.getState().currentSession?.snippets.find((s) => s.id === snippetId);
      expect(snippet?.executionResult?.success).toBe(true);
      expect(snippet?.executionResult?.output).toBe('hello\n');
    });

    it('handles execution failure', async () => {
      const snippetId = useCodeStore.getState().addSnippet({
        title: 'Test Snippet',
        language: 'python',
        code: 'print(undefined_var)',
      });

      const mockResponse = {
        success: true,
        data: {
          success: false,
          output: '',
          error: 'NameError: name "undefined_var" is not defined',
          executionTime: 50,
          timestamp: '2026-08-19T10:00:00Z',
        },
      };

      vi.mocked(api.executeCode).mockResolvedValue(mockResponse);

      const result = await useCodeStore.getState().executeSnippet(snippetId);

      expect(result).toBe(true); // API call succeeded
      const snippet = useCodeStore.getState().currentSession?.snippets.find((s) => s.id === snippetId);
      expect(snippet?.executionResult?.success).toBe(false);
      expect(snippet?.executionResult?.error).toContain('NameError');
    });

    it('handles API error', async () => {
      const snippetId = useCodeStore.getState().addSnippet({
        title: 'Test Snippet',
        language: 'python',
        code: 'print("test")',
      });

      vi.mocked(api.executeCode).mockResolvedValue({
        success: false,
        error: 'API error',
      });

      const result = await useCodeStore.getState().executeSnippet(snippetId);

      expect(result).toBe(false);
      expect(useCodeStore.getState().error).toBe('API error');
    });

    it('handles nonexistent snippet', async () => {
      const result = await useCodeStore.getState().executeSnippet('nonexistent-id');

      expect(result).toBe(false);
      expect(useCodeStore.getState().error).toBe('Snippet not found');
    });

    it('sets isExecuting during execution', async () => {
      const snippetId = useCodeStore.getState().addSnippet({
        title: 'Test Snippet',
        language: 'python',
        code: 'print("test")',
      });

      vi.mocked(api.executeCode).mockImplementation(() => {
        expect(useCodeStore.getState().isExecuting).toBe(true);
        return Promise.resolve({
          success: true,
          data: {
            success: true,
            output: 'test\n',
            executionTime: 100,
            timestamp: '2026-08-19T10:00:00Z',
          },
        });
      });

      await useCodeStore.getState().executeSnippet(snippetId);

      expect(useCodeStore.getState().isExecuting).toBe(false);
    });

    it('uses custom timeout', async () => {
      const snippetId = useCodeStore.getState().addSnippet({
        title: 'Test Snippet',
        language: 'python',
        code: 'import time; time.sleep(10)',
      });

      vi.mocked(api.executeCode).mockResolvedValue({
        success: true,
        data: {
          success: true,
          output: '',
          executionTime: 10000,
          timestamp: '2026-08-19T10:00:00Z',
        },
      });

      await useCodeStore.getState().executeSnippet(snippetId, 60);

      expect(api.executeCode).toHaveBeenCalledWith(expect.any(String), 'python', 60);
    });
  });

  describe('utility methods', () => {
    it('setLoading updates loading state', () => {
      useCodeStore.getState().setLoading(true);

      expect(useCodeStore.getState().isLoading).toBe(true);
    });

    it('setError updates error state', () => {
      useCodeStore.getState().setError('Test error');

      expect(useCodeStore.getState().error).toBe('Test error');
    });

    it('clearError clears error state', () => {
      useCodeStore.setState({ error: 'Test error' });

      useCodeStore.getState().clearError();

      expect(useCodeStore.getState().error).toBe(null);
    });
  });
});
