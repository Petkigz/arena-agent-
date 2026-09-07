import { apiKeyHeader, apiUrl } from './api';

export type Usefulness = 'helpful' | 'partially_helpful' | 'not_helpful';
export type TaskOutcome = 'success' | 'failure' | 'unknown';
export type EvaluationSplit = 'held_out' | 'contract';
export type EvaluationCondition = 'single' | 'baseline' | 'adapted';

export interface UsefulnessFeedback {
  feedback_id: string;
  trace_id: string;
  usefulness: Usefulness;
  outcome_signal: string;
  retrieval_useful: boolean | null;
  note: string;
  created_at: string;
}

export interface TaskEvaluation {
  evaluation_id: string;
  task_key: string;
  trace_id: string;
  split: EvaluationSplit;
  condition: EvaluationCondition;
  observed_outcome: TaskOutcome;
  usefulness: Usefulness | 'unknown';
  correction_received: boolean;
  note: string;
  created_at: string;
}

export interface UsefulnessSubmission {
  usefulness: Usefulness;
  note: string;
  submission_id: string;
}

export interface TaskEvaluationSubmission {
  task_key: string;
  split: EvaluationSplit;
  condition: EvaluationCondition;
  observed_outcome: TaskOutcome;
  usefulness: Usefulness | 'unknown';
  correction_received: boolean;
  evidence_ids: string[];
  note: string;
  submission_id: string;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.success !== true) {
    throw new Error(
      typeof body?.detail === 'string' ? body.detail
        : typeof body?.error === 'string' ? body.error
          : `Could not save or load response feedback (HTTP ${response.status}).`,
    );
  }
  return body as T;
}

export async function loadResponseFeedback(traceId: string, signal?: AbortSignal) {
  const encoded = encodeURIComponent(traceId);
  const [ratings, heldOut, contracts] = await Promise.all([
    request<{ feedback: UsefulnessFeedback[] }>(`/cognition/traces/${encoded}/usefulness`, { signal }),
    request<{ evaluations: TaskEvaluation[] }>(`/benchmarks/phase1/tasks/evaluations?trace_id=${encoded}&split=held_out&limit=100`, { signal }),
    request<{ evaluations: TaskEvaluation[] }>(`/benchmarks/phase1/tasks/evaluations?trace_id=${encoded}&split=contract&limit=100`, { signal }),
  ]);
  if (!Array.isArray(ratings.feedback) || !Array.isArray(heldOut.evaluations) || !Array.isArray(contracts.evaluations)) {
    throw new Error('The server returned an invalid feedback history. Nothing new was recorded.');
  }
  const feedback = ratings.feedback.filter((item) => item.trace_id === traceId);
  const evaluations = [...heldOut.evaluations, ...contracts.evaluations]
    .filter((item) => item.trace_id === traceId)
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  return { feedback, evaluations };
}

export async function recordResponseUsefulness(traceId: string, submission: UsefulnessSubmission) {
  const result = await request<{ feedback: UsefulnessFeedback }>(
    `/cognition/traces/${encodeURIComponent(traceId)}/usefulness`,
    { method: 'POST', body: JSON.stringify(submission) },
  );
  if (!result.feedback?.feedback_id || result.feedback.trace_id !== traceId) {
    throw new Error('No matching feedback receipt was returned. Retry to check the same submission.');
  }
  return result.feedback;
}

export async function recordTaskEvaluation(traceId: string, submission: TaskEvaluationSubmission) {
  const result = await request<{ evaluation: TaskEvaluation }>('/benchmarks/phase1/tasks/evaluations', {
    method: 'POST', body: JSON.stringify({ ...submission, trace_id: traceId }),
  });
  if (!result.evaluation?.evaluation_id || result.evaluation.trace_id !== traceId) {
    throw new Error('No matching evaluation receipt was returned. Retry to check the same submission.');
  }
  return result.evaluation;
}

/** Retry identity only, not a credential. HTTP LAN clients need the fallback. */
export function newSubmissionId(): string {
  const random = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `web-${random}`;
}


export interface ResponseExplanation {
  facts: { trace_id: string; request: string; response?: string; goal_verified: boolean };
  explanation: string[];
  epistemic_presentation: { confidence_label?: string; calibration_status?: string };
}

/** Reuse the existing grounded-introspection endpoint; never ask an LLM why. */
export async function getResponseExplanation(traceId: string, signal?: AbortSignal) {
  const result = await request<ResponseExplanation>(
    `/self-awareness/introspection/${encodeURIComponent(traceId)}`, { signal },
  );
  if (result.facts?.trace_id !== traceId || !Array.isArray(result.explanation)) {
    throw new Error('No matching trace explanation was returned.');
  }
  return result;
}
