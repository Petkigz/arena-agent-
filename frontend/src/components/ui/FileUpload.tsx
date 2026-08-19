import { useCallback, useState } from 'react';
import { Upload, File, X } from 'lucide-react';
import { Button } from './Button';
import { useFileStore } from '../../stores/fileStore';

interface FileUploadProps {
  onUpload: (files: File[]) => Promise<void>;
  accept?: string;
  multiple?: boolean;
  conversationId?: string;
}

export function FileUpload({
  onUpload,
  accept = '*',
  multiple = true,
  conversationId,
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const { error, setError } = useFileStore();

  const handleFiles = useCallback(
    async (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;

      const files = Array.from(fileList);

      setUploading(true);
      setError(null);

      try {
        await onUpload(files);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed');
      } finally {
        setUploading(false);
      }
    },
    [onUpload, setError, conversationId]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      handleFiles(e.target.files);
      e.target.value = ''; // Reset input
    },
    [handleFiles]
  );

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`
          border-2 border-dashed rounded-lg p-8 text-center transition-colors
          ${
            isDragging
              ? 'border-accent-primary bg-accent-primary/10'
              : 'border-border hover:border-accent-primary/50'
          }
        `}
      >
        <Upload className="w-12 h-12 text-text-muted mx-auto mb-3" />
        <p className="text-text-primary font-medium mb-2">
          {isDragging ? 'Drop files here' : 'Drag & drop files here'}
        </p>
        <p className="text-text-secondary text-sm mb-4">or</p>
        <label>
          <input
            type="file"
            accept={accept}
            multiple={multiple}
            onChange={handleInputChange}
            className="hidden"
            disabled={uploading}
            id="file-upload-input"
          />
          <Button
            variant="primary"
            onClick={() => (document.getElementById('file-upload-input') as HTMLInputElement)?.click()}
            disabled={uploading}
          >
            <File className="w-4 h-4 mr-2" />
            {uploading ? 'Uploading...' : 'Browse Files'}
          </Button>
        </label>
        <p className="text-text-muted text-xs mt-3">
          {multiple ? 'Multiple files allowed • All file types accepted' : 'All file types accepted'}
        </p>
      </div>

      {/* Error message */}
      {error && (
        <div className="bg-accent-error/10 border border-accent-error/30 rounded-lg p-3 flex items-start gap-2">
          <X className="w-5 h-5 text-accent-error flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-accent-error text-sm">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="text-accent-error hover:opacity-70">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
