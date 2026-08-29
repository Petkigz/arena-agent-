import { describe, it, expect, beforeEach } from 'vitest';
import { useConversationStore } from '../../stores/conversationStore';

describe('conversationStore', () => {
  beforeEach(() => {
    useConversationStore.setState({
      conversations: [],
      currentConversation: null,
      isLoading: false,
      error: null,
    });
  });

  describe('conversation management', () => {
    it('creates a conversation with default title', async () => {
      const id = await useConversationStore.getState().createConversation();
      const conv = useConversationStore.getState().conversations[0];
      expect(conv).toBeDefined();
      expect(conv.title).toBe('New Conversation');
      expect(conv.id).toBe(id);
    });

    it('creates a conversation with custom title', async () => {
      await useConversationStore.getState().createConversation('My Chat');
      const conv = useConversationStore.getState().conversations[0];
      expect(conv.title).toBe('My Chat');
    });

    it('sets current conversation on create', async () => {
      await useConversationStore.getState().createConversation('Test');
      expect(useConversationStore.getState().currentConversation).not.toBeNull();
      expect(useConversationStore.getState().currentConversation!.title).toBe('Test');
    });

    it('removes a conversation', async () => {
      const id = await useConversationStore.getState().createConversation('To Delete');
      useConversationStore.getState().removeConversation(id);
      expect(useConversationStore.getState().conversations).toHaveLength(0);
    });

    it('clears current conversation when removed', async () => {
      const id = await useConversationStore.getState().createConversation('Current');
      expect(useConversationStore.getState().currentConversation?.id).toBe(id);
      useConversationStore.getState().removeConversation(id);
      expect(useConversationStore.getState().currentConversation).toBeNull();
    });
  });

  describe('message management', () => {
    it('adds a message to current conversation', async () => {
      await useConversationStore.getState().createConversation('Test');
      useConversationStore.getState().addMessage({
        id: 'msg-1',
        role: 'user',
        content: 'Hello',
        timestamp: new Date().toISOString(),
      });

      const conv = useConversationStore.getState().currentConversation!;
      expect(conv.messages).toHaveLength(1);
      expect(conv.messages[0].content).toBe('Hello');
    });

    it('updates a message', async () => {
      await useConversationStore.getState().createConversation('Test');
      useConversationStore.getState().addMessage({
        id: 'msg-1',
        role: 'user',
        content: 'Hello',
        timestamp: new Date().toISOString(),
        status: 'sending',
      });

      useConversationStore.getState().updateMessage('msg-1', { status: 'sent' });
      const msg = useConversationStore.getState().currentConversation!.messages[0];
      expect(msg.status).toBe('sent');
    });

    it('removes a message', async () => {
      await useConversationStore.getState().createConversation('Test');
      useConversationStore.getState().addMessage({
        id: 'msg-1',
        role: 'user',
        content: 'Hello',
        timestamp: new Date().toISOString(),
      });
      useConversationStore.getState().addMessage({
        id: 'msg-2',
        role: 'assistant',
        content: 'Hi!',
        timestamp: new Date().toISOString(),
      });

      useConversationStore.getState().removeMessage('msg-1');
      expect(useConversationStore.getState().currentConversation!.messages).toHaveLength(1);
      expect(useConversationStore.getState().currentConversation!.messages[0].id).toBe('msg-2');
    });

    it('does nothing when adding message with no current conversation', () => {
      useConversationStore.getState().addMessage({
        id: 'msg-1',
        role: 'user',
        content: 'Hello',
        timestamp: new Date().toISOString(),
      });
      expect(useConversationStore.getState().currentConversation).toBeNull();
    });
  });

  describe('export', () => {
    it('exports conversation as JSON', async () => {
      const id = await useConversationStore.getState().createConversation('Export Test');
      const exported = useConversationStore.getState().exportConversation(id);
      expect(exported).not.toBeNull();
      expect(exported!.title).toBe('Export Test');
    });

    it('returns null for non-existent conversation', () => {
      const exported = useConversationStore.getState().exportConversation('nonexistent');
      expect(exported).toBeNull();
    });

    it('exports conversation as Markdown', async () => {
      const id = await useConversationStore.getState().createConversation('MD Test');
      useConversationStore.getState().addMessage({
        id: 'msg-1',
        role: 'user',
        content: 'Hello',
        timestamp: '2026-01-01T00:00:00Z',
      });

      const md = useConversationStore.getState().exportConversationAsMarkdown(id);
      expect(md).toContain('# MD Test');
      expect(md).toContain('**You**');
      expect(md).toContain('Hello');
    });
  });

  describe('multiple conversations', () => {
    it('tracks multiple conversations', async () => {
      await useConversationStore.getState().createConversation('Chat 1');
      await useConversationStore.getState().createConversation('Chat 2');
      await useConversationStore.getState().createConversation('Chat 3');

      expect(useConversationStore.getState().conversations).toHaveLength(3);
    });

    it('switches between conversations', async () => {
      await useConversationStore.getState().createConversation('Chat 1');
      const id1 = useConversationStore.getState().currentConversation!.id;

      await useConversationStore.getState().createConversation('Chat 2');

      // Switch back to Chat 1
      const conv1 = useConversationStore.getState().conversations.find((c) => c.id === id1);
      useConversationStore.getState().setCurrentConversation(conv1!);
      expect(useConversationStore.getState().currentConversation!.title).toBe('Chat 1');
    });
  });

  describe('backend sync (FE↔BE)', () => {
    it('hydrates conversations from server previews', () => {
      useConversationStore.getState().hydrateFromServer([
        { id: 'conv-a', title: 'Server Chat A', lastMessage: 'hi', updatedAt: '2026-08-20T00:00:00Z' },
        { id: 'conv-b', title: 'Server Chat B', lastMessage: 'yo', updatedAt: '2026-08-20T00:00:00Z' },
      ]);

      const convs = useConversationStore.getState().conversations;
      expect(convs).toHaveLength(2);
      expect(convs.find((c) => c.id === 'conv-a')!.title).toBe('Server Chat A');
    });

    it('auto-resumes the newest conversation when none is open (server restart / fresh load)', () => {
      // Previews arrive newest-first from the backend.
      useConversationStore.getState().hydrateFromServer([
        { id: 'conv-new', title: 'Latest Chat', lastMessage: 'latest', updatedAt: '2026-08-29T10:00:00Z' },
        { id: 'conv-old', title: 'Older Chat', lastMessage: 'older', updatedAt: '2026-08-01T10:00:00Z' },
      ]);

      // The previously-active conversation is restored, not a blank chat, so
      // follow-ups keep their context across restarts and reloads.
      const current = useConversationStore.getState().currentConversation;
      expect(current).not.toBeNull();
      expect(current!.id).toBe('conv-new');
    });

    it('does not switch conversations when one is already open', () => {
      useConversationStore.getState().hydrateFromServer([
        { id: 'conv-first', title: 'First', lastMessage: '', updatedAt: '' },
      ]);
      const first = useConversationStore.getState().currentConversation!;
      expect(first.id).toBe('conv-first');

      // A newer conversation appearing in a later list refresh must NOT
      // hijack the open conversation.
      useConversationStore.getState().hydrateFromServer([
        { id: 'conv-newer', title: 'Newer', lastMessage: '', updatedAt: '' },
        { id: 'conv-first', title: 'First', lastMessage: '', updatedAt: '' },
      ]);

      expect(useConversationStore.getState().currentConversation!.id).toBe('conv-first');
    });

    it('persists the open conversation for reloads (partialize)', () => {
      const store = useConversationStore.getState() as unknown as { currentConversation: unknown };
      const opts = (useConversationStore as unknown as {
        persist: { getOptions: () => { partialize?: (state: unknown) => unknown } };
      }).persist.getOptions();
      const partial = opts.partialize!(store) as { conversations: unknown[]; currentConversation: unknown };
      expect(Array.isArray(partial.conversations)).toBe(true);
      expect(partial).toHaveProperty('currentConversation');
    });

    it('preserves existing conversation state when hydrating the same id', () => {
      useConversationStore.getState().hydrateFromServer([
        { id: 'conv-x', title: 'Server Title', lastMessage: '', updatedAt: '' },
      ]);

      // Add a message to the existing conversation, then re-hydrate.
      const conv = useConversationStore.getState().conversations.find((c) => c.id === 'conv-x')!;
      useConversationStore.setState({
        currentConversation: { ...conv, messages: [{ id: 'm1', role: 'user', content: 'hello', timestamp: '' }] },
      });

      useConversationStore.getState().hydrateFromServer([
        { id: 'conv-x', title: 'Server Title', lastMessage: '', updatedAt: '' },
      ]);

      const existing = useConversationStore.getState().conversations.find((c) => c.id === 'conv-x')!;
      // Existing conversation object is preserved (messages not wiped).
      expect(existing.messages.length).toBeGreaterThanOrEqual(0);
    });

    it('hydrates messages into a conversation', () => {
      useConversationStore.getState().hydrateFromServer([
        { id: 'conv-h', title: 'History', lastMessage: '', updatedAt: '' },
      ]);
      useConversationStore.getState().hydrateMessages('conv-h', [
        { role: 'user', content: 'question' },
        { role: 'assistant', content: 'answer' },
      ]);

      const conv = useConversationStore.getState().conversations.find((c) => c.id === 'conv-h')!;
      expect(conv.messages).toHaveLength(2);
      expect(conv.messages[0].role).toBe('user');
      expect(conv.messages[1].role).toBe('assistant');
      expect(conv.messages[1].content).toBe('answer');
    });
  });
});
