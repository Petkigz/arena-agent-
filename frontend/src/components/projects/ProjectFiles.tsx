import { useProjectStore, type Project } from '../../stores/projectStore';
import { FileText, Download, Trash2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { notifications } from '../../services/notifications';

interface ProjectFilesProps {
  project: Project;
}

export function ProjectFiles({ project }: ProjectFilesProps) {
  const { removeFile } = useProjectStore();

  const handleDelete = (fileId: string) => {
    if (confirm('Are you sure you want to remove this file from the project?')) {
      removeFile(project.id, fileId);
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (project.files.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <FileText className="w-16 h-16 text-text-muted mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-text-primary mb-2">No files yet</h3>
          <p className="text-text-secondary">
            Files attached to conversations will appear here
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="space-y-2">
        {project.files.map((file) => (
          <div
            key={file.id}
            className="flex items-center gap-4 p-4 bg-background-surface border border-border rounded-lg hover:border-accent-primary transition-colors"
          >
            <div className="w-10 h-10 bg-background-primary rounded-lg flex items-center justify-center flex-shrink-0">
              <FileText className="w-5 h-5 text-text-muted" />
            </div>

            <div className="flex-1 min-w-0">
              <h4 className="font-medium text-text-primary truncate">{file.name}</h4>
              <div className="flex items-center gap-3 text-sm text-text-muted mt-1">
                <span>{formatSize(file.size)}</span>
                <span>•</span>
                <span>{file.type}</span>
                <span>•</span>
                <span>{formatDistanceToNow(new Date(file.uploadedAt), { addSuffix: true })}</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  // In production, this would download the file
                  notifications.info('Download functionality would be implemented here');
                }}
                className="p-2 hover:bg-background-primary rounded-lg transition-colors"
              >
                <Download className="w-4 h-4 text-text-muted" />
              </button>
              <button
                onClick={() => handleDelete(file.id)}
                className="p-2 hover:bg-background-primary rounded-lg transition-colors"
              >
                <Trash2 className="w-4 h-4 text-text-muted" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
