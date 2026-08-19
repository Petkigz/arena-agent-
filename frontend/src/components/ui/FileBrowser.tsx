import { useState, useMemo } from 'react';
import { Search, File, Image, FileText, Film, Music, Archive, Trash2, Eye } from 'lucide-react';
import { Button } from './Button';
import { EmptyState } from './EmptyState';
import { useFileStore, type UploadedFile } from '../../stores/fileStore';

interface FileBrowserProps {
  conversationId?: string;
  onPreview?: (file: UploadedFile) => void;
}

export function FileBrowser({ conversationId, onPreview }: FileBrowserProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<string>('all');
  const { files, removeFile, setSelectedFile } = useFileStore();

  const filteredFiles = useMemo(() => {
    let result = conversationId
      ? files.filter((f) => f.conversationId === conversationId)
      : files;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter((f) => f.name.toLowerCase().includes(q));
    }

    if (filterType !== 'all') {
      result = result.filter((f) => f.type.startsWith(filterType));
    }

    return result;
  }, [files, conversationId, searchQuery, filterType]);

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

  const handleDelete = (id: string) => {
    if (confirm('Delete this file?')) {
      removeFile(id);
    }
  };

  const handlePreview = (file: UploadedFile) => {
    setSelectedFile(file);
    onPreview?.(file);
  };

  return (
    <div className="space-y-4">
      {/* Search and filters */}
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search files..."
            className="w-full pl-10 pr-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-sm"
          />
        </div>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary text-sm"
        >
          <option value="all">All Types</option>
          <option value="image">Images</option>
          <option value="video">Videos</option>
          <option value="audio">Audio</option>
          <option value="application/pdf">PDFs</option>
          <option value="text">Text</option>
        </select>
      </div>

      {/* File list */}
      {filteredFiles.length === 0 ? (
        <EmptyState
          icon={<File className="w-16 h-16" />}
          title={searchQuery ? 'No files match your search' : 'No files uploaded yet'}
          description={searchQuery ? 'Try a different search term' : 'Upload files to see them here'}
        />
      ) : (
        <div className="space-y-2">
          {filteredFiles.map((file) => {
            const Icon = getFileIcon(file.type);
            return (
              <div
                key={file.id}
                className="flex items-center gap-3 p-3 bg-background-surface rounded-lg hover:bg-background-surface/80 transition-colors group"
              >
                {/* Icon or preview */}
                <div className="flex-shrink-0">
                  {file.preview ? (
                    <img
                      src={file.preview}
                      alt={file.name}
                      className="w-12 h-12 object-cover rounded"
                    />
                  ) : (
                    <div className="w-12 h-12 bg-background-primary rounded flex items-center justify-center">
                      <Icon className="w-6 h-6 text-text-muted" />
                    </div>
                  )}
                </div>

                {/* File info */}
                <div className="flex-1 min-w-0">
                  <p className="text-text-primary font-medium truncate">{file.name}</p>
                  <div className="flex items-center gap-3 text-xs text-text-muted mt-1">
                    <span>{formatSize(file.size)}</span>
                    <span>•</span>
                    <span>{new Date(file.uploadedAt).toLocaleDateString()}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  {onPreview && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handlePreview(file)}
                    >
                      <Eye className="w-4 h-4" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(file.id)}
                  >
                    <Trash2 className="w-4 h-4 text-accent-error" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* File count */}
      {filteredFiles.length > 0 && (
        <p className="text-text-muted text-sm text-center">
          {filteredFiles.length} file{filteredFiles.length !== 1 ? 's' : ''}
        </p>
      )}
    </div>
  );
}
