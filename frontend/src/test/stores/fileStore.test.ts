import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useFileStore } from '../../stores/fileStore';
import * as api from '../../services/api';

// Mock the API service
vi.mock('../../services/api', () => ({
  uploadFile: vi.fn(),
  downloadFile: vi.fn(),
  deleteFile: vi.fn(),
  listFiles: vi.fn(),
}));

describe('fileStore', () => {
  beforeEach(() => {
    useFileStore.setState({
      files: [],
      selectedFile: null,
      isLoading: false,
      error: null,
      uploadProgress: 0,
    });
    vi.clearAllMocks();
  });

  describe('uploadFile', () => {
    it('uploads file successfully', async () => {
      const mockFile = new File(['test content'], 'test.txt', { type: 'text/plain' });
      const mockResponse = {
        success: true,
        data: {
          id: 'file-123',
          name: 'test.txt',
          path: '/uploads/file-123.txt',
          size: 12,
          type: 'text/plain',
          category: 'document',
          hash: 'abc123',
          uploadedAt: '2026-08-19T10:00:00Z',
          conversationId: 'conv-1',
        },
      };

      vi.mocked(api.uploadFile).mockResolvedValue(mockResponse);

      const result = await useFileStore.getState().uploadFile(mockFile, 'conv-1');

      expect(result).toBe(true);
      expect(api.uploadFile).toHaveBeenCalledWith(mockFile, 'conv-1', expect.any(Function));
      expect(useFileStore.getState().files).toHaveLength(1);
      expect(useFileStore.getState().files[0].id).toBe('file-123');
      expect(useFileStore.getState().files[0].name).toBe('test.txt');
    });

    it('handles upload failure', async () => {
      const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
      const mockResponse = {
        success: false,
        error: 'Upload failed',
      };

      vi.mocked(api.uploadFile).mockResolvedValue(mockResponse);

      const result = await useFileStore.getState().uploadFile(mockFile);

      expect(result).toBe(false);
      expect(useFileStore.getState().error).toBe('Upload failed');
      expect(useFileStore.getState().files).toHaveLength(0);
    });

    it('updates upload progress', async () => {
      const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
      const mockResponse = {
        success: true,
        data: {
          id: 'file-123',
          name: 'test.txt',
          path: '/uploads/file-123.txt',
          size: 12,
          type: 'text/plain',
          category: 'document',
          hash: 'abc123',
          uploadedAt: '2026-08-19T10:00:00Z',
        },
      };

      vi.mocked(api.uploadFile).mockImplementation((_file, _convId, onProgress) => {
        if (onProgress) {
          onProgress(50);
          onProgress(100);
        }
        return Promise.resolve(mockResponse);
      });

      await useFileStore.getState().uploadFile(mockFile);

      // Progress should be updated during upload
      expect(useFileStore.getState().uploadProgress).toBe(0); // Reset after completion
    });

    it('sets loading state during upload', async () => {
      const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
      const mockResponse = {
        success: true,
        data: {
          id: 'file-123',
          name: 'test.txt',
          path: '/uploads/file-123.txt',
          size: 12,
          type: 'text/plain',
          category: 'document',
          hash: 'abc123',
          uploadedAt: '2026-08-19T10:00:00Z',
        },
      };

      vi.mocked(api.uploadFile).mockResolvedValue(mockResponse);

      const uploadPromise = useFileStore.getState().uploadFile(mockFile);

      // Loading should be true during upload
      expect(useFileStore.getState().isLoading).toBe(true);

      await uploadPromise;

      // Loading should be false after completion
      expect(useFileStore.getState().isLoading).toBe(false);
    });
  });

  describe('downloadFile', () => {
    it('downloads file successfully', async () => {
      const mockBlob = new Blob(['test content'], { type: 'text/plain' });
      vi.mocked(api.downloadFile).mockResolvedValue(mockBlob);

      const result = await useFileStore.getState().downloadFile('file-123');

      expect(result).toBe(mockBlob);
      expect(api.downloadFile).toHaveBeenCalledWith('file-123');
    });

    it('handles download failure', async () => {
      vi.mocked(api.downloadFile).mockResolvedValue(null);

      const result = await useFileStore.getState().downloadFile('file-123');

      expect(result).toBe(null);
    });
  });

  describe('removeFile', () => {
    it('removes file successfully', async () => {
      // Add a file first
      useFileStore.setState({
        files: [
          {
            id: 'file-123',
            name: 'test.txt',
            path: '/uploads/file-123.txt',
            size: 12,
            type: 'text/plain',
            category: 'document',
            hash: 'abc123',
            uploadedAt: '2026-08-19T10:00:00Z',
          },
        ],
      });

      vi.mocked(api.deleteFile).mockResolvedValue({ success: true });

      const result = await useFileStore.getState().removeFile('file-123');

      expect(result).toBe(true);
      expect(api.deleteFile).toHaveBeenCalledWith('file-123');
      expect(useFileStore.getState().files).toHaveLength(0);
    });

    it('handles remove failure', async () => {
      useFileStore.setState({
        files: [
          {
            id: 'file-123',
            name: 'test.txt',
            path: '/uploads/file-123.txt',
            size: 12,
            type: 'text/plain',
            category: 'document',
            hash: 'abc123',
            uploadedAt: '2026-08-19T10:00:00Z',
          },
        ],
      });

      vi.mocked(api.deleteFile).mockResolvedValue({ success: false, error: 'Delete failed' });

      const result = await useFileStore.getState().removeFile('file-123');

      expect(result).toBe(false);
      expect(useFileStore.getState().error).toBe('Delete failed');
      expect(useFileStore.getState().files).toHaveLength(1); // File still there
    });

    it('clears selectedFile when removing selected file', async () => {
      const file = {
        id: 'file-123',
        name: 'test.txt',
        path: '/uploads/file-123.txt',
        size: 12,
        type: 'text/plain',
        category: 'document',
        hash: 'abc123',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useFileStore.setState({
        files: [file],
        selectedFile: file,
      });

      vi.mocked(api.deleteFile).mockResolvedValue({ success: true });

      await useFileStore.getState().removeFile('file-123');

      expect(useFileStore.getState().selectedFile).toBe(null);
    });
  });

  describe('fetchFiles', () => {
    it('fetches all files', async () => {
      const mockResponse = {
        success: true,
        data: {
          files: [
            {
              id: 'file-1',
              name: 'test1.txt',
              path: '/uploads/file-1.txt',
              size: 10,
              type: 'text/plain',
              category: 'document',
              hash: 'hash1',
              uploadedAt: '2026-08-19T10:00:00Z',
            },
            {
              id: 'file-2',
              name: 'test2.txt',
              path: '/uploads/file-2.txt',
              size: 20,
              type: 'text/plain',
              category: 'document',
              hash: 'hash2',
              uploadedAt: '2026-08-19T11:00:00Z',
            },
          ],
          total: 2,
        },
      };

      vi.mocked(api.listFiles).mockResolvedValue(mockResponse);

      await useFileStore.getState().fetchFiles();

      expect(api.listFiles).toHaveBeenCalledWith(undefined);
      expect(useFileStore.getState().files).toHaveLength(2);
      expect(useFileStore.getState().files[0].id).toBe('file-1');
      expect(useFileStore.getState().files[1].id).toBe('file-2');
    });

    it('fetches files by conversation', async () => {
      const mockResponse = {
        success: true,
        data: {
          files: [
            {
              id: 'file-1',
              name: 'test1.txt',
              path: '/uploads/file-1.txt',
              size: 10,
              type: 'text/plain',
              category: 'document',
              hash: 'hash1',
              uploadedAt: '2026-08-19T10:00:00Z',
              conversationId: 'conv-1',
            },
          ],
          total: 1,
        },
      };

      vi.mocked(api.listFiles).mockResolvedValue(mockResponse);

      await useFileStore.getState().fetchFiles('conv-1');

      expect(api.listFiles).toHaveBeenCalledWith('conv-1');
      expect(useFileStore.getState().files).toHaveLength(1);
    });

    it('handles fetch failure', async () => {
      vi.mocked(api.listFiles).mockResolvedValue({
        success: false,
        error: 'Fetch failed',
      });

      await useFileStore.getState().fetchFiles();

      expect(useFileStore.getState().error).toBe('Fetch failed');
    });
  });

  describe('query methods', () => {
    beforeEach(() => {
      useFileStore.setState({
        files: [
          {
            id: 'file-1',
            name: 'test1.txt',
            path: '/uploads/file-1.txt',
            size: 10,
            type: 'text/plain',
            category: 'document',
            hash: 'hash1',
            uploadedAt: '2026-08-19T10:00:00Z',
            conversationId: 'conv-1',
          },
          {
            id: 'file-2',
            name: 'test2.jpg',
            path: '/uploads/file-2.jpg',
            size: 20,
            type: 'image/jpeg',
            category: 'image',
            hash: 'hash2',
            uploadedAt: '2026-08-19T11:00:00Z',
            conversationId: 'conv-2',
          },
          {
            id: 'file-3',
            name: 'test3.txt',
            path: '/uploads/file-3.txt',
            size: 30,
            type: 'text/plain',
            category: 'document',
            hash: 'hash3',
            uploadedAt: '2026-08-19T12:00:00Z',
            conversationId: 'conv-1',
          },
        ],
      });
    });

    it('getFilesByConversation filters correctly', () => {
      const files = useFileStore.getState().getFilesByConversation('conv-1');

      expect(files).toHaveLength(2);
      expect(files[0].id).toBe('file-1');
      expect(files[1].id).toBe('file-3');
    });

    it('getFilesByType filters correctly', () => {
      const files = useFileStore.getState().getFilesByType('text');

      expect(files).toHaveLength(2);
      expect(files[0].id).toBe('file-1');
      expect(files[1].id).toBe('file-3');
    });

    it('searchFiles searches by name', () => {
      const files = useFileStore.getState().searchFiles('test2');

      expect(files).toHaveLength(1);
      expect(files[0].id).toBe('file-2');
    });

    it('searchFiles is case-insensitive', () => {
      const files = useFileStore.getState().searchFiles('TEST');

      expect(files).toHaveLength(3);
    });
  });

  describe('utility methods', () => {
    it('setSelectedFile updates selected file', () => {
      const file = {
        id: 'file-1',
        name: 'test.txt',
        path: '/uploads/file-1.txt',
        size: 10,
        type: 'text/plain',
        category: 'document',
        hash: 'hash1',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useFileStore.getState().setSelectedFile(file);

      expect(useFileStore.getState().selectedFile).toBe(file);
    });

    it('clearFiles removes all files', () => {
      useFileStore.setState({
        files: [
          {
            id: 'file-1',
            name: 'test.txt',
            path: '/uploads/file-1.txt',
            size: 10,
            type: 'text/plain',
            category: 'document',
            hash: 'hash1',
            uploadedAt: '2026-08-19T10:00:00Z',
          },
        ],
        selectedFile: {
          id: 'file-1',
          name: 'test.txt',
          path: '/uploads/file-1.txt',
          size: 10,
          type: 'text/plain',
          category: 'document',
          hash: 'hash1',
          uploadedAt: '2026-08-19T10:00:00Z',
        },
      });

      useFileStore.getState().clearFiles();

      expect(useFileStore.getState().files).toHaveLength(0);
      expect(useFileStore.getState().selectedFile).toBe(null);
    });

    it('setError updates error state', () => {
      useFileStore.getState().setError('Test error');

      expect(useFileStore.getState().error).toBe('Test error');
    });

    it('setLoading updates loading state', () => {
      useFileStore.getState().setLoading(true);

      expect(useFileStore.getState().isLoading).toBe(true);
    });
  });
});
