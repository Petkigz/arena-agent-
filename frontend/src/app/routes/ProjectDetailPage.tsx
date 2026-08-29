import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useProjectStore } from '../../stores';
import type { Project } from '../../stores/projectStore';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { TaskBoard } from '../../components/projects/TaskBoard';
import { ProjectFiles } from '../../components/projects/ProjectFiles';
import { ProjectConversations } from '../../components/projects/ProjectConversations';
import { ArrowLeft, Trash2, Edit, FolderKanban, Layers, Cpu, Clock } from 'lucide-react';
import { getBackendProject, runProjectReadySteps, setProjectScheduler } from '../../services/api';
import { notifications } from '../../services/notifications';

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { projects, updateProject, deleteProject, loadProjectTasks } = useProjectStore();
  const [activeTab, setActiveTab] = useState<'tasks' | 'files' | 'conversations' | 'milestones'>('tasks');
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [backendDetail, setBackendDetail] = useState<{ project?: any; resume_context?: any; decomposition?: any } | null>(null);
  const [schedulerBusy, setSchedulerBusy] = useState(false);

  const project = projects.find((p) => p.id === projectId);

  // Fetch backend detail (milestones, resume_context, decomposition with resource-aware schedule)
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    getBackendProject(projectId).then((data) => {
      if (!cancelled && data) setBackendDetail(data);
    });
    // Pull the shared task list so the board reflects every UI's changes.
    loadProjectTasks(projectId);
    return () => { cancelled = true; };
  }, [projectId, loadProjectTasks]);

  const refreshBackendDetail = async () => {
    if (!projectId) return;
    const detail = await getBackendProject(projectId);
    if (detail) setBackendDetail(detail);
  };

  const toggleScheduler = async () => {
    if (!projectId) return;
    const enabled = !Boolean(backendDetail?.project?.context?.auto_schedule);
    setSchedulerBusy(true);
    const ok = await setProjectScheduler(projectId, enabled);
    if (ok) {
      await refreshBackendDetail();
      notifications.success(enabled ? 'Persistent DAG scheduling enabled' : 'Persistent DAG scheduling paused');
    } else {
      notifications.error('Could not update project scheduler');
    }
    setSchedulerBusy(false);
  };

  const runReadyStep = async () => {
    if (!projectId) return;
    setSchedulerBusy(true);
    const result = await runProjectReadySteps(projectId, 1);
    if (result) {
      await refreshBackendDetail();
      notifications.success(`Project scheduler: ${String(result.status || 'cycle complete')}`);
    } else {
      notifications.error('Could not run the next project step');
    }
    setSchedulerBusy(false);
  };

  if (!project) {
    return (
      <div className="h-full flex items-center justify-center bg-background-primary">
        <div className="text-center">
          <FolderKanban className="w-16 h-16 text-text-muted mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-text-primary mb-2">Project Not Found</h2>
          <p className="text-text-secondary mb-4">The project you're looking for doesn't exist.</p>
          <Button onClick={() => navigate('/projects')}>Back to Projects</Button>
        </div>
      </div>
    );
  }

  const handleDelete = () => {
    deleteProject(project.id);
    navigate('/projects');
  };

  const tabs = [
    { id: 'tasks', label: 'Tasks', count: project.tasks.length },
    { id: 'files', label: 'Files', count: project.files.length },
    { id: 'conversations', label: 'Conversations', count: project.conversations.length },
    { id: 'milestones', label: 'Milestones', count: backendDetail?.project?.milestones?.length || project.tasks.length },
  ];

  return (
    <div className="h-full flex flex-col bg-background-primary">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border">
        <div className="flex items-center gap-4 mb-4">
          <button
            onClick={() => navigate('/projects')}
            className="p-2 hover:bg-background-surface rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-text-secondary" />
          </button>
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: project.color + '20' }}
          >
            <FolderKanban className="w-5 h-5" style={{ color: project.color }} />
          </div>
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-text-primary">{project.name}</h1>
            {project.description && (
              <p className="text-sm text-text-secondary mt-1">{project.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => setShowEditModal(true)}
              variant="secondary"
              size="sm"
            >
              <Edit className="w-4 h-4 mr-2" />
              Edit
            </Button>
            <Button
              onClick={() => setShowDeleteConfirm(true)}
              variant="secondary"
              size="sm"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete
            </Button>
          </div>
        </div>

        {/* Progress */}
        {project.tasks.length > 0 && (
          <div className="mb-4">
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
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 border-b border-border">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                activeTab === tab.id
                  ? 'border-accent-primary text-accent-primary'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              {tab.label}
              <span className="ml-2 px-2 py-0.5 bg-background-surface rounded text-xs">
                {tab.count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'tasks' && <TaskBoard project={project} />}
        {activeTab === 'files' && <ProjectFiles project={project} />}
        {activeTab === 'conversations' && <ProjectConversations project={project} />}
        {activeTab === 'milestones' && (
          <div className="p-6 space-y-6">
            {backendDetail?.project?.context?.decomposition_id && (
              <div className="rounded border border-border bg-background-surface p-4">
                <h3 className="font-semibold text-text-primary">Persistent DAG Scheduler</h3>
                <p className="text-xs text-text-muted mt-1">
                  Runs one dependency-ready sub-goal per autonomous cycle through Owner Control, independent observation, and verification. Enable explicitly to avoid duplicating the foreground request.
                </p>
                <div className="flex flex-wrap gap-2 mt-3">
                  <Button onClick={toggleScheduler} disabled={schedulerBusy} variant="secondary" size="sm">
                    {backendDetail.project.context.auto_schedule ? 'Pause background scheduling' : 'Enable background scheduling'}
                  </Button>
                  <Button onClick={runReadyStep} disabled={schedulerBusy} size="sm">
                    Run next ready step
                  </Button>
                </div>
              </div>
            )}
            {/* Backend milestones (persistent project) */}
            {backendDetail?.project?.milestones ? (
              <div>
                <h3 className="text-lg font-semibold flex items-center gap-2"><Layers className="w-5 h-5" /> Persistent Milestones (backend)</h3>
                <p className="text-sm text-text-secondary mb-3">From ProjectManager — multi-session, resource-budgeted, with resume context</p>
                <div className="space-y-2">
                  {backendDetail.project.milestones.map((m: any, i: number) => (
                    <div key={m.id || i} className="flex items-center justify-between p-3 bg-background-surface rounded border border-border">
                      <span className="text-sm">{m.description || m}</span>
                      <span className={`text-xs px-2 py-1 rounded ${m.status === 'reached' ? 'bg-green-500/20 text-green-600' : 'bg-yellow-500/20 text-yellow-600'}`}>{m.status}</span>
                    </div>
                  ))}
                </div>
                {backendDetail.resume_context && (
                  <div className="mt-4 p-3 bg-background-secondary rounded border border-border">
                    <h4 className="font-medium text-sm">Resume Context</h4>
                    <p className="text-xs text-text-secondary">Progress: {backendDetail.resume_context.progress_percent}% — Total sessions: {backendDetail.resume_context.total_sessions}</p>
                    <p className="text-xs text-text-muted">Pending: {(backendDetail.resume_context.pending_milestones || []).slice(0,3).join(', ')}</p>
                  </div>
                )}
                {backendDetail.decomposition && (
                  <div className="mt-4 p-3 bg-background-secondary rounded border border-border">
                    <h4 className="font-medium text-sm flex items-center gap-2"><Cpu className="w-4 h-4" /> Resource-Aware Schedule</h4>
                    <p className="text-xs text-text-secondary">Progress: {backendDetail.decomposition.progress_percent}% — Total: {backendDetail.decomposition.total_sub_goals}, Completed: {backendDetail.decomposition.completed}, Blocked: {backendDetail.decomposition.blocked}</p>
                    <div className="mt-2 space-y-1">
                      {(backendDetail.decomposition.next_actions || []).slice(0,3).map((a: any, i: number) => (
                        <div key={i} className="text-xs flex items-center gap-2"><Clock className="w-3 h-3" /> {a.description} ({a.action_type})</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-text-muted">No backend milestones — this project is local-only. Complex goals auto-create persistent projects with milestones via cognitive runtime.</p>
            )}
          </div>
        )}
      </div>

      {/* Edit Modal */}
      <Modal
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        title="Edit Project"
      >
        <EditProjectForm
          project={project}
          onUpdate={(updates) => {
            updateProject(project.id, updates);
            setShowEditModal(false);
          }}
          onCancel={() => setShowEditModal(false)}
        />
      </Modal>

      {/* Delete Confirmation */}
      <Modal
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        title="Delete Project"
      >
        <div className="space-y-4">
          <p className="text-text-secondary">
            Are you sure you want to delete <strong>{project.name}</strong>? This action cannot be undone.
          </p>
          <div className="flex gap-3">
            <Button
              onClick={() => setShowDeleteConfirm(false)}
              variant="secondary"
              className="flex-1"
            >
              Cancel
            </Button>
            <Button
              onClick={handleDelete}
              variant="danger"
              className="flex-1"
            >
              Delete Project
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// Edit Project Form Component
function EditProjectForm({
  project,
  onUpdate,
  onCancel,
}: {
  project: Project;
  onUpdate: (updates: Partial<Project>) => void;
  onCancel: () => void;
}) {
  const [formData, setFormData] = useState({
    name: project.name,
    description: project.description || '',
    color: project.color,
    status: project.status,
  });

  const colors = [
    '#3b82f6', '#8b5cf6', '#ec4899', '#ef4444',
    '#f59e0b', '#10b981', '#06b6d4', '#6366f1',
  ];

  const handleSubmit = () => {
    if (!formData.name.trim()) return;
    onUpdate(formData);
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-text-primary mb-2">
          Project Name *
        </label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          className="w-full px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
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

      <div>
        <label className="block text-sm font-medium text-text-primary mb-2">
          Status
        </label>
        <select
          value={formData.status}
          onChange={(e) => setFormData({ ...formData, status: e.target.value as Project['status'] })}
          className="w-full px-4 py-2 bg-background-surface border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary"
        >
          <option value="active">Active</option>
          <option value="completed">Completed</option>
          <option value="on-hold">On Hold</option>
          <option value="archived">Archived</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-2">
          Color
        </label>
        <div className="flex gap-2">
          {colors.map((color) => (
            <button
              key={color}
              onClick={() => setFormData({ ...formData, color })}
              className={`w-8 h-8 rounded-lg transition-all ${
                formData.color === color ? 'ring-2 ring-offset-2 ring-offset-background-primary ring-accent-primary' : ''
              }`}
              style={{ backgroundColor: color }}
            />
          ))}
        </div>
      </div>

      <div className="flex gap-3 pt-4">
        <Button onClick={onCancel} variant="secondary" className="flex-1">
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!formData.name.trim()}
          className="flex-1"
        >
          Save Changes
        </Button>
      </div>
    </div>
  );
}
