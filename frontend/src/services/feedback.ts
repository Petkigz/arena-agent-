import { apiKeyHeader, apiUrl } from './api';

export type UsefulnessSignalType =
  | 'explicit_rating'
  | 'task_completed'
  | 'follow_up_correction'
  | 'clarification_requested'
  | 'abandoned'
  | 'accepted_without_followup';

export interface UsefulnessFeedbackRequest {
  trace_id: string;
  signal_type?: UsefulnessSignalType;
  value?: number;
  rating?: number;
  note?: string;
}

export async function recordUsefulnessFeedback(
  request: UsefulnessFeedbackRequest,
): Promise<Record<string, unknown>> {
  const response = await fetch(apiUrl('/feedback/usefulness'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
    body: JSON.stringify(request),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(String((data as { detail?: unknown }).detail || 'Could not record usefulness feedback'));
  }
  return data as Record<string, unknown>;
}
