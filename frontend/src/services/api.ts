import { logger } from './logger';
/**
 * API service for communicating with Arena backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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
