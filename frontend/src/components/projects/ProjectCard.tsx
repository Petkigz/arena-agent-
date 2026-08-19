import { useNavigate } from 'react-router-dom';
import { Card } from '../ui/Card';
import type { Project } from '../../stores/projectStore';
import { FolderKanban, Calendar, CheckCircle, Clock, AlertCircle } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface ProjectCardProps {
  project: Project;
}

export function ProjectCard({ project }: ProjectCardProps) {
  const navigate = useNavigate();

  const statusConfig = {
    active: { color: 'text-green-500', bg: 'bg-green-500/10', label: 'Active' },
    completed: { color: 'text-blue-500', bg: 'bg-blue-500/10', label: 'Completed' },
    archived: { color: 'text-gray-500', bg: 'bg-gray-500/10', label: 'Archived' },
    'on-hold': { color: 'text-yellow-500', bg: 'bg-yellow-500/10', label: 'On Hold' },
  };

  const status = statusConfig[project.status];
  const completedTasks = project.tasks.filter((t) => t.status === 'done').length;
  const totalTasks = project.tasks.length;
  const urgentTasks = project.tasks.filter((t) => t.priority === 'urgent' && t.status !== 'done').length;
  const overdueTasks = project.tasks.filter((t) => {
    if (!t.dueDate || t.status === 'done') return false;
    return new Date(t.dueDate) < new Date();
  }).length;

  return (
    <Card
      className="cursor-pointer transition-all hover:border-accent-primary hover:shadow-lg"
      onClick={() => navigate(`/projects/${project.id}`)}
    >
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3 flex-1">
            <div
              className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: project.color + '20' }}
            >
              <FolderKanban className="w-5 h-5" style={{ color: project.color }} />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-text-primary truncate">{project.name}</h3>
              {project.description && (
                <p className="text-sm text-text-secondary mt-1 line-clamp-2">
                  {project.description}
                </p>
              )}
            </div>
          </div>
          <span className={`px-2 py-1 rounded text-xs font-medium ${status.bg} ${status.color}`}>
            {status.label}
          </span>
        </div>

        {/* Progress */}
        {totalTasks > 0 && (
          <div>
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-text-secondary">Progress</span>
              <span className="text-text-primary font-medium">{project.progress}%</span>
            </div>
            <div className="w-full bg-background-surface rounded-full h-2">
              <div
                className="h-2 rounded-full transition-all"
                style={{ width: `${project.progress}%`, backgroundColor: project.color }}
              />
            </div>
            <p className="text-xs text-text-muted mt-1">
              {completedTasks} of {totalTasks} tasks completed
            </p>
          </div>
        )}

        {/* Stats */}
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1 text-text-secondary">
            <Calendar className="w-4 h-4" />
            <span>{formatDistanceToNow(new Date(project.updatedAt), { addSuffix: true })}</span>
          </div>
          {urgentTasks > 0 && (
            <div className="flex items-center gap-1 text-red-500">
              <AlertCircle className="w-4 h-4" />
              <span>{urgentTasks} urgent</span>
            </div>
          )}
          {overdueTasks > 0 && (
            <div className="flex items-center gap-1 text-orange-500">
              <Clock className="w-4 h-4" />
              <span>{overdueTasks} overdue</span>
            </div>
          )}
          {completedTasks === totalTasks && totalTasks > 0 && (
            <div className="flex items-center gap-1 text-green-500">
              <CheckCircle className="w-4 h-4" />
              <span>All done!</span>
            </div>
          )}
        </div>

        {/* Tags */}
        {project.tags && project.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {project.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 bg-background-surface text-text-muted text-xs rounded"
              >
                {tag}
              </span>
            ))}
            {project.tags.length > 3 && (
              <span className="px-2 py-0.5 bg-background-surface text-text-muted text-xs rounded">
                +{project.tags.length - 3}
              </span>
            )}
          </div>
        )}

        {/* Files and Conversations */}
        <div className="flex items-center gap-4 text-xs text-text-muted pt-2 border-t border-border">
          <span>{project.files.length} files</span>
          <span>{project.conversations.length} conversations</span>
        </div>
      </div>
    </Card>
  );
}
