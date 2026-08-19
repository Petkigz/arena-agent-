import { useState, useRef, useEffect } from 'react';
import { Send, Mic, X } from 'lucide-react';
import { Button } from '../ui/Button';
import { AttachmentButton } from '../ui/AttachmentButton';
import { useMultiModalStore, type Attachment } from '../../stores/multiModalStore';

interface ChatInputProps {
  onSendMessage: (content: string, attachments?: Attachment[]) => void;
  onVoiceStart?: () => void;
  onVoiceStop?: () => void;
  disabled?: boolean;
  isListening?: boolean;
}

export function ChatInput({ 
  onSendMessage, 
  onVoiceStart, 
  onVoiceStop,
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

  const handleAttach = (files: File[]) => {
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
  };

  const handleSubmit = (e: React.FormEvent) => {
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
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleVoiceToggle = () => {
    if (isListening) {
      onVoiceStop?.();
    } else {
      onVoiceStart?.();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="border-t border-slate-700 bg-slate-900 p-4" data-tutorial="chat-input">
      <div className="max-w-4xl mx-auto">
        {/* Pending attachments preview */}
        {pendingAttachments.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {pendingAttachments.map((attachment) => (
              <div
                key={attachment.id}
                className="relative group flex items-center gap-2 px-3 py-2 bg-slate-800 rounded-lg border border-slate-700"
              >
                {attachment.preview ? (
                  <img
                    src={attachment.preview}
                    alt={attachment.name}
                    className="w-8 h-8 object-cover rounded"
                  />
                ) : (
                  <div className="w-8 h-8 bg-slate-700 rounded flex items-center justify-center">
                    <span className="text-xs text-slate-400">
                      {attachment.name.split('.').pop()?.toUpperCase()}
                    </span>
                  </div>
                )}
                <span className="text-sm text-slate-300 max-w-[150px] truncate">
                  {attachment.name}
                </span>
                <button
                  type="button"
                  onClick={() => useMultiModalStore.getState().removePendingAttachment(attachment.id)}
                  className="p-0.5 hover:bg-slate-700 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="w-3 h-3 text-slate-400" />
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
            <textarea
              ref={textareaRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Arena..."
              disabled={disabled}
              rows={1}
              className="w-full px-4 py-2.5 bg-slate-800 text-slate-100 rounded-2xl border border-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none placeholder-slate-500 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ maxHeight: '200px' }}
            />
          </div>

          {/* Voice button */}
          {onVoiceStart && (
            <Button
              type="button"
              variant={isListening ? 'danger' : 'ghost'}
              size="sm"
              disabled={disabled}
              onClick={handleVoiceToggle}
              className="flex-shrink-0"
            >
              <Mic className={`w-5 h-5 ${isListening ? 'animate-pulse' : ''}`} />
            </Button>
          )}

          {/* Send button */}
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={(!message.trim() && pendingAttachments.length === 0) || disabled}
            className="flex-shrink-0"
          >
            <Send className="w-5 h-5" />
          </Button>
        </div>
      </div>
    </form>
  );
}
