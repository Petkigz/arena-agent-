import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Conversation, Message } from '../types';
import { webSocketService } from '../services/websocket';

interface ConversationState {
  conversations: Conversation[];
  currentConversation: Conversation | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  setConversations: (conversations: Conversation[]) => void;
  setCurrentConversation: (conversation: Conversation | null) => void;
  addMessage: (message: Message) => void;
  updateMessage: (messageId: string, updates: Partial<Message>) => void;
  removeMessage: (messageId: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  sendMessage: (content: string, imagePath?: string, attachments?: Array<{ name: string; path: string }>) => void;
  createConversation: (title?: string) => Promise<string>;
  removeConversation: (id: string) => void;
  exportConversation: (id: string) => Conversation | null;
  exportConversationAsMarkdown: (id: string) => string | null;
  hydrateFromServer: (
    previews: Array<{ id: string; title: string; lastMessage: string; updatedAt: string }>
  ) => void;
  hydrateMessages: (conversationId: string, messages: Array<{ role: string; content: string }>) => void;
}

export const useConversationStore = create<ConversationState>()(
  persist(
    (set, get) => ({
      conversations: [],
      currentConversation: null,
      isLoading: false,
      error: null,

      setConversations: (conversations) => set({ conversations }),

      setCurrentConversation: (conversation) => {
        set({ currentConversation: conversation });
        // Hydrate history from the backend when opening a conversation that has
        // not yet loaded its messages (persisted conversations start empty).
        if (conversation && conversation.messages.length === 0) {
          webSocketService.requestConversationHistory(conversation.id);
        }
      },

      addMessage: (message) =>
        set((state) => {
          if (!state.currentConversation) return state;
          const updatedConv = {
            ...state.currentConversation,
            messages: [...state.currentConversation.messages, message],
            updatedAt: new Date().toISOString(),
          };
          return {
            currentConversation: updatedConv,
            conversations: state.conversations.map((c) =>
              c.id === updatedConv.id ? updatedConv : c
            ),
          };
        }),

      updateMessage: (messageId, updates) =>
        set((state) => {
          if (!state.currentConversation) return state;
          const updatedConv = {
            ...state.currentConversation,
            messages: state.currentConversation.messages.map((msg) =>
              msg.id === messageId ? { ...msg, ...updates } : msg
            ),
          };
          return {
            currentConversation: updatedConv,
            conversations: state.conversations.map((c) =>
              c.id === updatedConv.id ? updatedConv : c
            ),
          };
        }),

      removeMessage: (messageId) =>
        set((state) => {
          if (!state.currentConversation) return state;
          const updatedConv = {
            ...state.currentConversation,
            messages: state.currentConversation.messages.filter((msg) => msg.id !== messageId),
          };
          return {
            currentConversation: updatedConv,
            conversations: state.conversations.map((c) =>
              c.id === updatedConv.id ? updatedConv : c
            ),
          };
        }),

      setLoading: (loading) => set({ isLoading: loading }),

      setError: (error) => set({ error }),

      sendMessage: (content, imagePath, attachments) => {
        const { currentConversation } = get();
        if (!currentConversation) return;

        // B10 fix: ack by temp-id, not content (same text sent twice would ack wrong).
        // Mark all temp- sending messages as sent — server ack doesn't include message_id,
        // so we mark all pending optimistics. The streaming token will create the assistant reply.
        set((state) => {
          if (!state.currentConversation) return state;
          return {
            currentConversation: {
              ...state.currentConversation,
              messages: state.currentConversation.messages.map((msg) =>
                msg.id.startsWith('temp-') && msg.status === 'sending'
                  ? { ...msg, status: 'sent' as const } as Message
                  : msg
              ),
            },
          };
        });

        // Send via WebSocket — P2 multimodal: include image_path + attachments so backend grounds vision
        webSocketService.sendMessage(currentConversation.id, content, imagePath, attachments as any);
      },

      createConversation: async (title) => {
        const conversationId = `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const newConversation: Conversation = {
          id: conversationId,
          title: title || 'New Conversation',
          messages: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };

        // Add to conversations list
        set((state) => ({
          conversations: [newConversation, ...state.conversations],
          currentConversation: newConversation,
        }));

        // Notify backend with the client-generated ID
        webSocketService.createConversation(title, conversationId);

        return conversationId;
      },

      removeConversation: (id) =>
        set((state) => ({
          conversations: state.conversations.filter((c) => c.id !== id),
          currentConversation: state.currentConversation?.id === id ? null : state.currentConversation,
        })),

      exportConversation: (id) => {
        const state = get();
        return state.conversations.find((c) => c.id === id) || null;
      },

      hydrateFromServer: (previews) =>
        set((state) => {
          const existingById = new Map(state.conversations.map((c) => [c.id, c]));
          const previewIds = new Set(previews.map((p) => p.id));
          // Keep local conversations that are not in server previews (offline-created)
          const localOnly = state.conversations.filter((c) => !previewIds.has(c.id));
          const conversations: Conversation[] = previews.map((p) => {
            const existing = existingById.get(p.id);
            return existing
              ? { ...existing, title: p.title || existing.title }
              : {
                  id: p.id,
                  title: p.title || 'New Conversation',
                  messages: [],
                  createdAt: p.updatedAt || new Date().toISOString(),
                  updatedAt: p.updatedAt || new Date().toISOString(),
                };
          });
          // Merge: server previews first, then local-only (preserves offline work) — fixes B11
          return { conversations: [...conversations, ...localOnly] };
        }),

      hydrateMessages: (conversationId, messages) =>
        set((state) => {
          const mapped: Message[] = messages.map((m, i) => ({
            id: `hist-${conversationId}-${i}`,
            conversationId,
            role: m.role === 'assistant' ? 'assistant' : 'user',
            content: m.content,
            timestamp: new Date().toISOString(),
            status: 'complete' as const,
          }));
          const updateConv = (c: Conversation): Conversation =>
            c.id === conversationId
              ? { ...c, messages: mapped, updatedAt: new Date().toISOString() }
              : c;
          return {
            conversations: state.conversations.map(updateConv),
            currentConversation: state.currentConversation
              ? updateConv(state.currentConversation)
              : state.currentConversation,
          };
        }),

      exportConversationAsMarkdown: (id) => {
        const state = get();
        const conv = state.conversations.find((c) => c.id === id);
        if (!conv) return null;

        const lines: string[] = [
          `# ${conv.title}`,
          '',
          `*Created: ${new Date(conv.createdAt).toLocaleString()}*`,
          `*Updated: ${new Date(conv.updatedAt).toLocaleString()}*`,
          '',
          '---',
          '',
        ];

        for (const msg of conv.messages) {
          const role = msg.role === 'user' ? '**You**' : '**Arena**';
          const time = new Date(msg.timestamp).toLocaleString();
          lines.push(`### ${role} — ${time}`);
          lines.push('');
          lines.push(msg.content);
          lines.push('');
        }

        return lines.join('\n');
      },
    }),
    {
      name: 'arena-conversations',
      partialize: (state) => ({
        conversations: state.conversations,
      }),
    }
  )
);
