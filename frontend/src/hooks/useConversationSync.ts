import { useEffect } from 'react';
import { webSocketService } from '../services/websocket';
import { useConversationStore } from '../stores/conversationStore';

/**
 * Hydrates the conversation store from the backend (SQLite-persisted) so chat
 * history survives restarts and syncs across browser sessions.
 *
 * - On connection, requests the conversation list.
 * - On `conversation_list`, populates the store's conversations.
 * - On `conversation_history`, populates a conversation's messages.
 */
export function useConversationSync(): void {
  const hydrateFromServer = useConversationStore((s) => s.hydrateFromServer);
  const hydrateMessages = useConversationStore((s) => s.hydrateMessages);

  useEffect(() => {
    const unsubscribe = webSocketService.subscribe((event) => {
      if (event.type === 'conversation_list') {
        const { conversations } = event.data as {
          conversations: Array<{ id: string; title: string; lastMessage: string; updatedAt: string }>;
        };
        if (Array.isArray(conversations)) {
          hydrateFromServer(conversations);
        }
      } else if (event.type === 'conversation_history') {
        const { conversation_id, messages } = event.data as {
          conversation_id: string;
          messages: Array<{ role: string; content: string }>;
        };
        if (conversation_id && Array.isArray(messages)) {
          hydrateMessages(conversation_id, messages);
        }
      }
    });

    // Request the list once connected (and re-request on reconnect).
    const unsubStatus = webSocketService.onStatusChange((status) => {
      if (status === 'connected') {
        webSocketService.requestConversationList();
      }
    });

    return () => {
      unsubscribe();
      unsubStatus();
    };
  }, [hydrateFromServer, hydrateMessages]);
}
