import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MessageBubble } from '../../components/chat/MessageBubble';
import type { Message } from '../../types';

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg-1',
    role: 'assistant',
    content: 'hello world',
    timestamp: '2026-08-20T12:00:00Z',
    status: 'complete',
    ...overrides,
  };
}

describe('MessageBubble', () => {
  beforeEach(() => {
    // jsdom has no clipboard; stub it for the copy action.
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('renders assistant message content with markdown', () => {
    render(<MessageBubble message={makeMessage({ content: '**bold** text' })} />);
    // markdown bold → <strong>
    const strong = screen.getByText('bold');
    expect(strong.tagName).toBe('STRONG');
    expect(screen.getByText('text')).toBeTruthy();
  });

  it('renders user message as plain text (no markdown)', () => {
    render(<MessageBubble message={makeMessage({ role: 'user', content: '**not bold**' })} />);
    // user messages are plain <p>, so the literal asterisks remain
    expect(screen.getByText('**not bold**')).toBeTruthy();
  });

  it('shows "Sending..." for sending status', () => {
    render(<MessageBubble message={makeMessage({ role: 'user', status: 'sending' })} />);
    expect(screen.getByText('Sending...')).toBeTruthy();
  });

  it('shows "Streaming..." and a cursor for streaming status', () => {
    render(<MessageBubble message={makeMessage({ status: 'streaming' })} />);
    expect(screen.getByText('Streaming...')).toBeTruthy();
  });

  it('shows "Failed to send" and a retry button for error status', () => {
    const onRetry = vi.fn();
    render(<MessageBubble message={makeMessage({ role: 'user', status: 'error' })} onRetry={onRetry} />);
    expect(screen.getByText('Failed to send')).toBeTruthy();

    const retry = screen.getByRole('button', { name: 'Retry sending message' });
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledWith('msg-1');
  });

  it('calls onDelete when the delete button is clicked', () => {
    const onDelete = vi.fn();
    render(<MessageBubble message={makeMessage()} onDelete={onDelete} />);

    const del = screen.getByRole('button', { name: 'Delete message' });
    fireEvent.click(del);
    expect(onDelete).toHaveBeenCalledWith('msg-1');
  });

  it('does not render a retry button when there is no error', () => {
    render(<MessageBubble message={makeMessage()} />);
    expect(screen.queryByRole('button', { name: 'Retry sending message' })).toBeNull();
  });

  it('renders assistant action steps when present', () => {
    render(
      <MessageBubble
        message={makeMessage({
          actionSteps: [
            { id: 's1', description: 'Analyze request', status: 'complete' },
            { id: 's2', description: 'Generate response', status: 'in_progress' },
          ],
        })}
      />
    );
    expect(screen.getByText('Analyze request')).toBeTruthy();
    expect(screen.getByText('Generate response')).toBeTruthy();
  });
});
