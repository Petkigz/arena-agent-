import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import * as api from '../services/api';

export interface UploadedFile {
  id: string;
  name: string;
  path: string;
  size: number;
  type: string;
  category: string;
  hash: string;
  uploadedAt: string;
  conversationId?: string;
  preview?: string; // base64 for images
}

export interface FileFolder {
  id: string;
  name: string;
  path: string;
  files: UploadedFile[];
  folders: FileFolder[];
}

interface FileStoreState {
  files: UploadedFile[];
  selectedFile: UploadedFile | null;
  isLoading: boolean;
  uploadProgress: number;
  error: string | null;

  // Actions
  uploadFile: (file: File, conversationId?: string) => Promise<boolean>;
  removeFile: (id: string) => Promise<boolean>;
  downloadFile: (id: string) => Promise<Blob | null>;
  setSelectedFile: (file: UploadedFile | null) => void;
  setLoading: (loading: boolean) => void;
  setUploadProgress: (progress: number) => void;
  setError: (error: string | null) => void;
  clearFiles: () => void;
  fetchFiles: (conversationId?: string) => Promise<void>;

  // Queries
  getFilesByConversation: (conversationId: string) => UploadedFile[];
  getFilesByType: (type: string) => UploadedFile[];
  searchFiles: (query: string) => UploadedFile[];
}

export const useFileStore = create<FileStoreState>()(
  persist(
    (set, get) => ({
      files: [],
      selectedFile: null,
      isLoading: false,
      uploadProgress: 0,
      error: null,

      uploadFile: async (file, conversationId) => {
        set({ isLoading: true, error: null, uploadProgress: 0 });
        
        const result = await api.uploadFile(file, conversationId, (progress) => {
          set({ uploadProgress: progress });
        });

        if (result.success && result.data) {
          set((state) => ({
            files: [result.data!, ...state.files],
            isLoading: false,
            uploadProgress: 0,
          }));
          return true;
        } else {
          set({ isLoading: false, uploadProgress: 0, error: result.error });
          return false;
        }
      },

      removeFile: async (id) => {
        set({ isLoading: true, error: null });
        
        const result = await api.deleteFile(id);

        if (result.success) {
          set((state) => ({
            files: state.files.filter((f) => f.id !== id),
            selectedFile: state.selectedFile?.id === id ? null : state.selectedFile,
            isLoading: false,
          }));
          return true;
        } else {
          set({ isLoading: false, error: result.error });
          return false;
        }
      },

      downloadFile: async (id) => {
        set({ isLoading: true, error: null });
        const blob = await api.downloadFile(id);
        set({ isLoading: false });
        return blob;
      },

      setSelectedFile: (file) => set({ selectedFile: file }),

      setLoading: (loading) => set({ isLoading: loading }),

      setUploadProgress: (progress) => set({ uploadProgress: progress }),

      setError: (error) => set({ error }),

      clearFiles: () => set({ files: [], selectedFile: null }),

      fetchFiles: async (conversationId) => {
        set({ isLoading: true, error: null });
        const result = await api.listFiles(conversationId);

        if (result.success && result.data) {
          set({ files: result.data.files, isLoading: false });
        } else {
          set({ isLoading: false, error: result.error });
        }
      },

      getFilesByConversation: (conversationId) => {
        const state = get();
        return state.files.filter((f) => f.conversationId === conversationId);
      },

      getFilesByType: (type) => {
        const state = get();
        return state.files.filter((f) => f.type.startsWith(type));
      },

      searchFiles: (query) => {
        const state = get();
        const q = query.toLowerCase();
        return state.files.filter((f) => f.name.toLowerCase().includes(q));
      },
    }),
    {
      name: 'arena-files',
    }
  )
);
