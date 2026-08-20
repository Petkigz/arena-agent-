import { useState } from 'react';
import { Paperclip, X, Image, FileText, Code, Film, Music } from 'lucide-react';
import { Button } from './Button';
import { useMultiModalStore, type AttachmentType } from '../../stores/multiModalStore';

interface AttachmentButtonProps {
  onAttach: (files: File[]) => void;
  disabled?: boolean;
}

export function AttachmentButton({ onAttach, disabled }: AttachmentButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { pendingAttachments, removePendingAttachment } = useMultiModalStore();

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      onAttach(files);
      setIsOpen(false);
    }
    e.target.value = '';
  };

  const getAttachmentIcon = (type: AttachmentType) => {
    switch (type) {
      case 'image':
        return Image;
      case 'document':
        return FileText;
      case 'code':
        return Code;
      case 'video':
        return Film;
      case 'audio':
        return Music;
      default:
        return FileText;
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="relative">
      {/* Attachment button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        title="Attach files"
      >
        <Paperclip className="w-5 h-5" />
        {pendingAttachments.length > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 bg-accent-primary text-white text-xs rounded-full flex items-center justify-center">
            {pendingAttachments.length}
          </span>
        )}
      </Button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute bottom-full left-0 mb-2 w-80 bg-background-secondary border border-border rounded-lg shadow-lg z-50">
          <div className="p-3 border-b border-border">
            <h3 className="text-sm font-medium text-text-primary mb-2">Attach Files</h3>
            <label className="block">
              <input
                type="file"
                multiple
                onChange={handleFileSelect}
                className="hidden"
                accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt,.json,.js,.ts,.py,.xml,.yaml,.yml"
              />
              <Button
                variant="primary"
                size="sm"
                className="w-full"
                onClick={() => document.querySelector<HTMLInputElement>('input[type="file"]')?.click()}
              >
                <Paperclip className="w-4 h-4 mr-2" />
                Choose Files
              </Button>
            </label>
          </div>

          {/* Pending attachments */}
          {pendingAttachments.length > 0 && (
            <div className="p-3 max-h-64 overflow-y-auto">
              <h4 className="text-xs font-medium text-text-muted mb-2">
                Pending ({pendingAttachments.length})
              </h4>
              <div className="space-y-2">
                {pendingAttachments.map((attachment) => {
                  const Icon = getAttachmentIcon(attachment.type);
                  return (
                    <div
                      key={attachment.id}
                      className="flex items-center gap-2 p-2 bg-background-surface rounded"
                    >
                      {attachment.preview ? (
                        <img
                          src={attachment.preview}
                          alt={attachment.name}
                          className="w-10 h-10 object-cover rounded"
                        />
                      ) : (
                        <div className="w-10 h-10 bg-background-primary rounded flex items-center justify-center">
                          <Icon className="w-5 h-5 text-text-muted" />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-text-primary truncate">{attachment.name}</p>
                        <p className="text-xs text-text-muted">{formatSize(attachment.size)}</p>
                      </div>
                      <button
                        onClick={() => removePendingAttachment(attachment.id)}
                        className="p-1 hover:bg-background-primary rounded"
                      >
                        <X className="w-4 h-4 text-text-muted" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
