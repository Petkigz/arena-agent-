import { useEffect, useRef } from 'react';
import { webSocketService } from '../services/websocket';
import { useConversationStore } from '../stores/conversationStore';

/**
 * Hydrates the conversation store from the backend (SQLite-persisted) so chat
 * history survives restarts and syncs across browser sessions and devices.
 *
 * - On connection, requests the conversation list, re-joins the open
 *   conversation's room and re-fetches its history (page reload / reconnect
 *   always converges to the server's state).
 * - On `conversation_list`, populates the store's conversations.
 * - On `conversation_history`, populates a conversation's messages.
 * - On `conversation_activity` (the owner chatted on another device), the
 *   list is refreshed (debounced) so new/updated conversations appear in the
 *   sidebar without a page reload.
 */
export function useConversationSync(): void {
  const hydrateFromServer = useConversationStore((s) => s.hydrateFromServer);
  const hydrateMessages = useConversationStore((s) => s.hydrateMessages);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const requestList = () => webSocketService.requestConversationList();

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
      } else if (event.type === 'conversation_activity') {
        // Another device moved the owner's active conversation — refresh the
        // sidebar soon (debounced: bursts of messages trigger one refresh).
        if (refreshTimer.current) clearTimeout(refreshTimer.current);
        refreshTimer.current = setTimeout(requestList, 500);
      }
    });

    // Request the list once connected (and re-request on reconnect), plus
    // re-join the open room and re-hydrate its history so a page reload or
    // reconnect lands on the same live conversation.
    const unsubStatus = webSocketService.onStatusChange((status) => {
      if (status === 'connected') {
        requestList();
        const { currentConversation } = useConversationStore.getState();
        if (currentConversation) {
          webSocketService.joinConversation(currentConversation.id);
          webSocketService.requestConversationHistory(currentConversation.id);
        }
      }
    });

    return () => {
      unsubscribe();
      unsubStatus();
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [hydrateFromServer, hydrateMessages]);
}
