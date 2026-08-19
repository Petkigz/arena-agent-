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
  sendMessage: (content: string) => void;
  createConversation: (title?: string) => Promise<string>;
  removeConversation: (id: string) => void;
  exportConversation: (id: string) => Conversation | null;
  exportConversationAsMarkdown: (id: string) => string | null;
}

export const useConversationStore = create<ConversationState>()(
  persist(
    (set, get) => ({
      conversations: [],
      currentConversation: null,
      isLoading: false,
      error: null,

      setConversations: (conversations) => set({ conversations }),

      setCurrentConversation: (conversation) => set({ currentConversation: conversation }),

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

      sendMessage: (content) => {
        const { currentConversation } = get();
        if (!currentConversation) return;

        // Update the optimistic message status to 'sent'
        set((state) => {
          if (!state.currentConversation) return state;
          return {
            currentConversation: {
              ...state.currentConversation,
              messages: state.currentConversation.messages.map((msg) =>
                msg.id.startsWith('temp-') && msg.content === content
                  ? { ...msg, status: 'sent' as const } as Message
                  : msg
              ),
            },
          };
        });

        // Send via WebSocket
        webSocketService.sendMessage(currentConversation.id, content);
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

        // Notify backend
        webSocketService.createConversation(title);

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
