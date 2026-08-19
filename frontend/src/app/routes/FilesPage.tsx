import { useState } from 'react';
import { FileUpload } from '../../components/ui/FileUpload';
import { FileBrowser } from '../../components/ui/FileBrowser';
import { FilePreview } from '../../components/ui/FilePreview';
import { useFileStore, type UploadedFile } from '../../stores/fileStore';

export function FilesPage() {
  const [previewFile, setPreviewFile] = useState<UploadedFile | null>(null);
  const { uploadFile, uploadProgress, isLoading, error } = useFileStore();

  const handleUpload = async (files: File[]) => {
    for (const file of files) {
      await uploadFile(file);
    }
  };

  return (
    <div className="h-full flex flex-col bg-background-primary">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border">
        <h1 className="text-2xl font-bold text-text-primary">Files</h1>
        <p className="text-text-secondary mt-1">Upload, browse, and manage your files</p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Upload section */}
        <div>
          <h2 className="text-lg font-semibold text-text-primary mb-3">Upload Files</h2>
          <FileUpload onUpload={handleUpload} />
          
          {/* Upload progress */}
          {isLoading && uploadProgress > 0 && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-text-secondary">Uploading...</span>
                <span className="text-sm text-text-secondary">{Math.round(uploadProgress)}%</span>
              </div>
              <div className="w-full bg-background-surface rounded-full h-2">
                <div 
                  className="bg-accent-primary h-2 rounded-full transition-all"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}
          
          {/* Error message */}
          {error && (
            <div className="mt-4 p-4 bg-accent-error/10 border border-accent-error rounded">
              <p className="text-sm text-accent-error">{error}</p>
            </div>
          )}
        </div>

        {/* Browser section */}
        <div>
          <h2 className="text-lg font-semibold text-text-primary mb-3">Your Files</h2>
          <FileBrowser onPreview={setPreviewFile} />
        </div>
      </div>

      {/* Preview modal */}
      {previewFile && (
        <FilePreview file={previewFile} onClose={() => setPreviewFile(null)} />
      )}
    </div>
  );
}
