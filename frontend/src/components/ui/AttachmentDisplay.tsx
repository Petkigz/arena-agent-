import { getAttachmentIcon, formatFileSize } from '../../utils/filePresentation';
import { Eye, Download } from 'lucide-react';
import { Button } from './Button';
import type { Attachment } from '../../stores/multiModalStore';

interface AttachmentDisplayProps {
  attachments: Attachment[];
  onPreview?: (attachment: Attachment) => void;
}

export function AttachmentDisplay({ attachments, onPreview }: AttachmentDisplayProps) {
  if (attachments.length === 0) return null;


  return (
    <div className="mt-3 space-y-2">
      {attachments.map((attachment) => {
        const Icon = getAttachmentIcon(attachment.type);

        return (
          <div
            key={attachment.id}
            className="flex items-center gap-3 p-3 bg-background-surface rounded-lg border border-border"
          >
            {/* Preview or icon */}
            {attachment.type === 'image' && attachment.preview ? (
              <img
                src={attachment.preview}
                alt={attachment.name}
                className="w-16 h-16 object-cover rounded"
              />
            ) : (
              <div className="w-16 h-16 bg-background-primary rounded flex items-center justify-center">
                <Icon className="w-8 h-8 text-text-muted" />
              </div>
            )}

            {/* Info */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary truncate">{attachment.name}</p>
              <div className="flex items-center gap-2 text-xs text-text-muted mt-1">
                <span>{formatFileSize(attachment.size)}</span>
                <span>•</span>
                <span>{attachment.type}</span>
                {attachment.analysis && (
                  <>
                    <span>•</span>
                    <span className="text-accent-success">Analyzed</span>
                  </>
                )}
              </div>

              {/* Analysis preview */}
              {attachment.analysis && (
                <div className="mt-2 p-2 bg-background-primary rounded text-xs text-text-secondary max-h-20 overflow-hidden">
                  <p className="line-clamp-3">{attachment.analysis.content}</p>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2">
              {onPreview && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onPreview(attachment)}
                  title="Preview"
                >
                  <Eye className="w-4 h-4" />
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  // In production, this would download from backend
                  const link = document.createElement('a');
                  link.href = attachment.path;
                  link.download = attachment.name;
                  link.click();
                }}
                title="Download"
              >
                <Download className="w-4 h-4" />
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
