import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { WebSocketEvent, WebSocketEventHandler } from '../../services/websocket';
import { ChatPage } from '../../app/routes/ChatPage';
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
  MessageBubble: () => null,
  ChatInput: () => null, ChatHeader: () => null, ConversationShareMenu: () => null,
  VirtualMessageList: () => null,
}));
vi.mock('../../components/beanie', () => ({ BeanieOrbPanel: () => null, ListeningIndicator: () => null }));
vi.mock('../../components/presence', () => ({ ReactiveBeanieOrb: () => null }));
vi.mock('../../components/ui', () => ({ EmptyState: () => null }));
vi.mock('../../services/ownerControl', () => ({
  executeAuthorizedAction: vi.fn(), revokeAuthorization: vi.fn(),
}));
vi.mock('../../services/api', () => ({}));

function emit(event: WebSocketEvent) { [...listeners].forEach((listener) => listener(event)); }

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

describe('in-chat correction notice', () => {
  it('surfaces an understood correction for the current conversation', () => {
    render(<ChatPage />);
    act(() => {
      emit({
        type: 'correction_recorded',
        data: {
          conversation_id: 'chat-a',
          correction_type: 'retrieval',
          signal: 'no,',
          target_trace_id: 'trace-a',
          candidate_id: 'train-1',
          generalized: false,
          duplicate: false,
        },
      });
    });
    const notice = screen.getByRole('status');
    expect(notice.textContent).toContain('correction (retrieval)');
    expect(notice.textContent).toContain('pending your review');
  });

  it('stays silent for another conversation and for duplicate retries', () => {
    render(<ChatPage />);
    act(() => {
      emit({
        type: 'correction_recorded',
        data: {
          conversation_id: 'chat-b',
          correction_type: 'retrieval',
          signal: 'no,',
          target_trace_id: 'trace-b',
          candidate_id: 'train-2',
          generalized: false,
          duplicate: false,
        },
      });
      emit({
        type: 'correction_recorded',
        data: {
          conversation_id: 'chat-a',
          correction_type: 'retrieval',
          signal: 'no,',
          target_trace_id: 'trace-a',
          candidate_id: 'train-1',
          generalized: false,
          duplicate: true,
        },
      });
    });
    expect(screen.queryByRole('status')).toBeNull();
  });
});
