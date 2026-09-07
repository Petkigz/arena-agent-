import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '../../types';
import type { WebSocketEvent, WebSocketEventHandler } from '../../services/websocket';
import { ChatPage } from '../../app/routes/ChatPage';
import { useConversationSync } from '../../hooks/useConversationSync';
import { useConversationStore } from '../../stores/conversationStore';

const { listeners, transport } = vi.hoisted(() => ({
  listeners: new Set<WebSocketEventHandler>(),
  transport: {
    status: 'connected', isConnected: true,
    subscribe: vi.fn(), onStatusChange: vi.fn(() => () => {}),
    joinConversation: vi.fn(), requestConversationHistory: vi.fn(), requestConversationList: vi.fn(),
  },
}));
vi.mock('../../services/websocket', () => ({ webSocketService: transport }));
vi.mock('../../components/chat', () => ({
  MessageBubble: ({ message }: { message: Message }) => <div>{message.content}</div>,
  ChatInput: () => null, ChatHeader: () => null, ConversationShareMenu: () => null,
  VirtualMessageList: () => null,
}));
vi.mock('../../components/beanie', () => ({ BeanieOrbPanel: () => null, ListeningIndicator: () => null }));
vi.mock('../../components/presence', () => ({ ReactiveBeanieOrb: () => null }));
vi.mock('../../components/ui', () => ({ EmptyState: () => null }));

function Harness() { useConversationSync(); return <ChatPage />; }
function emit(event: WebSocketEvent) { [...listeners].forEach((listener) => listener(event)); }
const currentMessages = () => useConversationStore.getState().currentConversation!.messages;

beforeEach(() => {
  listeners.clear();
  transport.subscribe.mockImplementation((handler: WebSocketEventHandler) => {
    listeners.add(handler);
    return () => listeners.delete(handler);
  });
  Element.prototype.scrollIntoView = vi.fn();
  const conversations = ['chat-a', 'chat-b'].map((id) => ({
    id, title: id, messages: [], createdAt: '2026-09-07', updatedAt: '2026-09-07',
  }));
  useConversationStore.setState({ conversations, currentConversation: conversations[0] });
});
afterEach(cleanup);

describe('chat trace transport integration', () => {
  it('handles metadata and back-to-back tokens before React re-renders without duplicate bubbles', () => {
    render(<Harness />);
    act(() => {
      emit({ type: 'cognitive_metadata', data: { conversation_id: 'chat-a', message_id: 'reply-a', trace_id: 'trace-a' } });
      emit({ type: 'message_token', data: { conversation_id: 'chat-a', message_id: 'reply-a', token: 'First ', done: false } });
      emit({ type: 'message_token', data: { conversation_id: 'chat-a', message_id: 'reply-a', token: 'answer.', done: true } });
    });
    expect(currentMessages()).toHaveLength(1);
    expect(currentMessages()[0]).toMatchObject({ id: 'reply-a', traceId: 'trace-a', content: 'First answer.', status: 'complete' });
  });

  it('does not attach another room’s trace, tool steps or response tokens to the current chat', () => {
    render(<Harness />);
    act(() => {
      emit({ type: 'cognitive_metadata', data: { conversation_id: 'chat-b', message_id: 'reply-b', trace_id: 'trace-b' } });
      emit({ type: 'action_step', data: { conversation_id: 'chat-b', message_id: 'reply-b', id: 'step-b', description: 'Other room', status: 'complete' } });
      emit({ type: 'message_token', data: { conversation_id: 'chat-b', message_id: 'reply-b', token: 'Other reply', done: true } });
    });
    expect(currentMessages()).toHaveLength(0);
    const other = useConversationStore.getState().conversations.find((item) => item.id === 'chat-b');
    expect(other?.messages[0].traceId).toBe('trace-b');
  });

  it('preserves the exact trace when full history arrives before the last streamed token', () => {
    render(<Harness />);
    act(() => {
      emit({ type: 'cognitive_metadata', data: { conversation_id: 'chat-a', message_id: 'reply-a', trace_id: 'trace-a' } });
      emit({ type: 'conversation_history', data: { conversation_id: 'chat-a', messages: [{
        message_id: 'reply-a', trace_id: 'trace-a', role: 'assistant', content: 'Complete answer.', created_at: '2026-09-07T10:00:00Z',
      }] } });
      emit({ type: 'message_token', data: { conversation_id: 'chat-a', message_id: 'reply-a', token: 'answer.', done: true } });
    });
    expect(currentMessages()).toHaveLength(1);
    expect(currentMessages()[0]).toMatchObject({ traceId: 'trace-a', content: 'Complete answer.', timestamp: '2026-09-07T10:00:00Z' });
  });
});
