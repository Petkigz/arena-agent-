import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { webSocketService } from '../../services/websocket';

// Mock WebSocket class with proper static constants
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  binaryType = 'blob';
  send = vi.fn();
  close = vi.fn();
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;

  constructor(_url: string) {
    // Auto-open after construction (simulates successful connection)
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.(new Event('open'));
    }, 0);
  }
}

describe('WebSocketService', () => {
  beforeEach(() => {
    webSocketService.disconnect();
    vi.stubGlobal('WebSocket', MockWebSocket);
    vi.useFakeTimers();
  });

  afterEach(() => {
    webSocketService.disconnect();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('connection status', () => {
    it('starts as disconnected', () => {
      expect(webSocketService.status).toBe('disconnected');
      expect(webSocketService.isConnected).toBe(false);
    });

    it('transitions to connecting on connect()', () => {
      webSocketService.connect('ws://localhost:8000/ws');
      expect(webSocketService.status).toBe('connecting');
    });

    it('transitions to connected after WebSocket opens', async () => {
      webSocketService.connect('ws://localhost:8000/ws');
      expect(webSocketService.status).toBe('connecting');

      // Flush the setTimeout that opens the connection
      vi.runAllTimers();
      expect(webSocketService.status).toBe('connected');
    });
  });

  describe('send', () => {
    it('returns false when not connected', () => {
      const result = webSocketService.send('test', { foo: 'bar' });
      expect(result).toBe(false);
    });
  });

  describe('sendBinary', () => {
    it('returns false when not connected', () => {
      const buffer = new ArrayBuffer(16);
      const result = webSocketService.sendBinary(buffer);
      expect(result).toBe(false);
    });
  });

  describe('subscribe', () => {
    it('returns an unsubscribe function', () => {
      const handler = vi.fn();
      const unsubscribe = webSocketService.subscribe(handler);
      expect(typeof unsubscribe).toBe('function');
      unsubscribe();
    });
  });

  describe('onStatusChange', () => {
    it('calls handler immediately with current status', () => {
      const handler = vi.fn();
      webSocketService.onStatusChange(handler);
      expect(handler).toHaveBeenCalledWith('disconnected');
    });

    it('returns an unsubscribe function', () => {
      const handler = vi.fn();
      const unsubscribe = webSocketService.onStatusChange(handler);
      expect(typeof unsubscribe).toBe('function');
      unsubscribe();
    });
  });

  describe('message sending helpers', () => {
    // Track WebSocket instances
    let lastWsInstance: MockWebSocket | null = null;

    class TrackedMockWebSocket extends MockWebSocket {
      constructor(url: string) {
        super(url);
        lastWsInstance = this;
      }
    }

    beforeEach(() => {
      lastWsInstance = null;
      vi.stubGlobal('WebSocket', TrackedMockWebSocket);
    });

    it('sendMessage returns true when connected', () => {
      webSocketService.connect('ws://localhost:8000/ws');
      vi.runAllTimers();

      const result = webSocketService.sendMessage('conv-1', 'Hello');
      expect(result).toBe(true);
    });

    it('sendMessage sends correct JSON format', () => {
      webSocketService.connect('ws://localhost:8000/ws');
      vi.runAllTimers();

      webSocketService.sendMessage('conv-1', 'Hello');

      expect(lastWsInstance!.send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'user_message', conversation_id: 'conv-1', content: 'Hello' })
      );
    });

    it('startVoiceInput sends correct message', () => {
      webSocketService.connect('ws://localhost:8000/ws');
      vi.runAllTimers();

      webSocketService.startVoiceInput('conv-1');

      expect(lastWsInstance!.send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'voice_start', conversation_id: 'conv-1' })
      );
    });

    it('createConversation sends correct message', () => {
      webSocketService.connect('ws://localhost:8000/ws');
      vi.runAllTimers();

      webSocketService.createConversation('My Chat');

      expect(lastWsInstance!.send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'create_conversation', title: 'My Chat' })
      );
    });

    it('retryMessage sends with retry_id', () => {
      webSocketService.connect('ws://localhost:8000/ws');
      vi.runAllTimers();

      webSocketService.retryMessage('conv-1', 'msg-1', 'Hello again');

      expect(lastWsInstance!.send).toHaveBeenCalledWith(
        JSON.stringify({
          type: 'user_message',
          conversation_id: 'conv-1',
          content: 'Hello again',
          retry_id: 'msg-1',
        })
      );
    });

    it('recordOwnerCorrection sends a trace-bound correction', () => {
      webSocketService.connect('ws://localhost:8000/ws');
      vi.runAllTimers();

      webSocketService.recordOwnerCorrection('conv-1', 'trace-1', 'I meant the phone', {
        errorType: 'intent',
        actionType: 'answer',
        goalType: 'device_question',
      });

      expect(lastWsInstance!.send).toHaveBeenCalledWith(
        JSON.stringify({
          type: 'owner_correction',
          conversation_id: 'conv-1',
          trace_id: 'trace-1',
          correction: 'I meant the phone',
          error_type: 'intent',
          subject: '',
          predicate: '',
          corrected_value: undefined,
          action_type: 'answer',
          goal_type: 'device_question',
        })
      );
    });
  });

  describe('message parsing', () => {
    it('parses JSON text messages and notifies subscribers', () => {
      const handler = vi.fn();
      webSocketService.subscribe(handler);

      // Track the WebSocket instance via a global ref
      const instances: MockWebSocket[] = [];
      const OriginalMock = MockWebSocket;
      vi.stubGlobal('WebSocket', function(this: MockWebSocket, url: string) {
        const ws = new OriginalMock(url);
        instances.push(ws);
        return ws;
      });

      webSocketService.connect('ws://localhost:8000/ws');
      vi.runAllTimers(); // Open connection

      const wsInstance = instances[0];
      // Simulate incoming message
      if (wsInstance && wsInstance.onmessage) {
        wsInstance.onmessage({
          data: JSON.stringify({ type: 'message_ack', conversation_id: 'c1', status: 'processing' }),
        } as unknown as MessageEvent);
      }

      expect(handler).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'message_ack',
        })
      );
    });
  });

  describe('disconnect', () => {
    it('closes the WebSocket and sets status to disconnected', () => {
      webSocketService.connect('ws://localhost:8000/ws');
      vi.runAllTimers();
      expect(webSocketService.status).toBe('connected');

      webSocketService.disconnect();
      expect(webSocketService.status).toBe('disconnected');
    });
  });
});
