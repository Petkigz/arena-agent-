import { beforeEach, describe, expect, it } from 'vitest';
import { useConversationStore } from '../../stores/conversationStore';
import type { Conversation } from '../../types';

function conversation(id: string): Conversation {
  return { id, title: id, messages: [], createdAt: '2026-09-07', updatedAt: '2026-09-07' };
}

beforeEach(() => {
  const first = conversation('chat-a');
  useConversationStore.setState({ conversations: [first, conversation('chat-b')], currentConversation: first });
});

describe('response trace binding', () => {
  it('creates one exact streaming placeholder before tokens arrive', () => {
    const store = useConversationStore.getState();
    store.bindResponseTrace('chat-a', 'reply-a', 'trace-a');
    store.bindResponseTrace('chat-a', 'reply-a', 'trace-a');
    expect(useConversationStore.getState().currentConversation?.messages).toEqual([
      expect.objectContaining({ id: 'reply-a', traceId: 'trace-a', content: '', status: 'streaming' }),
    ]);
  });

  it('updates an inactive room without attaching metadata to the open room', () => {
    useConversationStore.getState().bindResponseTrace('chat-b', 'reply-b', 'trace-b');
    const state = useConversationStore.getState();
    expect(state.currentConversation?.messages).toHaveLength(0);
    expect(state.conversations.find((item) => item.id === 'chat-b')?.messages[0].traceId).toBe('trace-b');
  });

  it('refuses unbound, conflicting, and user-message metadata', () => {
    const store = useConversationStore.getState();
    store.addMessage({ id: 'question', role: 'user', content: 'Hi', timestamp: '2026-09-07' });
    store.bindResponseTrace('chat-a', 'question', 'wrong');
    store.bindResponseTrace('missing-room', 'reply', 'trace');
    store.bindResponseTrace('chat-a', '', 'trace');
    store.bindResponseTrace('chat-a', 'reply', ' ');
    expect(useConversationStore.getState().currentConversation?.messages).toHaveLength(1);
    expect(useConversationStore.getState().currentConversation?.messages[0].traceId).toBeUndefined();
    store.bindResponseTrace('chat-a', 'reply', 'trace-right');
    store.bindResponseTrace('chat-a', 'reply', 'trace-wrong');
    expect(useConversationStore.getState().currentConversation?.messages[1].traceId).toBe('trace-right');
  });

  it('hydrates stable IDs, real timestamps and trace links without inventing legacy links', () => {
    useConversationStore.getState().hydrateMessages('chat-a', [
      { message_id: 1, role: 'user', content: 'Question', trace_id: 'invalid-user-link' },
      { message_id: 2, role: 'assistant', content: 'Old answer' },
      { message_id: 'reply-new', role: 'assistant', content: 'New answer', trace_id: 'trace-new', created_at: '2026-09-07T10:00:00Z' },
    ]);
    const messages = useConversationStore.getState().currentConversation!.messages;
    expect(messages.map((item) => item.id)).toEqual(['1', '2', 'reply-new']);
    expect(messages[0].traceId).toBeUndefined();
    expect(messages[1].traceId).toBeUndefined();
    expect(messages[2]).toMatchObject({ traceId: 'trace-new', timestamp: '2026-09-07T10:00:00Z', status: 'complete' });
    useConversationStore.getState().bindResponseTrace('chat-a', 'reply-new', 'trace-new');
    expect(useConversationStore.getState().currentConversation?.messages[2].content).toBe('New answer');
    expect(useConversationStore.getState().currentConversation?.messages[2].status).toBe('complete');
  });

  it('does not keep an unconfirmed local trace after authoritative history hydration', () => {
    const store = useConversationStore.getState();
    store.bindResponseTrace('chat-a', 'reply', 'local-trace');
    store.hydrateMessages('chat-a', [{ message_id: 'reply', role: 'assistant', content: 'Unlinked history' }]);
    expect(useConversationStore.getState().currentConversation?.messages[0].traceId).toBeUndefined();
  });
});
