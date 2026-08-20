import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type AttachmentType = 'image' | 'document' | 'code' | 'audio' | 'video';

export interface Attachment {
  id: string;
  type: AttachmentType;
  name: string;
  path: string;
  size: number;
  mimeType: string;
  preview?: string; // base64 for images
  analysis?: AttachmentAnalysis;
  uploadedAt: string;
  file?: File; // Store the actual File object for upload
}

export interface AttachmentAnalysis {
  type: 'ocr' | 'vision' | 'document' | 'code';
  content: string;
  confidence?: number;
  metadata?: Record<string, string | number | boolean>;
  analyzedAt: string;
}

export interface MultiModalMessage {
  id: string;
  conversationId: string;
  role: 'user' | 'assistant';
  text?: string;
  attachments: Attachment[];
  timestamp: string;
}

interface MultiModalStoreState {
  attachments: Attachment[];
  pendingAttachments: Attachment[]; // Attachments waiting to be sent
  isLoading: boolean;
  error: string | null;

  // Attachment actions
  addAttachment: (attachment: Attachment) => void;
  addPendingAttachment: (attachment: Attachment) => void;
  removePendingAttachment: (id: string) => void;
  clearPendingAttachments: () => void;
  setAttachmentAnalysis: (id: string, analysis: AttachmentAnalysis) => void;
  removeAttachment: (id: string) => void;

  // Utility
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  // Queries
  getAttachmentsByType: (type: AttachmentType) => Attachment[];
  getAnalyzedAttachments: () => Attachment[];
}

export const useMultiModalStore = create<MultiModalStoreState>()(
  persist(
    (set, get) => ({
      attachments: [],
      pendingAttachments: [],
      isLoading: false,
      error: null,

      addAttachment: (attachment) =>
        set((state) => ({
          attachments: [attachment, ...state.attachments],
        })),

      addPendingAttachment: (attachment) =>
        set((state) => ({
          pendingAttachments: [...state.pendingAttachments, attachment],
        })),

      removePendingAttachment: (id) =>
        set((state) => ({
          pendingAttachments: state.pendingAttachments.filter((a) => a.id !== id),
        })),

      clearPendingAttachments: () => set({ pendingAttachments: [] }),

      setAttachmentAnalysis: (id, analysis) =>
        set((state) => ({
          attachments: state.attachments.map((a) =>
            a.id === id ? { ...a, analysis } : a
          ),
        })),

      removeAttachment: (id) =>
        set((state) => ({
          attachments: state.attachments.filter((a) => a.id !== id),
        })),

      setLoading: (loading) => set({ isLoading: loading }),
      setError: (error) => set({ error }),

      getAttachmentsByType: (type) => {
        const state = get();
        return state.attachments.filter((a) => a.type === type);
      },

      getAnalyzedAttachments: () => {
        const state = get();
        return state.attachments.filter((a) => a.analysis);
      },
    }),
    {
      name: 'arena-multimodal',
    }
  )
);
