import { useEffect, useRef, useCallback, useState } from 'react';
import { MessageBubble, ChatInput, ConversationShareMenu, VirtualMessageList } from '../../components/chat';
import { BeanieOrbPanel, ListeningIndicator } from '../../components/beanie';
import { ReactiveBeanieOrb } from '../../components/presence';
import { EmptyState } from '../../components/ui';
import { MessageCircle, Share2, ShieldAlert } from 'lucide-react';
import { useConversationStore, useMultiModalStore } from '../../stores';
import {
  webSocketService,
  type ApprovalRequestEvent,
  type ApprovalResultEvent,
  type VoiceState,
} from '../../services/websocket';
import { executeAuthorizedAction, revokeAuthorization } from '../../services/ownerControl';
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
  const [beanieActive, setBeanieActive] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [approvalRequest, setApprovalRequest] = useState<ApprovalRequestEvent | null>(null);
  const [approvalResult, setApprovalResult] = useState<ApprovalResultEvent | null>(null);
  const [authorizedExecutionBusy, setAuthorizedExecutionBusy] = useState(false);

  // Track the voice pipeline state so the floating listening indicator reflects it.
  useEffect(() => {
    const unsubscribe = webSocketService.subscribe((event) => {
      if (event.type === 'voice_state') {
        setVoiceState(event.data.state as VoiceState);
      }
    });
    return unsubscribe;
  }, []);

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
        // B10 fix: mark all pending temp- sending as sent (server ack has no message_id)
        const { conversation_id } = event.data as { conversation_id: string; status: string };
        if (conversation_id === currentConversation.id) {
          const sending = currentConversation.messages.filter(
            (m) => m.id.startsWith('temp-') && m.status === 'sending'
          );
          sending.forEach((msg) => updateMessage(msg.id, { status: 'sent' as const }));
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
      } else if (event.type === 'approval_request') {
        const request = event.data as ApprovalRequestEvent;
        if (request.conversation_id === currentConversation.id) {
          setApprovalRequest(request);
          setApprovalResult(null);
        }
      } else if (event.type === 'approval_result') {
        const result = event.data as ApprovalResultEvent;
        if (approvalRequest?.action_id === result.action_id) {
          setApprovalResult(result);
          if (result.status === 'denied') setApprovalRequest(null);
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
        // Server confirmed conversation creation — frontend already created it optimistically
      }
    });

    return unsubscribe;
  }, [currentConversation, conversations, addMessage, updateMessage, approvalRequest]);

  const handleSendMessage = useCallback(
    async (content: string, attachments?: Attachment[]) => {
      if (!currentConversation) return;

      // Upload attachments if any
      let uploadedAttachments: Attachment[] | undefined;
      let imagePathForGrounding: string | undefined;
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

                // P2 AGI: Capture image path for multimodal grounding (perception→grounding)
                if (attachment.type === 'image' && !imagePathForGrounding) {
                  imagePathForGrounding = result.data.path;
                }

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
      // P2 multimodal: pass image path + attachments so backend grounds vision via cognitive runtime
      const attachPayload = uploadedAttachments?.map((a) => ({ name: a.name, path: a.path || '' })) || [];
      sendMessage(content, imagePathForGrounding, attachPayload as any);
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

  const decideApproval = (approved: boolean) => {
    if (!currentConversation || !approvalRequest) return;
    webSocketService.approveAction(
      currentConversation.id,
      approvalRequest.action_id,
      approved,
      approved ? 'Approved exact scope' : 'Denied by owner',
    );
    if (!approved) {
      setApprovalRequest(null);
      setApprovalResult(null);
      toast('Action denied');
    }
  };

  const discardAuthorization = async () => {
    if (approvalResult?.authorization_id) {
      await revokeAuthorization(approvalResult.authorization_id);
    }
    setApprovalRequest(null);
    setApprovalResult(null);
    toast('Authorization revoked');
  };

  const executeApprovedScope = async () => {
    if (!approvalRequest || !approvalResult?.authorization_id) return;
    setAuthorizedExecutionBusy(true);
    const result = await executeAuthorizedAction({
      authorizationId: approvalResult.authorization_id,
      actionType: approvalRequest.action_type,
      payload: approvalRequest.payload,
      userText: approvalRequest.goal_text || `Execute owner-approved ${approvalRequest.action_type}`,
    });
    setAuthorizedExecutionBusy(false);
    if (!result.success) {
      toast.error(result.reason || 'Authorized action did not execute');
      return;
    }

    setApprovalRequest(null);
    setApprovalResult(null);
    if (result.goalVerified) {
      toast.success('Authorized action executed and independently verified');
    } else if (result.executionSuccess) {
      toast(
        result.verificationUnknown
          ? 'Action executed, but the outcome remains unknown pending evidence'
          : 'Action executed, but the goal was not verified',
      );
    } else {
      toast.error('Authorized execution was attempted but the tool did not succeed');
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
    <div className="relative h-full flex flex-col">
      {/* Floating voice-state indicator (listening / thinking / speaking) */}
      <ListeningIndicator state={voiceState} />
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-background-surface bg-background-primary">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-text-primary">{currentConversation.title}</h1>
            {currentConversation.projectId && (
              <p className="text-sm text-text-muted mt-0.5">Project: {currentConversation.projectId}</p>
            )}
          </div>
          <button
            onClick={() => setShowShareMenu(true)}
            className="p-2 text-text-muted hover:text-text-primary hover:bg-background-secondary rounded-lg transition-colors"
            title="Share conversation"
          >
            <Share2 className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Owner approval is separate from execution. */}
      {approvalRequest && (
        <div className="flex-shrink-0 mx-6 mt-4 rounded-lg border border-amber-500/60 bg-amber-500/10 p-4" role="alert">
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 text-amber-500 mt-0.5" />
            <div className="flex-1 min-w-0">
              <h2 className="font-semibold text-text-primary">Owner authorization required</h2>
              <p className="text-sm text-text-secondary mt-1">{approvalRequest.reason}</p>
              <p className="text-sm font-medium text-text-primary mt-2">
                Action: <code>{approvalRequest.action_type}</code>
              </p>
              <pre className="mt-2 max-h-32 overflow-auto rounded bg-background-primary p-2 text-xs text-text-secondary">
                {JSON.stringify(approvalRequest.payload, null, 2)}
              </pre>

              {!approvalResult?.authorization_id ? (
                <div className="flex gap-2 mt-3">
                  <button
                    type="button"
                    onClick={() => decideApproval(false)}
                    className="px-3 py-2 rounded border border-border text-text-primary"
                  >
                    Deny
                  </button>
                  <button
                    type="button"
                    onClick={() => decideApproval(true)}
                    className="px-3 py-2 rounded bg-amber-600 text-white"
                  >
                    Authorize exact scope
                  </button>
                </div>
              ) : (
                <div className="mt-3">
                  <p className="text-xs text-text-secondary">
                    Authorized once. Nothing has executed yet. Review the unchanged payload, then execute separately.
                  </p>
                  <div className="flex gap-2 mt-2">
                    <button
                      type="button"
                      onClick={discardAuthorization}
                      className="px-3 py-2 rounded border border-border text-text-primary"
                    >
                      Do not execute
                    </button>
                    <button
                      type="button"
                      disabled={authorizedExecutionBusy}
                      onClick={executeApprovedScope}
                      className="px-3 py-2 rounded bg-red-600 text-white disabled:opacity-50"
                    >
                      {authorizedExecutionBusy ? 'Executing…' : 'Execute authorized action'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Beanie orb (replaces the chat content when active) OR messages */}
      {beanieActive ? (
        <div className="flex-1 overflow-hidden">
          <BeanieOrbPanel conversationId={currentConversation.id} />
        </div>
      ) : currentConversation.messages.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6 py-4" role="region" aria-label="Messages">
          <ReactiveBeanieOrb status="idle" size="lg" className="mb-4" />
          <h2 className="text-xl font-semibold text-text-primary">I'm Beanie.</h2>
          <p className="text-sm text-text-secondary mt-1 text-center">
            Send a message or tap the ✨ orb to talk.
          </p>
        </div>
      ) : currentConversation.messages.length > 50 ? (
        /* Virtual scrolling for large message lists */
        <VirtualMessageList
          messages={currentConversation.messages}
          onRetry={handleRetry}
          onDelete={handleDelete}
          className="px-6"
        />
      ) : (
        /* Regular rendering for small message lists */
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6" role="log" aria-label="Messages" aria-live="polite" aria-relevant="additions">
          {currentConversation.messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              onRetry={handleRetry}
              onDelete={handleDelete}
            />
          ))}
          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Input */}
      <div className="flex-shrink-0">
        <ChatInput
          onSendMessage={handleSendMessage}
          onVoiceStart={handleVoiceStart}
          onVoiceStop={handleVoiceStop}
          onOpenBeanie={() => setBeanieActive((v) => !v)}
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
