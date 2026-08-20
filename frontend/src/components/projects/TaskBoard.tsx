import { useState } from 'react';
import { useProjectStore, type Project, type ProjectTask } from '../../stores/projectStore';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { Plus, Calendar, Flag, Trash2, Edit } from 'lucide-react';
import { format } from 'date-fns';

interface TaskBoardProps {
  project: Project;
}

export function TaskBoard({ project }: TaskBoardProps) {
  const { addTask, updateTask, deleteTask, moveTask } = useProjectStore();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingTask, setEditingTask] = useState<ProjectTask | null>(null);

  const columns = [
    { id: 'todo', label: 'To Do', color: 'border-gray-400' },
    { id: 'in-progress', label: 'In Progress', color: 'border-blue-400' },
    { id: 'done', label: 'Done', color: 'border-green-400' },
    { id: 'blocked', label: 'Blocked', color: 'border-red-400' },
  ];

  const priorityConfig = {
    low: { color: 'text-text-muted', bg: 'bg-background-surface/10', label: 'Low' },
    medium: { color: 'text-blue-500', bg: 'bg-blue-500/10', label: 'Medium' },
    high: { color: 'text-orange-500', bg: 'bg-orange-500/10', label: 'High' },
    urgent: { color: 'text-red-500', bg: 'bg-red-500/10', label: 'Urgent' },
  };

  const handleCreateTask = (taskData: Omit<ProjectTask, 'id' | 'createdAt' | 'updatedAt'>) => {
    addTask(project.id, taskData);
    setShowCreateModal(false);
  };

  const handleUpdateTask = (taskData: Partial<ProjectTask>) => {
    if (editingTask) {
      updateTask(project.id, editingTask.id, taskData);
      setEditingTask(null);
    }
  };

  const handleDeleteTask = (taskId: string) => {
    if (confirm('Are you sure you want to delete this task?')) {
      deleteTask(project.id, taskId);
    }
  };

  const handleMoveTask = (taskId: string, newStatus: ProjectTask['status']) => {
    moveTask(project.id, taskId, newStatus);
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-text-primary">Tasks</h2>
        <Button onClick={() => setShowCreateModal(true)} size="sm">
          <Plus className="w-4 h-4 mr-2" />
          Add Task
        </Button>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {columns.map((column) => {
          const tasks = project.tasks.filter((t) => t.status === column.id);

          return (
            <div key={column.id} className="space-y-3">
              {/* Column Header */}
              <div className={`border-l-4 ${column.color} pl-3 py-2`}>
                <h3 className="font-semibold text-text-primary">{column.label}</h3>
                <p className="text-sm text-text-muted">{tasks.length} tasks</p>
              </div>

              {/* Tasks */}
              <div className="space-y-2">
                {tasks.map((task) => {
                  const priority = priorityConfig[task.priority];
                  const isOverdue = task.dueDate && new Date(task.dueDate) < new Date() && task.status !== 'done';

                  return (
                    <div
                      key={task.id}
                      className="bg-background-surface border border-border rounded-lg p-3 hover:border-accent-primary transition-colors"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <h4 className="font-medium text-text-primary flex-1">{task.title}</h4>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => setEditingTask(task)}
                            className="p-1 hover:bg-background-primary rounded transition-colors"
                          >
                            <Edit className="w-3 h-3 text-text-muted" />
                          </button>
                          <button
                            onClick={() => handleDeleteTask(task.id)}
                            className="p-1 hover:bg-background-primary rounded transition-colors"
                          >
                            <Trash2 className="w-3 h-3 text-text-muted" />
                          </button>
                        </div>
                      </div>

                      {task.description && (
                        <p className="text-sm text-text-secondary mb-2 line-clamp-2">
                          {task.description}
                        </p>
                      )}

                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${priority.bg} ${priority.color}`}>
                          <Flag className="w-3 h-3 inline mr-1" />
                          {priority.label}
                        </span>

                        {task.dueDate && (
                          <span className={`text-xs ${isOverdue ? 'text-red-500' : 'text-text-muted'}`}>
                            <Calendar className="w-3 h-3 inline mr-1" />
                            {format(new Date(task.dueDate), 'MMM d')}
                          </span>
                        )}
                      </div>

                      {task.tags && task.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {task.tags.map((tag) => (
                            <span
                              key={tag}
                              className="px-2 py-0.5 bg-background-primary text-text-muted text-xs rounded"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Move buttons */}
                      <div className="flex gap-1 mt-3 pt-3 border-t border-border">
                        {columns
                          .filter((c) => c.id !== column.id)
                          .map((c) => (
                            <button
                              key={c.id}
                              onClick={() => handleMoveTask(task.id, c.id as 'todo' | 'in-progress' | 'done' | 'blocked')}
                              className="flex-1 px-2 py-1 text-xs bg-background-primary hover:bg-background-primary/80 rounded transition-colors"
                            >
                              → {c.label}
                            </button>
                          ))}
                      </div>
                    </div>
                  );
                })}

                {tasks.length === 0 && (
                  <div className="text-center py-8 text-text-muted text-sm">
                    No tasks
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Create Task Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create New Task"
      >
        <TaskForm
          onSubmit={handleCreateTask}
          onCancel={() => setShowCreateModal(false)}
        />
      </Modal>

      {/* Edit Task Modal */}
      <Modal
        isOpen={!!editingTask}
        onClose={() => setEditingTask(null)}
        title="Edit Task"
      >
        {editingTask && (
          <TaskForm
            task={editingTask}
            onSubmit={handleUpdateTask}
            onCancel={() => setEditingTask(null)}
          />
        )}
      </Modal>
    </div>
  );
}

// Task Form Component
function TaskForm({
  task,
  onSubmit,
  onCancel,
}: {
  task?: ProjectTask;
  onSubmit: (data: Omit<ProjectTask, 'id' | 'createdAt' | 'updatedAt'>) => void;
  onCancel: () => void;
}) {
  const [formData, setFormData] = useState<{
    title: string;
    description: string;
    status: 'todo' | 'in-progress' | 'done' | 'blocked';
    priority: 'low' | 'medium' | 'high' | 'urgent';
    dueDate: string;
    tags: string;
  }>({
    title: task?.title || '',
    description: task?.description || '',
    status: task?.status || 'todo',
    priority: task?.priority || 'medium',
    dueDate: task?.dueDate || '',
    tags: task?.tags?.join(', ') || '',
  });

  const handleSubmit = () => {
    if (!formData.title.trim()) return;

    const taskData = {
      ...formData,
      tags: formData.tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    };

    onSubmit(taskData);
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-text-primary mb-2">
          Title *
        </label>
        <input
          type="text"
          value={formData.title}
          onChange={(e) => setFormData({ ...formData, title: e.target.value })}
          className="w-full px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
          autoFocus
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-2">
          Description
        </label>
        <textarea
          value={formData.description}
          onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          rows={3}
          className="w-full px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary resize-none"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-text-primary mb-2">
            Status
          </label>
          <select
            value={formData.status}
            onChange={(e) => setFormData({ ...formData, status: e.target.value as 'todo' | 'in-progress' | 'done' | 'blocked' })}
            className="w-full px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
          >
            <option value="todo">To Do</option>
            <option value="in-progress">In Progress</option>
            <option value="done">Done</option>
            <option value="blocked">Blocked</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-text-primary mb-2">
            Priority
          </label>
          <select
            value={formData.priority}
            onChange={(e) => setFormData({ ...formData, priority: e.target.value as 'low' | 'medium' | 'high' | 'urgent' })}
            className="w-full px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="urgent">Urgent</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-2">
          Due Date
        </label>
        <input
          type="date"
          value={formData.dueDate}
          onChange={(e) => setFormData({ ...formData, dueDate: e.target.value })}
          className="w-full px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-2">
          Tags (comma-separated)
        </label>
        <input
          type="text"
          value={formData.tags}
          onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
          placeholder="e.g., frontend, bug, urgent"
          className="w-full px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
        />
      </div>

      <div className="flex gap-3 pt-4">
        <Button onClick={onCancel} variant="secondary" className="flex-1">
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!formData.title.trim()}
          className="flex-1"
        >
          {task ? 'Save Changes' : 'Create Task'}
        </Button>
      </div>
    </div>
  );
}
