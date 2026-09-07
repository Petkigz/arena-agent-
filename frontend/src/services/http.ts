import { apiKeyHeader } from './api';

/**
 * Shared authenticated JSON request helper for service modules.
 *
 * Single home for the fetch/error/parse pattern (auth header, JSON content
 * type, status-checked errors) so service modules do not each carry a private
 * copy — found as the top cross-file duplication in the 2026-09-07 audit
 * (phase1Evidence.ts <-> cognition.ts, 5 shared 8-line windows).
 */
export async function requestJson<T = Record<string, unknown>>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...apiKeyHeader(), ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}): ${path}`);
  }
  return (await response.json()) as T;
}
