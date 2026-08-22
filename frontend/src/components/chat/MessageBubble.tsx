import { useState, memo, useCallback, useMemo, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion } from 'framer-motion';
import { User, RotateCcw, Trash2, Copy, Check } from 'lucide-react';
import { ActionSteps } from './ActionSteps';
import { ReasoningTrace } from './ReasoningTrace';
import { CodeChanges } from './CodeChanges';
import { AttachmentDisplay } from '../ui/AttachmentDisplay';
import { messageVariants } from '../animations/variants';
import { BeanieAvatar } from '../presence/BeanieAvatar';
import type { Message } from '../../types';

interface MessageBubbleProps {
  message: Message;
  onRetry?: (messageId: string) => void;
  onDelete?: (messageId: string) => void;
}

function MessageBubbleComponent({ message, onRetry, onDelete }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
  }, [message.content]);

  const handleRetry = useCallback(() => {
    onRetry?.(message.id);
  }, [onRetry, message.id]);

  const handleDelete = useCallback(() => {
    onDelete?.(message.id);
  }, [onDelete, message.id]);

  // Memoize timestamp formatting
  const formattedTime = useMemo(() => {
    return new Date(message.timestamp).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit'
    });
  }, [message.timestamp]);

  return (
    <motion.div
      variants={messageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      layout
      role="article"
      aria-label={`${isUser ? 'You' : 'Arena'} said at ${formattedTime}`}
      className={`group flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      {/* Avatar — the user keeps a simple glyph; the assistant is Beanie's orb */}
      <motion.div
        className="flex-shrink-0"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.1, type: 'spring', stiffness: 300 }}
      >
        {isUser ? (
          <div className="w-8 h-8 rounded-full flex items-center justify-center bg-blue-600">
            <User className="w-5 h-5 text-white" aria-hidden="true" />
          </div>
        ) : (
          <BeanieAvatar messageStatus={message.status} />
        )}
      </motion.div>

      {/* Message content */}
      <div className={`flex-1 max-w-[80%] ${isUser ? 'items-end' : ''}`}>
        {/* Message bubble */}
        <div className={`rounded-2xl px-4 py-2.5 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-background-secondary text-text-primary'
        }`}>
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
          ) : (
            <div className="text-sm leading-relaxed prose prose-invert prose-sm max-w-none
              prose-headings:text-text-primary prose-p:text-text-primary prose-a:text-blue-400
              prose-code:text-emerald-400 prose-code:bg-background-primary prose-code:px-1 prose-code:py-0.5 prose-code:rounded
              prose-pre:bg-background-primary prose-pre:border prose-pre:border-background-surface
              prose-strong:text-text-primary prose-li:text-text-primary">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
              {message.status === 'streaming' && (
                <span className="inline-block w-2 h-4 bg-text-muted animate-pulse ml-0.5" />
              )}
            </div>
          )}
        </div>

        {/* Attachments */}
        {message.attachments && message.attachments.length > 0 && (
          <AttachmentDisplay attachments={message.attachments} />
        )}

        {/* Metadata and actions */}
        <div className={`mt-1 flex items-center gap-2 text-xs text-text-muted ${
          isUser ? 'justify-end' : ''
        }`}>
          <span>{formattedTime}</span>
          {message.status === 'sending' && (
            <span className="text-blue-500">Sending...</span>
          )}
          {message.status === 'streaming' && (
            <span className="text-blue-400">Streaming...</span>
          )}
          {message.status === 'error' && (
            <span className="text-red-500">Failed to send</span>
          )}

          {/* Action buttons (visible on hover) */}
          <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
            <button
              onClick={handleCopy}
              className="p-1 hover:text-text-secondary transition-colors"
              aria-label={copied ? 'Copied' : 'Copy message'}
            >
              {copied ? <Check className="w-3 h-3 text-green-500" aria-hidden="true" /> : <Copy className="w-3 h-3" aria-hidden="true" />}
            </button>
            {message.status === 'error' && onRetry && (
              <button
                onClick={handleRetry}
                className="p-1 hover:text-blue-400 transition-colors"
                aria-label="Retry sending message"
              >
                <RotateCcw className="w-3 h-3" aria-hidden="true" />
              </button>
            )}
            {onDelete && (
              <button
                onClick={handleDelete}
                className="p-1 hover:text-red-400 transition-colors"
                aria-label="Delete message"
              >
                <Trash2 className="w-3 h-3" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>

        {/* Action steps (only for assistant messages) */}
        {!isUser && message.actionSteps && message.actionSteps.length > 0 && (
          <ActionSteps steps={message.actionSteps} />
        )}

        {/* Reasoning trace (only for assistant messages) */}
        {!isUser && message.reasoningTrace && (
          <ReasoningTrace trace={message.reasoningTrace} />
        )}

        {/* Code changes (only for assistant messages) */}
        {!isUser && message.codeChanges && message.codeChanges.length > 0 && (
          <CodeChanges changes={message.codeChanges} />
        )}
      </div>
    </motion.div>
  );
}

// Custom comparison function for React.memo
function arePropsEqual(prevProps: MessageBubbleProps, nextProps: MessageBubbleProps): boolean {
  return (
    prevProps.message.id === nextProps.message.id &&
    prevProps.message.content === nextProps.message.content &&
    prevProps.message.status === nextProps.message.status &&
    prevProps.message.timestamp === nextProps.message.timestamp &&
    prevProps.onRetry === nextProps.onRetry &&
    prevProps.onDelete === nextProps.onDelete
  );
}

export const MessageBubble = memo(MessageBubbleComponent, arePropsEqual);
MessageBubble.displayName = 'MessageBubble';
