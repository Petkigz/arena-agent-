import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { User, Bot, RotateCcw, Trash2, Copy, Check } from 'lucide-react';
import { ActionSteps } from './ActionSteps';
import { ReasoningTrace } from './ReasoningTrace';
import { CodeChanges } from './CodeChanges';
import { AttachmentDisplay } from '../ui/AttachmentDisplay';
import type { Message } from '../../types';

interface MessageBubbleProps {
  message: Message;
  onRetry?: (messageId: string) => void;
  onDelete?: (messageId: string) => void;
}

export function MessageBubble({ message, onRetry, onDelete }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`group flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div className="flex-shrink-0">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-blue-600' : 'bg-purple-600'
        }`}>
          {isUser ? (
            <User className="w-5 h-5 text-white" />
          ) : (
            <Bot className="w-5 h-5 text-white" />
          )}
        </div>
      </div>

      {/* Message content */}
      <div className={`flex-1 max-w-[80%] ${isUser ? 'items-end' : ''}`}>
        {/* Message bubble */}
        <div className={`rounded-2xl px-4 py-2.5 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-slate-800 text-slate-100'
        }`}>
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
          ) : (
            <div className="text-sm leading-relaxed prose prose-invert prose-sm max-w-none
              prose-headings:text-slate-100 prose-p:text-slate-200 prose-a:text-blue-400
              prose-code:text-emerald-400 prose-code:bg-slate-900 prose-code:px-1 prose-code:py-0.5 prose-code:rounded
              prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-700
              prose-strong:text-slate-100 prose-li:text-slate-200">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
              {message.status === 'streaming' && (
                <span className="inline-block w-2 h-4 bg-slate-400 animate-pulse ml-0.5" />
              )}
            </div>
          )}
        </div>

        {/* Attachments */}
        {message.attachments && message.attachments.length > 0 && (
          <AttachmentDisplay attachments={message.attachments} />
        )}

        {/* Metadata and actions */}
        <div className={`mt-1 flex items-center gap-2 text-xs text-slate-500 ${
          isUser ? 'justify-end' : ''
        }`}>
          <span>
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit'
            })}
          </span>
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
              className="p-1 hover:text-slate-300 transition-colors"
              title="Copy message"
            >
              {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
            </button>
            {message.status === 'error' && onRetry && (
              <button
                onClick={() => onRetry(message.id)}
                className="p-1 hover:text-blue-400 transition-colors"
                title="Retry"
              >
                <RotateCcw className="w-3 h-3" />
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => onDelete(message.id)}
                className="p-1 hover:text-red-400 transition-colors"
                title="Delete"
              >
                <Trash2 className="w-3 h-3" />
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
    </div>
  );
}
