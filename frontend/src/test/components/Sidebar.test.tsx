import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from '../../components/layout/Sidebar';
import { useConversationStore } from '../../stores/conversationStore';
import { usePresenceStore } from '../../stores/presenceStore';
import type { Conversation } from '../../types';

vi.mock('../../services/websocket', () => ({
  webSocketService: {
    status: 'connected',
    onStatusChange: () => () => undefined,
  },
}));

function conv(id: string, title: string, updatedAt: string): Conversation {
  return { id, title, messages: [], createdAt: updatedAt, updatedAt } as Conversation;
}

const TODAY = new Date();
function iso(date: Date): string {
  return date.toISOString();
}
function daysAgo(days: number): string {
  return iso(new Date(TODAY.getTime() - days * 86_400_000));
}

function renderSidebar() {
  return render(
    <MemoryRouter initialEntries={['/chat']}>
      <Sidebar />
    </MemoryRouter>,
  );
}

describe('Sidebar — reference information architecture (21s)', () => {
  beforeEach(() => {
    useConversationStore.setState({
      conversations: [
        conv('c1', 'AI Agent Development', daysAgo(0)),
        conv('c2', 'Python Environment Issues', daysAgo(1)),
        conv('c3', 'Learning Roadmap', daysAgo(5)),
        conv('c4', 'Old idea', daysAgo(30)),
      ],
      currentConversation: null,
    } as never);
    usePresenceStore.setState({
      presence: { status: 'working', message: 'Planning the UI.' },
      quickActions: [],
    });
  });

  it('makes conversation history the primary navigation, grouped by recency', () => {
    renderSidebar();
    const history = screen.getByRole('region', { name: 'Conversation history' });
    expect(history).toBeTruthy();
    expect(history.getAttribute('data-tutorial')).toBe('conversation-list');

    expect(screen.getByText('Today')).toBeTruthy();
    expect(screen.getByText('Yesterday')).toBeTruthy();
    expect(screen.getByText('Previous 7 days')).toBeTruthy();
    expect(screen.getByText('Older')).toBeTruthy();

    expect(screen.getByText('AI Agent Development')).toBeTruthy();
    expect(screen.getByText('Python Environment Issues')).toBeTruthy();
  });

  it('shows the brand header and the Beanie presence card', () => {
    renderSidebar();
    expect(screen.getByText('Arena')).toBeTruthy();
    expect(screen.getByText('New Chat')).toBeTruthy();

    const card = screen.getByRole('status', { name: 'Beanie presence' });
    expect(card).toBeTruthy();
    expect(screen.getByText('Working')).toBeTruthy();
    expect(screen.getByText('Planning the UI.')).toBeTruthy();
  });

  it('keeps the tool nav below the history — history is the chat navigation', () => {
    renderSidebar();
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(nav).toBeTruthy();
    for (const tool of ['Pansophy', 'Images', 'Files', 'Code', 'Settings']) {
      expect(screen.getByText(tool)).toBeTruthy();
    }
    expect(screen.queryByText('Chats')).toBeNull();
  });

  it('offers an empty-state hint instead of an empty list', () => {
    useConversationStore.setState({ conversations: [], currentConversation: null } as never);
    renderSidebar();
    expect(screen.getByText(/No conversations yet/i)).toBeTruthy();
  });
});
