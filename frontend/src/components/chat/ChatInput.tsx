import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Send, Mic, X, Sparkles } from 'lucide-react';
import { Button } from '../ui/Button';
import { AttachmentButton } from '../ui/AttachmentButton';
import { useMultiModalStore, type Attachment } from '../../stores/multiModalStore';

interface ChatInputProps {
  onSendMessage: (content: string, attachments?: Attachment[]) => void;
  onVoiceStart?: () => void;
  onVoiceStop?: () => void;
  onOpenBeanie?: () => void;
  disabled?: boolean;
  isListening?: boolean;
}

export function ChatInput({ 
  onSendMessage, 
  onVoiceStart, 
  onVoiceStop,
  onOpenBeanie,
  disabled = false,
  isListening = false,
}: ChatInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { pendingAttachments, addPendingAttachment, clearPendingAttachments } = useMultiModalStore();

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [message]);

  const handleAttach = useCallback((files: File[]) => {
    files.forEach((file) => {
      const attachment: Attachment = {
        id: crypto.randomUUID(),
        type: file.type.startsWith('image/') ? 'image' : 'document',
        name: file.name,
        path: '', // Will be set after upload
        size: file.size,
        mimeType: file.type,
        uploadedAt: new Date().toISOString(),
        file, // Store the actual File object
      };

      // Generate preview for images
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => {
          attachment.preview = e.target?.result as string;
          addPendingAttachment(attachment);
        };
        reader.readAsDataURL(file);
      } else {
        addPendingAttachment(attachment);
      }
    });
  }, [addPendingAttachment]);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const hasContent = message.trim() || pendingAttachments.length > 0;
    
    if (hasContent && !disabled) {
      onSendMessage(message.trim(), pendingAttachments.length > 0 ? pendingAttachments : undefined);
      setMessage('');
      clearPendingAttachments();
      
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  }, [message, pendingAttachments, disabled, onSendMessage, clearPendingAttachments]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }, [handleSubmit]);

  const handleVoiceToggle = useCallback(() => {
    if (isListening) {
      onVoiceStop?.();
    } else {
      onVoiceStart?.();
    }
  }, [isListening, onVoiceStart, onVoiceStop]);

  // Memoize send button disabled state
  const isSendDisabled = useMemo(() => {
    return (!message.trim() && pendingAttachments.length === 0) || disabled;
  }, [message, pendingAttachments, disabled]);

  return (
    <form onSubmit={handleSubmit} className="border-t border-background-surface bg-background-primary p-4" data-tutorial="chat-input" role="form" aria-label="Message input">
      <div className="max-w-4xl mx-auto">
        {/* Pending attachments preview */}
        {pendingAttachments.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2" role="list" aria-label="Attached files">
            {pendingAttachments.map((attachment) => (
              <div
                key={attachment.id}
                className="relative group flex items-center gap-2 px-3 py-2 bg-background-secondary rounded-lg border border-background-surface" role="listitem"
              >
                {attachment.preview ? (
                  <img
                    src={attachment.preview}
                    alt={attachment.name}
                    className="w-8 h-8 object-cover rounded"
                  />
                ) : (
                  <div className="w-8 h-8 bg-background-surface rounded flex items-center justify-center">
                    <span className="text-xs text-text-muted">
                      {attachment.name.split('.').pop()?.toUpperCase()}
                    </span>
                  </div>
                )}
                <span className="text-sm text-text-secondary max-w-[150px] truncate">
                  {attachment.name}
                </span>
                <button
                  type="button"
                  onClick={() => useMultiModalStore.getState().removePendingAttachment(attachment.id)}
                  className="p-0.5 hover:bg-background-surface rounded opacity-0 group-hover:opacity-100 transition-opacity"
                  aria-label={`Remove ${attachment.name}`}
                >
                  <X className="w-3 h-3 text-text-muted" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Input row */}
        <div className="flex items-end gap-2">
          {/* Attach button */}
          <AttachmentButton onAttach={handleAttach} disabled={disabled} />

          {/* Message input */}
          <div className="flex-1 relative">
            <label htmlFor="message-input" className="sr-only">Message</label>
            <textarea
              id="message-input"
              ref={textareaRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Arena..."
              disabled={disabled}
              rows={1}
              aria-label="Type your message"
              className="w-full px-4 py-2.5 bg-background-secondary text-text-primary rounded-2xl border border-background-surface focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none placeholder-text-muted disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ maxHeight: '200px' }}
            />
          </div>

          {/* Beanie button — opens the floating orb panel */}
          {onOpenBeanie && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={disabled}
              onClick={onOpenBeanie}
              className="flex-shrink-0"
              aria-label="Open Beanie"
              title="Beanie"
            >
              <Sparkles className="w-5 h-5" aria-hidden="true" />
            </Button>
          )}

          {/* Voice button */}
          {onVoiceStart && (
            <Button
              type="button"
              variant={isListening ? 'danger' : 'ghost'}
              size="sm"
              disabled={disabled}
              onClick={handleVoiceToggle}
              className="flex-shrink-0"
              aria-label={isListening ? 'Stop voice input' : 'Start voice input'}
              aria-pressed={isListening}
            >
              <Mic className={`w-5 h-5 ${isListening ? 'animate-pulse' : ''}`} aria-hidden="true" />
            </Button>
          )}

          {/* Send button */}
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={isSendDisabled}
            className="flex-shrink-0"
            aria-label="Send message"
          >
            <Send className="w-5 h-5" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </form>
  );
}
