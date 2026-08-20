import { describe, it, expect, beforeEach } from 'vitest';
import { useMultiModalStore } from '../../stores/multiModalStore';

describe('multiModalStore', () => {
  beforeEach(() => {
    useMultiModalStore.setState({
      attachments: [],
      pendingAttachments: [],
      isLoading: false,
      error: null,
    });
  });

  describe('attachment management', () => {
    it('adds an attachment', () => {
      const attachment = {
        id: 'attach-1',
        type: 'image' as const,
        name: 'test.jpg',
        path: '/uploads/attach-1.jpg',
        size: 1024,
        mimeType: 'image/jpeg',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useMultiModalStore.getState().addAttachment(attachment);

      expect(useMultiModalStore.getState().attachments).toHaveLength(1);
      expect(useMultiModalStore.getState().attachments[0].id).toBe('attach-1');
      expect(useMultiModalStore.getState().attachments[0].name).toBe('test.jpg');
    });

    it('removes an attachment', () => {
      const attachment = {
        id: 'attach-1',
        type: 'image' as const,
        name: 'test.jpg',
        path: '/uploads/attach-1.jpg',
        size: 1024,
        mimeType: 'image/jpeg',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useMultiModalStore.setState({ attachments: [attachment] });

      useMultiModalStore.getState().removeAttachment('attach-1');

      expect(useMultiModalStore.getState().attachments).toHaveLength(0);
    });

    it('sets attachment analysis', () => {
      const attachment = {
        id: 'attach-1',
        type: 'image' as const,
        name: 'test.jpg',
        path: '/uploads/attach-1.jpg',
        size: 1024,
        mimeType: 'image/jpeg',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useMultiModalStore.setState({ attachments: [attachment] });

      const analysis = {
        type: 'vision' as const,
        content: 'This is a test image showing a cat.',
        confidence: 0.95,
        analyzedAt: '2026-08-19T10:01:00Z',
      };

      useMultiModalStore.getState().setAttachmentAnalysis('attach-1', analysis);

      const updated = useMultiModalStore.getState().attachments[0];
      expect(updated.analysis?.type).toBe('vision');
      expect(updated.analysis?.content).toBe('This is a test image showing a cat.');
      expect(updated.analysis?.confidence).toBe(0.95);
    });
  });

  describe('pending attachments', () => {
    it('adds a pending attachment', () => {
      const file = new File(['test content'], 'test.txt', { type: 'text/plain' });
      const attachment = {
        id: 'pending-1',
        type: 'document' as const,
        name: 'test.txt',
        path: '',
        size: 12,
        mimeType: 'text/plain',
        uploadedAt: '2026-08-19T10:00:00Z',
        file,
      };

      useMultiModalStore.getState().addPendingAttachment(attachment);

      expect(useMultiModalStore.getState().pendingAttachments).toHaveLength(1);
      expect(useMultiModalStore.getState().pendingAttachments[0].id).toBe('pending-1');
      expect(useMultiModalStore.getState().pendingAttachments[0].file).toBe(file);
    });

    it('removes a pending attachment', () => {
      const attachment = {
        id: 'pending-1',
        type: 'document' as const,
        name: 'test.txt',
        path: '',
        size: 12,
        mimeType: 'text/plain',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useMultiModalStore.setState({ pendingAttachments: [attachment] });

      useMultiModalStore.getState().removePendingAttachment('pending-1');

      expect(useMultiModalStore.getState().pendingAttachments).toHaveLength(0);
    });

    it('clears all pending attachments', () => {
      const attachments = [
        {
          id: 'pending-1',
          type: 'document' as const,
          name: 'test1.txt',
          path: '',
          size: 12,
          mimeType: 'text/plain',
          uploadedAt: '2026-08-19T10:00:00Z',
        },
        {
          id: 'pending-2',
          type: 'image' as const,
          name: 'test2.jpg',
          path: '',
          size: 1024,
          mimeType: 'image/jpeg',
          uploadedAt: '2026-08-19T10:00:00Z',
        },
      ];

      useMultiModalStore.setState({ pendingAttachments: attachments });

      useMultiModalStore.getState().clearPendingAttachments();

      expect(useMultiModalStore.getState().pendingAttachments).toHaveLength(0);
    });
  });

  describe('query methods', () => {
    beforeEach(() => {
      const attachments = [
        {
          id: 'attach-1',
          type: 'image' as const,
          name: 'test1.jpg',
          path: '/uploads/attach-1.jpg',
          size: 1024,
          mimeType: 'image/jpeg',
          uploadedAt: '2026-08-19T10:00:00Z',
          analysis: {
            type: 'vision' as const,
            content: 'Image 1 analysis',
            analyzedAt: '2026-08-19T10:01:00Z',
          },
        },
        {
          id: 'attach-2',
          type: 'document' as const,
          name: 'test2.pdf',
          path: '/uploads/attach-2.pdf',
          size: 2048,
          mimeType: 'application/pdf',
          uploadedAt: '2026-08-19T11:00:00Z',
        },
        {
          id: 'attach-3',
          type: 'image' as const,
          name: 'test3.png',
          path: '/uploads/attach-3.png',
          size: 512,
          mimeType: 'image/png',
          uploadedAt: '2026-08-19T12:00:00Z',
        },
      ];

      useMultiModalStore.setState({ attachments });
    });

    it('getAttachmentsByType filters by type', () => {
      const images = useMultiModalStore.getState().getAttachmentsByType('image');

      expect(images).toHaveLength(2);
      expect(images[0].id).toBe('attach-1');
      expect(images[1].id).toBe('attach-3');
    });

    it('getAnalyzedAttachments returns only analyzed attachments', () => {
      const analyzed = useMultiModalStore.getState().getAnalyzedAttachments();

      expect(analyzed).toHaveLength(1);
      expect(analyzed[0].id).toBe('attach-1');
      expect(analyzed[0].analysis?.type).toBe('vision');
    });
  });

  describe('utility methods', () => {
    it('setLoading updates loading state', () => {
      useMultiModalStore.getState().setLoading(true);

      expect(useMultiModalStore.getState().isLoading).toBe(true);
    });

    it('setError updates error state', () => {
      useMultiModalStore.getState().setError('Test error');

      expect(useMultiModalStore.getState().error).toBe('Test error');
    });
  });

  describe('attachment types', () => {
    it('handles image attachments', () => {
      const attachment = {
        id: 'attach-1',
        type: 'image' as const,
        name: 'test.jpg',
        path: '/uploads/attach-1.jpg',
        size: 1024,
        mimeType: 'image/jpeg',
        uploadedAt: '2026-08-19T10:00:00Z',
        preview: 'data:image/jpeg;base64,/9j/4AAQSkZJRg...',
      };

      useMultiModalStore.getState().addAttachment(attachment);

      const stored = useMultiModalStore.getState().attachments[0];
      expect(stored.type).toBe('image');
      expect(stored.preview).toBeDefined();
    });

    it('handles document attachments', () => {
      const attachment = {
        id: 'attach-2',
        type: 'document' as const,
        name: 'test.pdf',
        path: '/uploads/attach-2.pdf',
        size: 2048,
        mimeType: 'application/pdf',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useMultiModalStore.getState().addAttachment(attachment);

      const stored = useMultiModalStore.getState().attachments[0];
      expect(stored.type).toBe('document');
    });

    it('handles code attachments', () => {
      const attachment = {
        id: 'attach-3',
        type: 'code' as const,
        name: 'test.py',
        path: '/uploads/attach-3.py',
        size: 512,
        mimeType: 'text/x-python',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useMultiModalStore.getState().addAttachment(attachment);

      const stored = useMultiModalStore.getState().attachments[0];
      expect(stored.type).toBe('code');
    });

    it('handles video attachments', () => {
      const attachment = {
        id: 'attach-4',
        type: 'video' as const,
        name: 'test.mp4',
        path: '/uploads/attach-4.mp4',
        size: 10485760,
        mimeType: 'video/mp4',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useMultiModalStore.getState().addAttachment(attachment);

      const stored = useMultiModalStore.getState().attachments[0];
      expect(stored.type).toBe('video');
    });

    it('handles audio attachments', () => {
      const attachment = {
        id: 'attach-5',
        type: 'audio' as const,
        name: 'test.mp3',
        path: '/uploads/attach-5.mp3',
        size: 5242880,
        mimeType: 'audio/mpeg',
        uploadedAt: '2026-08-19T10:00:00Z',
      };

      useMultiModalStore.getState().addAttachment(attachment);

      const stored = useMultiModalStore.getState().attachments[0];
      expect(stored.type).toBe('audio');
    });
  });
});
