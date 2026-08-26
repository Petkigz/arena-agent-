import { apiKeyHeader } from './api';

/**
 * Cognition services: the F1 cognitive-loop owner surfaces.
 * Charter, uncertainty questions, induced skills, learning progress,
 * and the owner model. All calls go through the authenticated owner API.
 */

async function cognitionRequest<T = Record<string, unknown>>(
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

// ── Owner Charter ───────────────────────────────────────────────────────────

export interface OwnerCharter {
  mission: string;
  values: { name: string; description: string }[];
  priorities: string[];
  communication_style: string;
  standing_directives: string[];
  revision: number;
  content_digest: string;
  updated_at: string;
}

export async function fetchOwnerCharter(): Promise<OwnerCharter> {
  const data = await cognitionRequest<{ charter: OwnerCharter }>('/owner-control/charter');
  return data.charter;
}

export async function updateOwnerCharter(patch: Partial<OwnerCharter>): Promise<{ revision: number }> {
  const data = await cognitionRequest<{ charter: OwnerCharter }>('/owner-control/charter', {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
  return { revision: data.charter.revision };
}

// ── Uncertainty questions ───────────────────────────────────────────────────

export interface OwnerQuestion {
  question_id: string;
  action_type: string;
  question_text: string;
  reason: string;
  calibrated_confidence: number;
  threshold: number;
  status: string;
  created_at: string;
}

export async function fetchOwnerQuestions(status = 'pending'): Promise<OwnerQuestion[]> {
  const data = await cognitionRequest<{ questions: OwnerQuestion[] }>(
    `/owner-control/questions?status=${encodeURIComponent(status)}`,
  );
  return data.questions ?? [];
}

export async function answerOwnerQuestion(
  questionId: string,
  answer: 'approve' | 'deny' | 'observe',
  note = '',
): Promise<Record<string, unknown>> {
  return cognitionRequest(`/owner-control/questions/${encodeURIComponent(questionId)}/answer`, {
    method: 'POST',
    body: JSON.stringify({ answer, note }),
  });
}

// ── Induced skills ──────────────────────────────────────────────────────────

export interface InducedSkill {
  candidate_id: string;
  skill_name: string;
  action_sequence: string[];
  occurrences: number;
  context_success_rate: number;
  status: string;
}

export async function fetchInducedSkills(status = 'pending'): Promise<InducedSkill[]> {
  const data = await cognitionRequest<{ candidates: InducedSkill[] }>(
    `/owner-control/induced-skills?status=${encodeURIComponent(status)}`,
  );
  return data.candidates ?? [];
}

export async function decideInducedSkill(
  candidateId: string,
  accept: boolean,
): Promise<Record<string, unknown>> {
  const action = accept ? 'accept' : 'reject';
  return cognitionRequest(`/owner-control/induced-skills/${encodeURIComponent(candidateId)}/${action}`, {
    method: 'POST',
    body: '{}',
  });
}

// ── Learning progress ───────────────────────────────────────────────────────

export interface LearningTarget {
  action_type: string;
  earlier_rate: number | null;
  recent_rate: number | null;
  progress: number | null;
  overall_rate: number;
  learning_value: number;
  status: string;
}

export async function fetchLearningProgress(): Promise<LearningTarget[]> {
  const data = await cognitionRequest<{ targets: LearningTarget[] }>('/owner-control/learning-progress');
  return data.targets ?? [];
}

// ── Owner model ─────────────────────────────────────────────────────────────

export interface OwnerModelReport {
  consistently_approves: string[];
  consistently_denies: string[];
  peak_activity_hours_utc: { hour_utc: number; actions: number }[];
  counted_preferences: {
    action_type: string;
    approved: number;
    denied: number;
    approval_rate: number;
  }[];
}

export async function fetchOwnerModel(): Promise<OwnerModelReport> {
  return cognitionRequest<OwnerModelReport>('/owner-control/owner-model');
}
