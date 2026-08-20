import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ChatInput } from '../../components/chat/ChatInput';
import { useMultiModalStore } from '../../stores/multiModalStore';

describe('ChatInput', () => {
  beforeEach(() => {
    useMultiModalStore.setState({ pendingAttachments: [] });
  });

  it('renders the message textarea with placeholder', () => {
    render(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByPlaceholderText('Message Arena...')).toBeTruthy();
  });

  it('disables the send button when the input is empty', () => {
    render(<ChatInput onSendMessage={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
  });

  it('enables send once text is typed', () => {
    render(<ChatInput onSendMessage={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText('Message Arena...'), {
      target: { value: 'hello' },
    });
    expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled();
  });

  it('submits on Enter (no shift) and clears the input', () => {
    const onSend = vi.fn();
    render(<ChatInput onSendMessage={onSend} />);
    const textarea = screen.getByPlaceholderText('Message Arena...');
    fireEvent.change(textarea, { target: { value: 'hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(onSend).toHaveBeenCalledWith('hello', undefined);
    expect(textarea).toHaveValue('');
  });

  it('does not submit on Shift+Enter (newline)', () => {
    const onSend = vi.fn();
    render(<ChatInput onSendMessage={onSend} />);
    const textarea = screen.getByPlaceholderText('Message Arena...');
    fireEvent.change(textarea, { target: { value: 'hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it('does not submit when disabled', () => {
    const onSend = vi.fn();
    render(<ChatInput onSendMessage={onSend} disabled />);
    fireEvent.change(screen.getByPlaceholderText('Message Arena...'), {
      target: { value: 'hello' },
    });
    fireEvent.keyDown(screen.getByPlaceholderText('Message Arena...'), {
      key: 'Enter',
      shiftKey: false,
    });
    expect(onSend).not.toHaveBeenCalled();
  });

  it('toggles voice: start when not listening, stop when listening', () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    const { rerender } = render(
      <ChatInput onSendMessage={vi.fn()} onVoiceStart={onStart} onVoiceStop={onStop} isListening={false} />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Start voice input' }));
    expect(onStart).toHaveBeenCalled();

    rerender(
      <ChatInput onSendMessage={vi.fn()} onVoiceStart={onStart} onVoiceStop={onStop} isListening />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice input' }));
    expect(onStop).toHaveBeenCalled();
  });
});
