import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  listBackendProjectsPage,
  createBackendProject,
  listBackendProjectTasks,
  createBackendProjectTask,
  updateBackendProjectTask,
  deleteBackendProjectTask,
} from '../services/api';

export interface ProjectTask {
  id: string;
  title: string;
  description?: string;
  status: 'todo' | 'in-progress' | 'done' | 'blocked';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  assignee?: string;
  dueDate?: string;
  tags?: string[];
  createdAt: string;
  updatedAt: string;
  completedAt?: string;
}

export interface ProjectFile {
  id: string;
  name: string;
  path: string;
  type: string;
  size: number;
  uploadedAt: string;
  uploadedBy?: string;
}

export interface ProjectConversation {
  id: string;
  title: string;
  messageCount: number;
  lastActivity: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  color: string;
  icon?: string;
  status: 'active' | 'completed' | 'archived' | 'on-hold';
  progress: number; // 0-100
  tasks: ProjectTask[];
  files: ProjectFile[];
  conversations: ProjectConversation[];
  tags?: string[];
  createdAt: string;
  updatedAt: string;
  startDate?: string;
  endDate?: string;
  completedAt?: string;
}

interface ProjectStoreState {
  projects: Project[];
  currentProject: Project | null;
  isLoading: boolean;
  error: string | null;
  backendHasMore: boolean;
  backendNextOffset: number | null;

  // Project actions
  createProject: (project: Omit<Project, 'id' | 'createdAt' | 'updatedAt' | 'tasks' | 'files' | 'conversations'>) => string;
  updateProject: (id: string, updates: Partial<Project>) => void;
  deleteProject: (id: string) => void;
  setCurrentProject: (project: Project | null) => void;

  // Task actions (server-backed: every mutation syncs to the shared store so
  // tasks follow the owner across web/desktop/Android)
  addTask: (projectId: string, task: Omit<ProjectTask, 'id' | 'createdAt' | 'updatedAt'>) => string;
  updateTask: (projectId: string, taskId: string, updates: Partial<ProjectTask>) => void;
  deleteTask: (projectId: string, taskId: string) => void;
  moveTask: (projectId: string, taskId: string, newStatus: ProjectTask['status']) => void;
  loadProjectTasks: (projectId: string) => Promise<void>;

  // File actions
  addFile: (projectId: string, file: Omit<ProjectFile, 'id' | 'uploadedAt'>) => string;
  removeFile: (projectId: string, fileId: string) => void;

  // Conversation actions
  addConversation: (projectId: string, conversation: Omit<ProjectConversation, 'lastActivity'>) => void;
  updateConversation: (projectId: string, conversationId: string, updates: Partial<ProjectConversation>) => void;

  // Utility
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  getProjectProgress: (projectId: string) => number;
  hydrateFromBackend: () => Promise<void>;
  loadMoreBackendProjects: () => Promise<void>;
  createProjectBackend: (name: string, description?: string, priority?: string, milestones?: string[], tags?: string[]) => Promise<string | null>;
}

export const useProjectStore = create<ProjectStoreState>()(
  persist(
    (set, get) => ({
      projects: [],
      currentProject: null,
      isLoading: false,
      error: null,
      backendHasMore: false,
      backendNextOffset: null,

      createProject: (projectData) => {
        const id = `proj-${Date.now()}`;
        const now = new Date().toISOString();
        const project: Project = {
          ...projectData,
          id,
          tasks: [],
          files: [],
          conversations: [],
          createdAt: now,
          updatedAt: now,
        };

        set((state) => ({
          projects: [...state.projects, project],
        }));

        return id;
      },

      updateProject: (id, updates) =>
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === id ? { ...p, ...updates, updatedAt: new Date().toISOString() } : p
          ),
          currentProject:
            state.currentProject?.id === id
              ? { ...state.currentProject, ...updates, updatedAt: new Date().toISOString() }
              : state.currentProject,
        })),

      deleteProject: (id) =>
        set((state) => ({
          projects: state.projects.filter((p) => p.id !== id),
          currentProject: state.currentProject?.id === id ? null : state.currentProject,
        })),

      setCurrentProject: (project) => set({ currentProject: project }),

      addTask: (projectId, taskData) => {
        const taskId = `task-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
        const now = new Date().toISOString();
        const task: ProjectTask = {
          ...taskData,
          id: taskId,
          createdAt: now,
          updatedAt: now,
        };

        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId
              ? { ...p, tasks: [...p.tasks, task], updatedAt: now }
              : p
          ),
          currentProject:
            state.currentProject?.id === projectId
              ? { ...state.currentProject, tasks: [...state.currentProject.tasks, task], updatedAt: now }
              : state.currentProject,
        }));

        // Sync to the server (client-supplied id keeps every UI's copy
        // matched). Local state stays as the optimistic fallback when offline.
        void createBackendProjectTask(projectId, {
          id: taskId,
          title: task.title,
          description: task.description || '',
          status: task.status,
          priority: task.priority,
          assignee: task.assignee || '',
          dueDate: task.dueDate || '',
          tags: task.tags || [],
        });

        return taskId;
      },

      updateTask: (projectId, taskId, updates) => {
        const now = new Date().toISOString();
        const completedAt = updates.status === 'done' ? now : undefined;

        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId
              ? {
                  ...p,
                  tasks: p.tasks.map((t) =>
                    t.id === taskId ? { ...t, ...updates, updatedAt: now, completedAt } : t
                  ),
                  updatedAt: now,
                }
              : p
          ),
          currentProject:
            state.currentProject?.id === projectId
              ? {
                  ...state.currentProject,
                  tasks: state.currentProject.tasks.map((t) =>
                    t.id === taskId ? { ...t, ...updates, updatedAt: now, completedAt } : t
                  ),
                  updatedAt: now,
                }
              : state.currentProject,
        }));

        void updateBackendProjectTask(projectId, taskId, {
          ...updates,
          ...(completedAt ? { completedAt } : {}),
        });
      },

      deleteTask: (projectId, taskId) => {
        const now = new Date().toISOString();
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId
              ? { ...p, tasks: p.tasks.filter((t) => t.id !== taskId), updatedAt: now }
              : p
          ),
          currentProject:
            state.currentProject?.id === projectId
              ? { ...state.currentProject, tasks: state.currentProject.tasks.filter((t) => t.id !== taskId), updatedAt: now }
              : state.currentProject,
        }));

        void deleteBackendProjectTask(projectId, taskId);
      },

      loadProjectTasks: async (projectId) => {
        const tasks = await listBackendProjectTasks(projectId);
        if (!tasks.length) return;
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId ? { ...p, tasks: tasks as unknown as ProjectTask[] } : p
          ),
          currentProject:
            state.currentProject?.id === projectId
              ? { ...state.currentProject, tasks: tasks as unknown as ProjectTask[] }
              : state.currentProject,
        }));
      },

      moveTask: (projectId, taskId, newStatus) => {
        const now = new Date().toISOString();
        const completedAt = newStatus === 'done' ? now : undefined;

        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId
              ? {
                  ...p,
                  tasks: p.tasks.map((t) =>
                    t.id === taskId ? { ...t, status: newStatus, updatedAt: now, completedAt } : t
                  ),
                  updatedAt: now,
                }
              : p
          ),
          currentProject:
            state.currentProject?.id === projectId
              ? {
                  ...state.currentProject,
                  tasks: state.currentProject.tasks.map((t) =>
                    t.id === taskId ? { ...t, status: newStatus, updatedAt: now, completedAt } : t
                  ),
                  updatedAt: now,
                }
              : state.currentProject,
        }));

        // Status moves sync to the server so the board matches on every UI.
        void updateBackendProjectTask(projectId, taskId, {
          status: newStatus,
          ...(completedAt ? { completedAt } : {}),
        });
      },

      addFile: (projectId, fileData) => {
        const fileId = `file-${Date.now()}`;
        const now = new Date().toISOString();
        const file: ProjectFile = {
          ...fileData,
          id: fileId,
          uploadedAt: now,
        };

        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId
              ? { ...p, files: [...p.files, file], updatedAt: now }
              : p
          ),
          currentProject:
            state.currentProject?.id === projectId
              ? { ...state.currentProject, files: [...state.currentProject.files, file], updatedAt: now }
              : state.currentProject,
        }));

        return fileId;
      },

      removeFile: (projectId, fileId) => {
        const now = new Date().toISOString();
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId
              ? { ...p, files: p.files.filter((f) => f.id !== fileId), updatedAt: now }
              : p
          ),
          currentProject:
            state.currentProject?.id === projectId
              ? { ...state.currentProject, files: state.currentProject.files.filter((f) => f.id !== fileId), updatedAt: now }
              : state.currentProject,
        }));
      },

      addConversation: (projectId, conversationData) => {
        const now = new Date().toISOString();
        const conversation: ProjectConversation = {
          ...conversationData,
          lastActivity: now,
        };

        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId
              ? { ...p, conversations: [...p.conversations, conversation], updatedAt: now }
              : p
          ),
          currentProject:
            state.currentProject?.id === projectId
              ? { ...state.currentProject, conversations: [...state.currentProject.conversations, conversation], updatedAt: now }
              : state.currentProject,
        }));
      },

      updateConversation: (projectId, conversationId, updates) => {
        const now = new Date().toISOString();
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId
              ? {
                  ...p,
                  conversations: p.conversations.map((c) =>
                    c.id === conversationId ? { ...c, ...updates, lastActivity: now } : c
                  ),
                  updatedAt: now,
                }
              : p
          ),
          currentProject:
            state.currentProject?.id === projectId
              ? {
                  ...state.currentProject,
                  conversations: state.currentProject.conversations.map((c) =>
                    c.id === conversationId ? { ...c, ...updates, lastActivity: now } : c
                  ),
                  updatedAt: now,
                }
              : state.currentProject,
        }));
      },

      setLoading: (loading) => set({ isLoading: loading }),
      setError: (error) => set({ error }),

      getProjectProgress: (projectId) => {
        const state = get();
        const project = state.projects.find((p) => p.id === projectId);
        if (!project || project.tasks.length === 0) return 0;

        const completedTasks = project.tasks.filter((t) => t.status === 'done').length;
        return Math.round((completedTasks / project.tasks.length) * 100);
      },

      hydrateFromBackend: async () => {
        set({ isLoading: true });
        try {
          const page = await listBackendProjectsPage(0, 50);
          set((state) => {
            const existingById = new Map(state.projects.map((p) => [p.id, p]));
            const merged: Project[] = page.projects.map((bp) => {
              const existing = existingById.get(bp.project_id) || existingById.get(bp.project_id.replace('proj-','')) as any;
              if (existing) {
                return { ...existing, name: bp.name, description: bp.description, status: (bp.status as any) || existing.status, progress: Math.round(bp.progress_percent), updatedAt: bp.updated_at };
              }
              return {
                id: bp.project_id, name: bp.name, description: bp.description,
                color: '#3b82f6', status: (bp.status as any) || 'active',
                progress: Math.round(bp.progress_percent), tasks: [], files: [], conversations: [],
                tags: bp.tags, createdAt: bp.created_at, updatedAt: bp.updated_at,
              };
            });
            const backendIds = new Set(page.projects.map((bp) => bp.project_id));
            // Locally-created fallback IDs are explicitly prefixed. Do not keep
            // stale backend pages from persisted browser state, or pagination
            // would silently rehydrate the entire old collection.
            const localOnly = state.projects.filter(
              (p) => p.id.startsWith('proj-') && !backendIds.has(p.id)
            );
            return {
              projects: [...merged, ...localOnly],
              backendHasMore: page.has_more,
              backendNextOffset: page.next_offset,
              isLoading: false,
            };
          });
        } catch {
          set({ isLoading: false });
        }
      },

      loadMoreBackendProjects: async () => {
        const { backendHasMore, backendNextOffset, isLoading } = get();
        if (!backendHasMore || backendNextOffset === null || isLoading) return;
        set({ isLoading: true });
        try {
          const page = await listBackendProjectsPage(backendNextOffset, 50);
          set((state) => {
            const existingIds = new Set(state.projects.map((project) => project.id));
            const additional: Project[] = page.projects
              .filter((bp) => !existingIds.has(bp.project_id))
              .map((bp) => ({
                id: bp.project_id, name: bp.name, description: bp.description,
                color: '#3b82f6', status: (bp.status as any) || 'active',
                progress: Math.round(bp.progress_percent), tasks: [], files: [], conversations: [],
                tags: bp.tags, createdAt: bp.created_at, updatedAt: bp.updated_at,
              }));
            return {
              projects: [...state.projects, ...additional],
              backendHasMore: page.has_more,
              backendNextOffset: page.next_offset,
              isLoading: false,
            };
          });
        } catch {
          set({ isLoading: false });
        }
      },

      createProjectBackend: async (name, description, priority, milestones, tags) => {
        try {
          const res = await createBackendProject(name, description || '', priority || 'normal', milestones, tags);
          if (res?.project_id) {
            // Optimistically add
            const now = new Date().toISOString();
            const proj: Project = {
              id: res.project_id,
              name,
              description,
              color: '#3b82f6',
              status: 'active',
              progress: 0,
              tasks: [],
              files: [],
              conversations: [],
              tags,
              createdAt: now,
              updatedAt: now,
            };
            set((state) => ({ projects: [proj, ...state.projects] }));
            return res.project_id;
          }
          return null;
        } catch {
          return null;
        }
      },
    }),
    {
      name: 'arena-projects',
    }
  )
);
