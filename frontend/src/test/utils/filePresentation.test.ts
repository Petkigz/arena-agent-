import { describe, expect, it } from 'vitest';
import { Archive, Code, File, FileText, Film, Image, Music } from 'lucide-react';
import { formatFileSize, getAttachmentIcon, getFileIcon } from '../../utils/filePresentation';

describe('shared file presentation', () => {
  it('preserves the previous byte/KB/MB formatting boundaries', () => {
    expect(formatFileSize(0)).toBe('0 B');
    expect(formatFileSize(1023)).toBe('1023 B');
    expect(formatFileSize(1024)).toBe('1.0 KB');
    expect(formatFileSize(1024 * 1024)).toBe('1.0 MB');
  });

  it('keeps MIME and attachment-category mappings distinct but canonical', () => {
    expect(getAttachmentIcon('image')).toBe(Image);
    expect(getAttachmentIcon('code')).toBe(Code);
    expect(getAttachmentIcon('document')).toBe(FileText);
    expect(getAttachmentIcon('video')).toBe(Film);
    expect(getAttachmentIcon('audio')).toBe(Music);
    expect(getFileIcon('application/zip')).toBe(Archive);
    expect(getFileIcon('application/pdf')).toBe(FileText);
    expect(getFileIcon('application/octet-stream')).toBe(File);
  });
});
