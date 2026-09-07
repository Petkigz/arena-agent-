/** Shared presentation rules for existing file and attachment views. */
import { Archive, Code, File, FileText, Film, Image, Music } from 'lucide-react';
import type { AttachmentType } from '../stores/multiModalStore';

export function getAttachmentIcon(type: AttachmentType) {
  switch (type) {
    case 'image': return Image;
    case 'code': return Code;
    case 'video': return Film;
    case 'audio': return Music;
    default: return FileText;
  }
}

export function getFileIcon(type: string) {
  if (type.startsWith('image/')) return Image;
  if (type.startsWith('video/')) return Film;
  if (type.startsWith('audio/')) return Music;
  if (type.includes('pdf') || type.includes('document')) return FileText;
  if (type.includes('zip') || type.includes('archive')) return Archive;
  return File;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
