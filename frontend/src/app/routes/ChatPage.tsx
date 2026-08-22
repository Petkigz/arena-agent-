import { useEffect, useRef, useCallback, useState } from 'react';
import { MessageBubble, ChatInput, ConversationShareMenu, VirtualMessageList } from '../../components/chat';
import { EmptyState } from '../../components/ui';
import { PresenceOrb } from '../../components/presence/PresenceOrb';
import { MessageCircle, Share2 } from 'lucide-react';
import { useConversationStore, useMultiModalStore } from '../../stores';
import { useVoice } from '../../hooks/useVoice';
import { webSocketService } from '../../services/websocket';
import * as api from '../../services/api';
import type { Message, ActionStep } from '../../types';
import type { Attachment } from '../../stores/multiModalStore';
import toast from 'react-hot-toast';

export function ChatPage() {
  const { currentConversation, conversations, sendMessage, addMessage, updateMessage, removeMessage } = useConversationStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [showShareMenu, setShowShareMenu] = useState(false);

  const handleSendMessage = useCallback(async (content: string, attachments?: Attachment[]) => {
    if (!currentConversation) return;

    let uploadedAttachments: Attachment[] | undefined;
    if (attachments?.length) {
      uploadedAttachments = await Promise.all(attachments.map(async (attachment) => {
        if (!attachment.file) return attachment;
        const result = await api.uploadFile(attachment.file, currentConversation.id);
        if (!result.success || !result.data) {
          toast.error(`Failed to upload ${attachment.name}: ${result.error}`);
          return attachment;
        }
        const uploadedAttachment = { ...attachment, path: result.data.path, id: result.data.id, file: undefined };
        if (attachment.type === 'image' || attachment.type === 'document') {
          const analysisType = attachment.type === 'image' ? 'vision' : 'document';
          api.analyzeAttachment(result.data.id, analysisType).then((analysisResult) => {
            if (analysisResult.success && analysisResult.data) {
              useMultiModalStore.getState().setAttachmentAnalysis(result.data!.id, {
                type: analysisResult.data!.type as 'ocr' | 'vision' | 'document' | 'code',
                content: analysisResult.data!.content,
                confidence: analysisResult.data!.confidence,
                metadata: analysisResult.data!.metadata,
                analyzedAt: analysisResult.data!.analyzedAt,
              });
            }
          });
        }
        return uploadedAttachment;
      }));
    }

    addMessage({ id: `temp-${Date.now()}`, role: 'user', content, timestamp: new Date().toISOString(), status: 'sending', attachments: uploadedAttachments });
    sendMessage(content);
  }, [currentConversation, addMessage, sendMessage]);

  const handleVoiceTranscript = useCallback((text: string, isFinal: boolean) => {
    if (isFinal && text.trim()) void handleSendMessage(text.trim());
  }, [handleSendMessage]);

  const conversationId = currentConversation?.id ?? '';
  const { voiceState, isListening, startListening, stopListening, audioLevel } = useVoice({
    conversationId,
    onTranscript: handleVoiceTranscript,
    onError: (message) => toast.error(message),
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentConversation?.messages]);

  useEffect(() => {
    const unsubscribe = webSocketService.subscribe((event) => {
      if (!currentConversation) return;

      if (event.type === 'message') {
        const message = event.data as Message;
        if (!message.conversationId || message.conversationId === currentConversation.id) addMessage(message);
      } else if (event.type === 'message_ack') {
        const { conversation_id } = event.data as { conversation_id: string; status: string };
        if (conversation_id === currentConversation.id) {
          const sending = currentConversation.messages.find((m) => m.id.startsWith('temp-') && m.status === 'sending');
          if (sending) updateMessage(sending.id, { status: 'sent' as const });
        }
      } else if (event.type === 'message_token') {
        const { conversation_id, message_id, token, done } = event.data as { conversation_id: string; message_id: string; token: string; done: boolean };
        if (conversation_id !== currentConversation.id) return;
        const existing = currentConversation.messages.find((m) => m.id === message_id);
        if (existing) {
          updateMessage(message_id, { content: existing.content + token, status: done ? 'complete' as const : 'streaming' as const });
        } else {
          addMessage({ id: message_id, role: 'assistant', content: token, timestamp: new Date().toISOString(), status: done ? 'complete' as const : 'streaming' as const });
        }
      } else if (event.type === 'action_step') {
        const step = event.data as ActionStep & { message_id: string };
        const message = currentConversation.messages.find((m) => m.id === step.message_id);
        if (message?.actionSteps) updateMessage(step.message_id, { actionSteps: message.actionSteps.map((s) => s.id === step.id ? { ...s, ...step } : s) });
      }
    });
    return unsubscribe;
  }, [currentConversation, conversations, addMessage, updateMessage]);

  const handleRetry = useCallback((messageId: string) => {
    if (!currentConversation) return;
    const message = currentConversation.messages.find((m) => m.id === messageId);
    if (message) {
      updateMessage(messageId, { status: 'sending' as const });
      webSocketService.retryMessage(currentConversation.id, messageId, message.content);
    }
  }, [currentConversation, updateMessage]);

  const handleDelete = useCallback((messageId: string) => removeMessage(messageId), [removeMessage]);

  const presenceStatus = voiceState === 'listening' || voiceState === 'recording'
    ? 'listening'
    : voiceState === 'speaking'
      ? 'speaking'
      : voiceState === 'thinking' || voiceState === 'processing'
        ? 'working'
        : 'idle';

  if (!currentConversation) {
    return <div className="h-full flex items-center justify-center"><EmptyState icon={<MessageCircle className="w-16 h-16" />} title="No conversation selected" description="Start a new conversation or select one from the sidebar" /></div>;
  }

  return (
    <div className="h-full flex flex-col relative bg-background-primary">
      {/* ChatGPT-style conversation header: Beanie is the assistant identity; the chat title is secondary. */}
      <div className="flex-shrink-0 px-5 md:px-7 py-3 border-b border-background-surface bg-background-primary">
        <div className="flex items-center justify-between max-w-5xl mx-auto w-full">
          <div className="flex items-center gap-3 min-w-0">
            <PresenceOrb status={presenceStatus} size="sm" activity={audioLevel} />
            <div className="min-w-0">
              <h1 className="text-base font-semibold text-text-primary">Beanie</h1>
              <p className="text-xs text-text-muted truncate">{currentConversation.title}{currentConversation.projectId ? ` · ${currentConversation.projectId}` : ''}</p>
            </div>
          </div>
          <button onClick={() => setShowShareMenu(true)} className="p-2 text-text-muted hover:text-text-primary hover:bg-background-secondary rounded-lg transition-colors" title="Share conversation" aria-label="Share conversation">
            <Share2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      {currentConversation.messages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center px-6 py-4" role="region" aria-label="Messages">
          <div className="flex flex-col items-center text-center">
            <PresenceOrb status={presenceStatus} size="lg" activity={audioLevel} className="mb-3" />
            <h2 className="text-2xl font-semibold text-text-primary mb-1">How can Beanie help?</h2>
            <p className="text-sm text-text-muted">Send a message or use voice input to begin.</p>
          </div>
        </div>
      ) : currentConversation.messages.length > 50 ? (
        <VirtualMessageList messages={currentConversation.messages} onRetry={handleRetry} onDelete={handleDelete} className="px-4 md:px-8" />
      ) : (
        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-5" role="log" aria-label="Messages" aria-live="polite" aria-relevant="additions">
          <div className="max-w-4xl mx-auto space-y-6">
            {currentConversation.messages.map((message) => <MessageBubble key={message.id} message={message} onRetry={handleRetry} onDelete={handleDelete} />)}
            <div ref={messagesEndRef} />
          </div>
        </div>
      )}

      {isListening && (
        <div className="absolute left-1/2 bottom-24 -translate-x-1/2 z-20 pointer-events-none">
          <div className="rounded-2xl bg-background-primary/90 backdrop-blur-md border border-background-surface shadow-2xl px-4 py-2 flex items-center gap-2">
            <PresenceOrb status={presenceStatus} size="xs" activity={audioLevel} />
            <span className="text-xs text-text-secondary">Listening to you…</span>
          </div>
        </div>
      )}

      <div className="flex-shrink-0 px-3 md:px-6 pb-3 bg-background-primary">
        <div className="max-w-4xl mx-auto">
          <ChatInput onSendMessage={handleSendMessage} onVoiceStart={startListening} onVoiceStop={stopListening} isListening={isListening} disabled={!webSocketService.isConnected} />
          <p className="text-[10px] text-center text-text-muted mt-2">Beanie can make mistakes. Verify important information.</p>
        </div>
      </div>

      {currentConversation && <ConversationShareMenu conversation={currentConversation} isOpen={showShareMenu} onClose={() => setShowShareMenu(false)} />}
    </div>
  );
}
