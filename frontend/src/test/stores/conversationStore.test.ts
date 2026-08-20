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
});
