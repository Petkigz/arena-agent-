import { logger } from './logger';
/**
 * API service for communicating with Arena backend.
 */

/**
 * Backend origin for HTTP calls. Mirrors websocket.ts (`ws://${hostname}:8000`):
 * works under `vite dev` (localhost:5173 → localhost:8000) AND when the built
 * SPA is served by the backend itself on any host (LAN/Android), where a
 * hardcoded "localhost:8000" would break every request.
 */
const API_BASE_URL = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;

/**
 * Turn a root-relative backend path (e.g. '/loras/status') into an absolute URL.
 * Use this everywhere instead of a bare fetch('/…'), which only works when the
 * page is served from the backend origin and silently 404s under `vite dev`.
 */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

/**
 * The API key the WebSocket uses (VITE_API_KEY), reused for HTTP so every
 * request is authenticated the same way when ARENA_API_KEY is enabled on the
 * backend. When unset (localhost default), this is an empty string and no
 * header is sent — matching the backend's auth-disabled mode.
 */
function apiKeyHeader(): Record<string, string> {
  const apiKey = import.meta.env.VITE_API_KEY;
  return apiKey ? { 'X-API-Key': apiKey } : {};
}

/** Exported for other API-calling modules (e.g. wakeWordStore) to stay in sync. */
export { apiKeyHeader };

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface PiperVoice {
  id: string;
  name: string;
  language: string;
  region: string | null;
  quality: string;
  path: string;
  has_config: boolean;
  active?: boolean;
}

/**
 * List Piper voice models discovered on the backend (scans ~/piper_models,
 * ~/.local/share/piper, ARENA_PIPER_MODEL_DIR, and the piper-tts package dir).
 */
export async function listPiperVoices(): Promise<PiperVoice[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/voice/piper-voices`, { headers: apiKeyHeader() });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data?.voices) ? (data.voices as PiperVoice[]) : [];
  } catch {
    return [];
  }
}

/**
 * Persist the active Piper voice on the backend (drives /voice/synthesize and
 * the running voice pipeline).
 */
export async function selectPiperVoice(voiceId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/voice/piper/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ profile_name: voiceId }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    return data?.success === true;
  } catch {
    return false;
  }
}

/**
 * Synthesize speech on the backend (Piper-first, pyttsx3 fallback) and return
 * the playable audio URL, or null on failure.
 */
export async function synthesizeVoice(
  text: string,
  voice?: string
): Promise<{ audio_url: string; engine?: string } | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/voice/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ text, voice }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data?.success || !data?.audio_url) return null;
    const url = data.audio_url.startsWith('/')
      ? `${API_BASE_URL}${data.audio_url}`
      : data.audio_url;
    return { audio_url: url, engine: data.engine };
  } catch {
    return null;
  }
}

/**
 * Upload a file to the backend.
 */
export async function uploadFile(
  file: File,
  conversationId?: string,
  onProgress?: (progress: number) => void
): Promise<ApiResponse<{
  id: string;
  name: string;
  path: string;
  size: number;
  type: string;
  category: string;
  hash: string;
  uploadedAt: string;
  conversationId?: string;
}>> {
  try {
    const formData = new FormData();
    formData.append('file', file);
    if (conversationId) {
      formData.append('conversationId', conversationId);
    }

    const xhr = new XMLHttpRequest();
    
    return new Promise((resolve) => {
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && onProgress) {
          const progress = (e.loaded / e.total) * 100;
          onProgress(progress);
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const data = JSON.parse(xhr.responseText);
          resolve({ success: true, data });
        } else {
          const error = JSON.parse(xhr.responseText);
          resolve({ success: false, error: error.detail || 'Upload failed' });
        }
      });

      xhr.addEventListener('error', () => {
        resolve({ success: false, error: 'Network error' });
      });

      xhr.open('POST', `${API_BASE_URL}/api/files/upload`);
      // Harden: pass the same API key the WebSocket uses, so uploads keep
      // working when ARENA_API_KEY is enabled on the backend.
      const headers = apiKeyHeader();
      Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
      xhr.send(formData);
    });
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * Download a file from the backend.
 */
export async function downloadFile(fileId: string): Promise<Blob | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/files/${fileId}`, {
      headers: apiKeyHeader(),
    });
    if (!response.ok) {
      throw new Error(`Download failed: ${response.statusText}`);
    }
    return await response.blob();
  } catch (error) {
    logger.error('Download error:', error);
    return null;
  }
}

/**
 * Delete a file from the backend.
 */
export async function deleteFile(fileId: string): Promise<ApiResponse<void>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/files/${fileId}`, {
      method: 'DELETE',
      headers: apiKeyHeader(),
    });

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || 'Delete failed' };
    }

    return { success: true };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * Execute code in a sandbox.
 */
export async function executeCode(
  code: string,
  language: string,
  timeout: number = 30
): Promise<ApiResponse<{
  success: boolean;
  output: string;
  error?: string;
  executionTime: number;
  timestamp: string;
  isolated?: boolean;
}>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/code/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...apiKeyHeader(),
      },
      body: JSON.stringify({ code, language, timeout }),
    });

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || 'Execution failed' };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * Analyze an attachment (OCR, vision, document).
 */
export async function analyzeAttachment(
  fileId: string,
  analysisType: 'ocr' | 'vision' | 'document',
  promptFocus?: string
): Promise<ApiResponse<{
  success: boolean;
  type: string;
  content: string;
  confidence?: number;
  metadata?: Record<string, string | number | boolean>;
  analyzedAt: string;
}>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/attachments/analyze`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...apiKeyHeader(),
      },
      body: JSON.stringify({ fileId, analysisType, promptFocus }),
    });

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || 'Analysis failed' };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * List uploaded files.
 */
export async function listFiles(conversationId?: string): Promise<ApiResponse<{
  files: Array<{
    id: string;
    name: string;
    path: string;
    size: number;
    type: string;
    category: string;
    hash: string;
    uploadedAt: string;
    conversationId?: string;
  }>;
  total: number;
}>> {
  try {
    const url = conversationId
      ? `${API_BASE_URL}/api/files?conversationId=${conversationId}`
      : `${API_BASE_URL}/api/files`;

    const response = await fetch(url, {
      headers: apiKeyHeader(),
    });

    if (!response.ok) {
      const error = await response.json();
      return { success: false, error: error.detail || 'Failed to list files' };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

export interface VisionResult {
  success: boolean;
  image_name?: string;
  file_name?: string;
  file_path?: string;
  image_url?: string;
  file_url?: string;
  width?: number;
  height?: number;
  ocr_text?: string;
  extracted_text?: string;
  ai_analysis?: string;
  analysis?: string;
  screen_changed?: boolean;
  note?: string;
  error?: string;
  detections?: Array<{ label: string; confidence: number; bbox?: { x: number; y: number; width: number; height: number }; center?: { x: number; y: number } }>;
  faces?: Array<{ label: string; confidence: number; bbox?: { x: number; y: number; width: number; height: number } }>;
  count?: number;
  engine?: string;
  detection_engine?: string;
  groundings_created?: string[];
  groundings_count?: number;
}

/**
 * Resolve a backend-relative image URL (/static/…) into an absolute URL the
 * <img> tag can load. Absolute URLs pass through unchanged.
 */
export function resolveStaticUrl(url: string): string {
  if (!url) return '';
  if (/^https?:\/\//i.test(url) || url.startsWith('data:')) return url;
  return `${API_BASE_URL}${url.startsWith('/') ? '' : '/'}${url}`;
}

/**
 * POST /vision/capture — capture the host desktop screen (native sight).
 */
export async function captureScreen(): Promise<VisionResult> {
  try {
    const res = await fetch(`${API_BASE_URL}/vision/capture`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { success: false, error: err.detail || `Capture failed (${res.status})` };
    }
    return await res.json();
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * POST /vision/capture-and-analyze — capture the host screen then OCR + LLM-analyse it.
 */
export async function captureAndAnalyzeScreen(promptFocus?: string): Promise<VisionResult> {
  try {
    const qs = promptFocus?.trim()
      ? `?prompt_focus=${encodeURIComponent(promptFocus.trim())}`
      : '';
    const res = await fetch(`${API_BASE_URL}/vision/capture-and-analyze${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { success: false, error: err.detail || `Analysis failed (${res.status})` };
    }
    return await res.json();
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * POST /vision/ocr — extract text from an image already on the host.
 */
export async function ocrImage(imagePath: string): Promise<VisionResult> {
  try {
    const res = await fetch(`${API_BASE_URL}/vision/ocr`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ image_path: imagePath }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { success: false, error: err.detail || `OCR failed (${res.status})` };
    }
    return await res.json();
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * POST /vision/analyze — OCR + LLM analysis of an image on the host.
 */
export async function analyzeImage(
  imagePath: string,
  promptFocus?: string
): Promise<VisionResult> {
  try {
    const res = await fetch(`${API_BASE_URL}/vision/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({
        image_path: imagePath,
        prompt_focus: promptFocus?.trim() || null,
        auto_save_memory: true,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { success: false, error: err.detail || `Analysis failed (${res.status})` };
    }
    return await res.json();
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * POST /vision/detect-objects — detect objects + auto-create groundings (P1-1 AGI).
 */
export async function detectObjects(imagePath: string, confThreshold = 0.5, autoCreateGroundings = true): Promise<VisionResult & { detections?: Array<{ label: string; confidence: number; bbox: { x: number; y: number; width: number; height: number } }>; groundings_created?: string[]; engine?: string } > {
  try {
    const res = await fetch(`${API_BASE_URL}/vision/detect-objects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ image_path: imagePath, conf_threshold: confThreshold, auto_create_groundings: autoCreateGroundings }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { success: false, error: err.detail || `Detection failed (${res.status})` };
    }
    return await res.json();
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

export async function detectFaces(imagePath: string): Promise<VisionResult & { faces?: Array<{ label: string; confidence: number; bbox: { x: number; y: number; width: number; height: number } }>; count?: number }> {
  try {
    const res = await fetch(`${API_BASE_URL}/vision/detect-faces`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ image_path: imagePath }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { success: false, error: err.detail || `Face detection failed (${res.status})` };
    }
    return await res.json();
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

export async function listGroundings(symbol?: string, modality?: string): Promise<{ groundings: Array<{ symbol: string; modality: string; confidence: number; sensory_experience: string }>; count: number; summary?: Record<string, unknown> } | null> {
  try {
    const qs = new URLSearchParams();
    if (symbol) qs.set('symbol', symbol);
    if (modality) qs.set('modality', modality);
    qs.set('limit', '100');
    const res = await fetch(`${API_BASE_URL}/vision/groundings?${qs.toString()}`, { headers: apiKeyHeader() });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function getVlmStatus(): Promise<{ available: boolean; model_id?: string; engine?: string; note?: string } | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/vision/vlm-status`, { headers: apiKeyHeader() });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function vlmAnalyze(imagePath: string, prompt?: string): Promise<VisionResult | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/vision/vlm-analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ image_path: imagePath, prompt_focus: prompt }),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * POST /mobile/camera — upload an image file (multipart) for analysis.
 */
export async function uploadImageForVision(file: File): Promise<VisionResult> {
  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE_URL}/mobile/camera`, {
      method: 'POST',
      headers: apiKeyHeader(),
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { success: false, error: err.detail || `Upload failed (${res.status})` };
    }
    return await res.json();
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

/**
 * Shared settings (wake word, voice, speed, theme, connection, models, …) —
 * persisted on the backend so web/desktop/Android share one source of truth.
 */
export interface SharedSettings {
  wake_word: string;
  voice: string;
  voice_speed: number;
  voice_enabled: boolean;
  language: string;
  noise_suppression: boolean;
  vad_sensitivity: number;
  response_delay: number;
  theme: string;
  font_size: string;
  high_contrast: boolean;
  large_text: boolean;
  reduced_motion: boolean;
  server_url: string;
  api_key: string;
  fast_model: string;
  main_model: string;
  lm_studio_url: string;
}

export async function getSharedSettings(): Promise<SharedSettings | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/settings`, { headers: apiKeyHeader() });
    if (!res.ok) return null;
    return (await res.json()) as SharedSettings;
  } catch {
    return null;
  }
}

export async function updateSharedSettings(
  patch: Partial<SharedSettings>
): Promise<SharedSettings | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify(patch),
    });
    if (!res.ok) return null;
    return (await res.json()) as SharedSettings;
  } catch {
    return null;
  }
}

export interface KnowledgeEntity {
  id: string;
  name: string;
  type: string;
  confidence: number;
  first_seen: string;
  last_seen: string;
  attributes?: Record<string, unknown>;
}

export interface KnowledgeRelationship {
  id: string;
  subject_id: string;
  predicate: string;
  object_id: string;
  confidence: number;
  created_at: string;
  last_confirmed: string;
}

export interface BackendProject {
  project_id: string;
  name: string;
  description: string;
  status: string;
  priority: string;
  progress_percent: number;
  milestones_total: number;
  milestones_reached: number;
  total_sessions: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface CollectionPage<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
  nextOffset: number | null;
}

export async function listMemoryPage(
  offset = 0,
  limit = 50,
  category?: string,
): Promise<CollectionPage<Record<string, unknown>>> {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (category) params.set('category', category);
  try {
    const response = await fetch(`${API_BASE_URL}/memories/page?${params}`, { headers: apiKeyHeader() });
    if (!response.ok) throw new Error('Memory page unavailable');
    const data = await response.json();
    return {
      items: Array.isArray(data?.memories) ? data.memories : [], total: Number(data?.total || 0),
      limit: Number(data?.limit || limit), offset: Number(data?.offset || offset),
      hasMore: data?.has_more === true,
      nextOffset: typeof data?.next_offset === 'number' ? data.next_offset : null,
    };
  } catch {
    return { items: [], total: 0, limit, offset, hasMore: false, nextOffset: null };
  }
}

export async function listWorkspaceFilePage(
  offset = 0,
  limit = 50,
  extension?: string,
): Promise<CollectionPage<Record<string, unknown>>> {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (extension) params.set('extension', extension);
  try {
    const response = await fetch(`${API_BASE_URL}/tools/workspace-files/page?${params}`, { headers: apiKeyHeader() });
    if (!response.ok) throw new Error('Workspace page unavailable');
    const data = await response.json();
    return {
      items: Array.isArray(data?.files) ? data.files : [], total: Number(data?.total || 0),
      limit: Number(data?.limit || limit), offset: Number(data?.offset || offset),
      hasMore: data?.has_more === true,
      nextOffset: typeof data?.next_offset === 'number' ? data.next_offset : null,
    };
  } catch {
    return { items: [], total: 0, limit, offset, hasMore: false, nextOffset: null };
  }
}

export interface BackendProjectPage {
  projects: BackendProject[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  next_offset: number | null;
}

export async function listBackendProjectsPage(
  offset = 0,
  limit = 50,
  status?: string,
): Promise<BackendProjectPage> {
  const empty: BackendProjectPage = { projects: [], total: 0, limit, offset, has_more: false, next_offset: null };
  try {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (status) params.set('status', status);
    const res = await fetch(`${API_BASE_URL}/projects?${params.toString()}`, { headers: apiKeyHeader() });
    if (!res.ok) return empty;
    const data = await res.json();
    return {
      projects: Array.isArray(data?.projects) ? data.projects as BackendProject[] : [],
      total: Number(data?.total || 0),
      limit: Number(data?.limit || limit),
      offset: Number(data?.offset || offset),
      has_more: data?.has_more === true,
      next_offset: typeof data?.next_offset === 'number' ? data.next_offset : null,
    };
  } catch {
    return empty;
  }
}

export async function listBackendProjects(): Promise<BackendProject[]> {
  return (await listBackendProjectsPage()).projects;
}

export async function getBackendProject(projectId: string): Promise<{ project: BackendProject; resume_context?: Record<string, unknown>; decomposition?: Record<string, unknown> } | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectId)}`, { headers: apiKeyHeader() });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function setProjectScheduler(projectId: string, enabled: boolean): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectId)}/scheduler`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ enabled }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function runProjectReadySteps(projectId: string, maxSteps = 1): Promise<Record<string, unknown> | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectId)}/run-ready`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ max_steps: maxSteps }),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function createBackendProject(name: string, description = "", priority = "normal", milestones?: string[], tags?: string[]): Promise<{ project_id: string } | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ name, description, priority, milestones, tags }),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Project tasks (Kanban board). Server-backed so tasks created on any UI
 * sync everywhere; the shape mirrors the local ProjectTask type.
 */
export interface BackendProjectTask {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  assignee: string;
  dueDate: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
  completedAt?: string | null;
}

export async function listBackendProjectTasks(projectId: string): Promise<BackendProjectTask[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectId)}/tasks`, { headers: apiKeyHeader() });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data?.tasks) ? data.tasks as BackendProjectTask[] : [];
  } catch {
    return [];
  }
}

export async function createBackendProjectTask(projectId: string, task: Partial<BackendProjectTask> & { title: string }): Promise<BackendProjectTask | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectId)}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify(task),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data?.task ?? null;
  } catch {
    return null;
  }
}

export async function updateBackendProjectTask(projectId: string, taskId: string, updates: Partial<BackendProjectTask>): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify(updates),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function deleteBackendProjectTask(projectId: string, taskId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}`, {
      method: 'DELETE',
      headers: apiKeyHeader(),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Fetch the world-model knowledge graph (entities + relationships) from the
 * backend, so the web Pansophy shows the same graph as the desktop/Android.
 */
export async function fetchKnowledgeGraph(): Promise<{
  entities: KnowledgeEntity[];
  relationships: KnowledgeRelationship[];
} | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/knowledge/graph`, { headers: apiKeyHeader() });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      entities: data?.entities ?? [],
      relationships: data?.relationships ?? [],
    };
  } catch {
    return null;
  }
}
