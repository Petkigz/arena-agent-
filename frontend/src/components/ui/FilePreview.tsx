import { X, Download, Share2, File, Image, FileText, Film, Music, Archive } from 'lucide-react';
import { Button } from './Button';
import type { UploadedFile } from '../../stores/fileStore';

interface FilePreviewProps {
  file: UploadedFile;
  onClose: () => void;
}

export function FilePreview({ file, onClose }: FilePreviewProps) {
  const getFileIcon = (type: string) => {
    if (type.startsWith('image/')) return Image;
    if (type.startsWith('video/')) return Film;
    if (type.startsWith('audio/')) return Music;
    if (type.includes('pdf') || type.includes('document')) return FileText;
    if (type.includes('zip') || type.includes('archive')) return Archive;
    return File;
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleDownload = () => {
    // In a real implementation, this would download from the backend
    const link = document.createElement('a');
    link.href = file.path;
    link.download = file.name;
    link.click();
  };

  const handleShare = () => {
    // In a real implementation, this would open a share dialog
    if (navigator.share) {
      navigator.share({
        title: file.name,
        text: `Check out this file: ${file.name}`,
        url: file.path,
      });
    }
  };

  const renderPreview = () => {
    if (file.type.startsWith('image/')) {
      return (
        <div className="flex items-center justify-center p-8 bg-background-primary rounded-lg">
          {file.preview ? (
            <img
              src={file.preview}
              alt={file.name}
              className="max-w-full max-h-[60vh] object-contain rounded"
            />
          ) : (
            <Image className="w-32 h-32 text-text-muted" />
          )}
        </div>
      );
    }

    if (file.type.startsWith('video/')) {
      return (
        <div className="flex items-center justify-center p-8 bg-background-primary rounded-lg">
          <video controls className="max-w-full max-h-[60vh] rounded">
            <source src={file.path} type={file.type} />
            Your browser does not support video playback.
          </video>
        </div>
      );
    }

    if (file.type.startsWith('audio/')) {
      return (
        <div className="flex items-center justify-center p-8 bg-background-primary rounded-lg">
          <audio controls className="w-full">
            <source src={file.path} type={file.type} />
            Your browser does not support audio playback.
          </audio>
        </div>
      );
    }

    if (file.type.includes('pdf')) {
      return (
        <div className="flex items-center justify-center p-8 bg-background-primary rounded-lg h-[60vh]">
          <iframe
            src={file.path}
            className="w-full h-full rounded"
            title={file.name}
          />
        </div>
      );
    }

    if (file.type.startsWith('text/')) {
      return (
        <div className="flex items-center justify-center p-8 bg-background-primary rounded-lg h-[60vh]">
          <div className="w-full h-full overflow-auto p-4 font-mono text-sm text-text-primary whitespace-pre-wrap">
            {/* In a real implementation, this would fetch and display the file content */}
            <p className="text-text-muted">Text file preview not available in demo mode.</p>
            <p className="text-text-muted mt-2">File: {file.name}</p>
            <p className="text-text-muted">Size: {formatSize(file.size)}</p>
          </div>
        </div>
      );
    }

    // Default: show icon
    const Icon = getFileIcon(file.type);
    return (
      <div className="flex flex-col items-center justify-center p-8 bg-background-primary rounded-lg h-[60vh]">
        <Icon className="w-32 h-32 text-text-muted mb-4" />
        <p className="text-text-secondary">Preview not available for this file type</p>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-background-secondary rounded-lg max-w-5xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-semibold text-text-primary truncate">{file.name}</h2>
            <p className="text-sm text-text-muted mt-1">
              {formatSize(file.size)} • {file.type} • Uploaded{' '}
              {new Date(file.uploadedAt).toLocaleDateString()}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-background-surface rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-text-primary" />
          </button>
        </div>

        {/* Preview */}
        <div className="flex-1 overflow-auto p-4">{renderPreview()}</div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-4 border-t border-border">
          <Button variant="secondary" onClick={handleShare}>
            <Share2 className="w-4 h-4 mr-2" />
            Share
          </Button>
          <Button variant="primary" onClick={handleDownload}>
            <Download className="w-4 h-4 mr-2" />
            Download
          </Button>
        </div>
      </div>
    </div>
  );
}
