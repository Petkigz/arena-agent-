import { create } from 'zustand';
import { logger } from '../services/logger';

export interface Screenshot {
  id: string;
  timestamp: string;
  image: string; // Base64 encoded
  width: number;
  height: number;
  format: string;
  annotations: Array<{
    type: 'rect' | 'circle' | 'arrow' | 'text';
    x: number;
    y: number;
    width?: number;
    height?: number;
    color: string;
    text?: string;
  }>;
  analysis?: {
    type: string;
    content: string;
    prompt_focus?: string;
    timestamp: string;
  };
}

interface ScreenshotStoreState {
  screenshots: Screenshot[];
  currentScreenshot: Screenshot | null;
  isCapturing: boolean;
  isStreaming: boolean;
  conversationId: string | null;
  websocket: WebSocket | null;

  // Actions
  addScreenshot: (screenshot: Screenshot) => void;
  setCurrentScreenshot: (screenshot: Screenshot | null) => void;
  clearScreenshots: () => void;
  startCapture: () => void;
  stopCapture: () => void;
  startStreaming: (conversationId: string) => void;
  stopStreaming: () => void;
  sendScreenshot: (screenshot: Screenshot) => void;
}

export const useScreenshotStore = create<ScreenshotStoreState>((set, get) => ({
  screenshots: [],
  currentScreenshot: null,
  isCapturing: false,
  isStreaming: false,
  conversationId: null,
  websocket: null,

  addScreenshot: (screenshot) =>
    set((state) => ({
      screenshots: [screenshot, ...state.screenshots].slice(0, 50), // Keep last 50
      currentScreenshot: screenshot,
    })),

  setCurrentScreenshot: (screenshot) => set({ currentScreenshot: screenshot }),

  clearScreenshots: () => set({ screenshots: [], currentScreenshot: null }),

  startCapture: () => set({ isCapturing: true }),

  stopCapture: () => set({ isCapturing: false }),

  startStreaming: (conversationId) => {
    const wsUrl = `ws://${window.location.hostname}:8000/api/screenshots/ws/${conversationId}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      logger.info('[Screenshot WS] Connected');
      set({ isStreaming: true, conversationId, websocket: ws });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'screenshot') {
          get().addScreenshot(data.data);
        }
      } catch (error) {
        logger.error('[Screenshot WS] Failed to parse message', error);
      }
    };

    ws.onerror = (error) => {
      logger.error('[Screenshot WS] Error', error);
    };

    ws.onclose = () => {
      logger.info('[Screenshot WS] Disconnected');
      set({ isStreaming: false, conversationId: null, websocket: null });
    };
  },

  stopStreaming: () => {
    const { websocket } = get();
    if (websocket) {
      websocket.close();
    }
    set({ isStreaming: false, conversationId: null, websocket: null });
  },

  sendScreenshot: (screenshot) => {
    const { websocket, isStreaming } = get();
    if (!isStreaming || !websocket) {
      logger.warn('[Screenshot] Not streaming, cannot send screenshot');
      return;
    }

    try {
      websocket.send(JSON.stringify({
        type: 'screenshot',
        ...screenshot,
      }));
    } catch (error) {
      logger.error('[Screenshot] Failed to send screenshot', error);
    }
  },
}));
