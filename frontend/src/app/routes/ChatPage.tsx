import { useEffect, useRef, useCallback, useState } from 'react';
import { MessageBubble, ChatInput, ConversationShareMenu } from '../../components/chat';
import { EmptyState } from '../../components/ui';
import { MessageCircle, Share2 } from 'lucide-react';
import { useConversationStore, useMultiModalStore } from '../../stores';
import { webSocketService } from '../../services/websocket';
import * as api from '../../services/api';
import type { Message, ActionStep } from '../../types';
import type { Attachment } from '../../stores/multiModalStore';
import toast from 'react-hot-toast';

export function ChatPage() {
  const {
    currentConversation,
    conversations,
    sendMessage,
    addMessage,
    updateMessage,
    removeMessage,
  } = useConversationStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [showShareMenu, setShowShareMenu] = useState(false);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentConversation?.messages]);

  // Set up WebSocket event handlers
  useEffect(() => {
    const unsubscribe = webSocketService.subscribe((event) => {
      if (!currentConversation) return;

      if (event.type === 'message') {
        const message = event.data as Message;
        if (!message.conversationId || message.conversationId === currentConversation.id) {
          addMessage(message);
        }
      } else if (event.type === 'message_ack') {
        // Update optimistic message status to 'sent'
        const { conversation_id } = event.data as { conversation_id: string; status: string };
        if (conversation_id === currentConversation.id) {
          const msgs = currentConversation.messages;
          const sending = msgs.find(
            (m) => m.id.startsWith('temp-') && m.status === 'sending'
          );
          if (sending) {
            updateMessage(sending.id, { status: 'sent' as const });
          }
        }
      } else if (event.type === 'message_token') {
        // Streaming token support
        const { conversation_id, message_id, token, done } = event.data as {
          conversation_id: string;
          message_id: string;
          token: string;
          done: boolean;
        };
        if (conversation_id !== currentConversation.id) return;

        const existing = currentConversation.messages.find((m) => m.id === message_id);
        if (existing) {
          updateMessage(message_id, {
            content: existing.content + token,
            status: done ? 'complete' as const : 'streaming' as const,
          });
        } else {
          // Create new streaming message
          addMessage({
            id: message_id,
            role: 'assistant',
            content: token,
            timestamp: new Date().toISOString(),
            status: done ? 'complete' as const : 'streaming' as const,
          });
        }
      } else if (event.type === 'action_step') {
        const step = event.data as ActionStep & { message_id: string };
        const message = currentConversation.messages.find((m) => m.id === step.message_id);
        if (message && message.actionSteps) {
          const updatedSteps = message.actionSteps.map((s) =>
            s.id === step.id ? { ...s, ...step } : s
          );
          updateMessage(step.message_id, { actionSteps: updatedSteps });
        }
      } else if (event.type === 'conversation_created') {
        const { conversation_id, title } = event.data as { conversation_id: string; title: string };
        // Server confirmed conversation creation
        const conv = conversations.find((c) => c.id === conversation_id);
        if (conv && title) {
          // Update title if server provided a different one
        }
      }
    });

    return unsubscribe;
  }, [currentConversation, conversations, addMessage, updateMessage]);

  const handleSendMessage = useCallback(
    async (content: string, attachments?: Attachment[]) => {
      if (!currentConversation) return;

      // Upload attachments if any
      let uploadedAttachments: Attachment[] | undefined;
      if (attachments && attachments.length > 0) {
        uploadedAttachments = await Promise.all(
          attachments.map(async (attachment) => {
            if (attachment.file) {
              const result = await api.uploadFile(attachment.file, currentConversation.id);
              if (result.success && result.data) {
                const uploadedAttachment = {
                  ...attachment,
                  path: result.data.path,
                  id: result.data.id,
                  file: undefined, // Don't store the File object in the message
                };

                // Trigger analysis for images and documents
                if (attachment.type === 'image' || attachment.type === 'document') {
                  const analysisType = attachment.type === 'image' ? 'vision' : 'document';
                  api.analyzeAttachment(result.data.id, analysisType).then((analysisResult) => {
                    if (analysisResult.success && analysisResult.data) {
                      // Update the attachment with analysis results
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
              } else {
                toast.error(`Failed to upload ${attachment.name}: ${result.error}`);
                return attachment;
              }
            }
            return attachment;
          })
        );
      }

      // Create optimistic user message
      const userMessage: Message = {
        id: `temp-${Date.now()}`,
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
        status: 'sending',
        attachments: uploadedAttachments,
      };

      addMessage(userMessage);
      sendMessage(content);
    },
    [currentConversation, addMessage, sendMessage]
  );

  const handleRetry = useCallback(
    (messageId: string) => {
      if (!currentConversation) return;
      const message = currentConversation.messages.find((m) => m.id === messageId);
      if (message) {
        updateMessage(messageId, { status: 'sending' as const });
        webSocketService.retryMessage(currentConversation.id, messageId, message.content);
      }
    },
    [currentConversation, updateMessage]
  );

  const handleDelete = useCallback(
    (messageId: string) => {
      removeMessage(messageId);
    },
    [removeMessage]
  );

  const handleVoiceStart = () => {
    if (currentConversation) {
      webSocketService.startVoiceInput(currentConversation.id);
    }
  };

  const handleVoiceStop = () => {
    if (currentConversation) {
      webSocketService.stopVoiceInput(currentConversation.id);
    }
  };

  if (!currentConversation) {
    return (
      <div className="h-full flex items-center justify-center">
        <EmptyState
          icon={<MessageCircle className="w-16 h-16" />}
          title="No conversation selected"
          description="Start a new conversation or select one from the sidebar"
        />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-slate-700 bg-slate-900">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-100">{currentConversation.title}</h1>
            {currentConversation.projectId && (
              <p className="text-sm text-slate-400 mt-0.5">Project: {currentConversation.projectId}</p>
            )}
          </div>
          <button
            onClick={() => setShowShareMenu(true)}
            className="p-2 text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-colors"
            title="Share conversation"
          >
            <Share2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {currentConversation.messages.length === 0 ? (
          <EmptyState
            icon={<MessageCircle className="w-12 h-12" />}
            title="Start a conversation"
            description="Send a message or use voice input to begin"
          />
        ) : (
          <>
            {currentConversation.messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                onRetry={handleRetry}
                onDelete={handleDelete}
              />
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="flex-shrink-0">
        <ChatInput
          onSendMessage={handleSendMessage}
          onVoiceStart={handleVoiceStart}
          onVoiceStop={handleVoiceStop}
          disabled={!webSocketService.isConnected}
        />
      </div>

      {/* Share menu */}
      {currentConversation && (
        <ConversationShareMenu
          conversation={currentConversation}
          isOpen={showShareMenu}
          onClose={() => setShowShareMenu(false)}
        />
      )}
    </div>
  );
}
