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
