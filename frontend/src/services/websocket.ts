import { logger } from './logger';
import type { Message, ActionStep, PresenceState, Conversation } from '../types';

export type VoiceState = 'idle' | 'listening' | 'recording' | 'processing' | 'thinking' | 'speaking' | 'stopped';

export type WebSocketEvent =
  | { type: 'message'; data: Message }
  | { type: 'message_ack'; data: { conversation_id: string; status: string } }
  | { type: 'message_token'; data: { conversation_id: string; message_id: string; token: string; done: boolean } }
  | { type: 'action_step'; data: ActionStep & { conversation_id: string; message_id: string } }
  | { type: 'presence_update'; data: PresenceState }
  | { type: 'conversation_created'; data: { conversation_id: string; title: string } }
  | { type: 'conversation_joined'; data: { conversation_id: string } }
  | { type: 'conversation_list'; data: { conversations: Conversation[] } }
  | { type: 'voice_state'; data: { state: VoiceState; conversation_id?: string } }
  | { type: 'voice_transcript'; data: { text: string; is_final: boolean } }
  | { type: 'voice_audio'; data: ArrayBuffer }
  | { type: 'voice_status'; data: { status: string; conversation_id: string } }
  | { type: 'error'; data: { message: string } };

export type WebSocketEventHandler = (event: WebSocketEvent) => void;

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

class WebSocketService {
  private ws: WebSocket | null = null;
  private handlers: Set<WebSocketEventHandler> = new Set();
  private statusHandlers: Set<(status: ConnectionStatus) => void> = new Set();
  private _status: ConnectionStatus = 'disconnected';
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private url = '';
  private shouldReconnect = true;

  get status(): ConnectionStatus {
    return this._status;
  }

  private setStatus(status: ConnectionStatus) {
    this._status = status;
    this.statusHandlers.forEach((h) => h(status));
  }

  connect(url?: string) {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    // Resolve WebSocket URL: parameter > env var > hostname-based default
    const wsUrl = url || import.meta.env.VITE_WS_URL || `ws://${window.location.hostname}:8000/ws`;

    // Append API key if configured
    const apiKey = import.meta.env.VITE_API_KEY;
    const finalUrl = apiKey ? `${wsUrl}?api_key=${encodeURIComponent(apiKey)}` : wsUrl;

    this.url = finalUrl;
    this.shouldReconnect = true;
    this.setStatus('connecting');

    try {
      this.ws = new WebSocket(finalUrl);
      this.ws.binaryType = 'arraybuffer';

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.setStatus('connected');
        this.emit({ type: 'presence_update', data: { status: 'idle' } as PresenceState });
      };

      this.ws.onclose = (_event) => {
        this.ws = null;
        this.setStatus('disconnected');
        this.emit({ type: 'presence_update', data: { status: 'offline' } as PresenceState });

        if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (error) => {
        logger.error('[WS] Error:', error);
        this.emit({
          type: 'error',
          data: { message: 'WebSocket connection error' },
        });
      };

      this.ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          try {
            const parsed = JSON.parse(event.data);
            const wsEvent: WebSocketEvent = { type: parsed.type, data: parsed };
            this.emit(wsEvent);
          } catch {
            logger.warn('[WS] Failed to parse message', { data: event.data });
          }
        } else if (event.data instanceof ArrayBuffer) {
          // Binary audio data
          this.emit({ type: 'voice_audio', data: event.data });
        }
      };
    } catch (e) {
      logger.error('[WS] Failed to create WebSocket', e);
      this.setStatus('disconnected');
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;

    this.reconnectAttempts++;
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000);
    this.setStatus('reconnecting');

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.shouldReconnect) {
        this.connect(this.url);
      }
    }, delay);
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close(1000, 'Client disconnecting');
      this.ws = null;
    }
    this.setStatus('disconnected');
  }

  send(type: string, data: Record<string, unknown>) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      logger.warn('[WS] Not connected, cannot send', { type });
      return false;
    }
    const message = { type, ...data };
    this.ws.send(JSON.stringify(message));
    return true;
  }

  sendBinary(data: ArrayBuffer) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      logger.warn('[WS] Not connected, cannot send binary data');
      return false;
    }
    this.ws.send(data);
    return true;
  }

  sendMessage(conversationId: string, content: string) {
    return this.send('user_message', { conversation_id: conversationId, content });
  }

  retryMessage(conversationId: string, messageId: string, content: string) {
    return this.send('user_message', { conversation_id: conversationId, content, retry_id: messageId });
  }

  deleteMessage(conversationId: string, messageId: string) {
    return this.send('delete_message', { conversation_id: conversationId, message_id: messageId });
  }

  startVoiceInput(conversationId: string) {
    return this.send('voice_start', { conversation_id: conversationId });
  }

  stopVoiceInput(conversationId: string) {
    return this.send('voice_stop', { conversation_id: conversationId });
  }

  updateVoiceSettings(settings: Record<string, unknown>) {
    return this.send('voice_settings', { settings });
  }

  joinConversation(conversationId: string) {
    return this.send('join_conversation', { conversation_id: conversationId });
  }

  createConversation(title?: string) {
    return this.send('create_conversation', { title: title || 'New Conversation' });
  }

  requestConversationList() {
    return this.send('list_conversations', {});
  }

  approveAction(conversationId: string, actionId: string, approved: boolean, reason?: string) {
    return this.send('action_approval', { conversationId, actionId, approved, reason });
  }

  subscribe(handler: WebSocketEventHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  onStatusChange(handler: (status: ConnectionStatus) => void): () => void {
    this.statusHandlers.add(handler);
    // Immediately call with current status
    handler(this._status);
    return () => {
      this.statusHandlers.delete(handler);
    };
  }

  private emit(event: WebSocketEvent) {
    this.handlers.forEach((handler) => {
      try {
        handler(event);
      } catch (e) {
        logger.error('[WS] Handler error', e);
      }
    });
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const webSocketService = new WebSocketService();
