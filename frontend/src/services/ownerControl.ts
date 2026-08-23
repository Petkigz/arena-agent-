import { apiKeyHeader } from './api';

export interface AuthorizedExecutionInput {
  authorizationId: string;
  actionType: string;
  payload: Record<string, unknown>;
  userText?: string;
  planId?: string;
}

export async function revokeAuthorization(authorizationId: string): Promise<boolean> {
  try {
    const response = await fetch(`/owner-control/authorizations/${encodeURIComponent(authorizationId)}`, {
      method: 'DELETE',
      headers: apiKeyHeader(),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export interface ReviewedPlanStep {
  step_id: string;
  goal_id: string;
  description: string;
  task_type: string;
  depends_on: string[];
  requires_evidence: string[];
  produces_evidence: string[];
  success_criteria: string[];
  failure_conditions: string[];
}

export interface ReviewedPlan {
  plan_id: string;
  goal_id: string;
  goal_title: string;
  revision: number;
  status: 'pending' | 'approved' | 'rejected' | 'revoked' | 'executed';
  snapshot: {
    plan_id: string;
    goal_id: string;
    goal_title: string;
    steps: ReviewedPlanStep[];
  };
  updated_at: string;
  decision_note: string;
}

async function jsonRequest(url: string, init?: RequestInit) {
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...apiKeyHeader(), ...(init?.headers || {}) },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data?.detail || 'Owner-control request failed');
  return data;
}

export async function listReviewedPlans(): Promise<ReviewedPlan[]> {
  try {
    const data = await jsonRequest('/owner-control/plans');
    return Array.isArray(data?.plans) ? data.plans : [];
  } catch {
    return [];
  }
}

export async function editReviewedPlan(plan: ReviewedPlan, steps: ReviewedPlanStep[]): Promise<ReviewedPlan> {
  const data = await jsonRequest(`/owner-control/plans/${encodeURIComponent(plan.plan_id)}`, {
    method: 'PUT',
    body: JSON.stringify({ expected_revision: plan.revision, steps }),
  });
  return data.plan;
}

export async function decideReviewedPlan(plan: ReviewedPlan, approved: boolean, note = ''): Promise<ReviewedPlan> {
  const data = await jsonRequest(`/owner-control/plans/${encodeURIComponent(plan.plan_id)}/decision`, {
    method: 'POST',
    body: JSON.stringify({ expected_revision: plan.revision, approved, note }),
  });
  return data.plan;
}

export async function revokeReviewedPlan(planId: string, note = ''): Promise<ReviewedPlan> {
  const data = await jsonRequest(`/owner-control/plans/${encodeURIComponent(planId)}/revoke`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  });
  return data.plan;
}

export async function executeReviewedPlan(planId: string): Promise<Record<string, unknown>> {
  return jsonRequest(`/owner-control/plans/${encodeURIComponent(planId)}/execute`, { method: 'POST' });
}

export interface AuthorizedExecutionResult {
  success: boolean;
  requestSuccess?: boolean;
  executionSuccess?: boolean;
  goalVerified?: boolean;
  verificationUnknown?: boolean;
  goalLifecycleState?: string;
  assistantReply?: string;
  reason?: string;
}

export async function executeAuthorizedAction(
  input: AuthorizedExecutionInput
): Promise<AuthorizedExecutionResult> {
  try {
    const response = await fetch('/owner-control/execute-authorized', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({
        authorization_id: input.authorizationId,
        action_type: input.actionType,
        payload: input.payload,
        user_text: input.userText || 'Owner-authorized action',
        plan_id: input.planId,
      }),
    });
    const data = await response.json();
    if (!response.ok) return { success: false, reason: data?.detail || 'Execution request failed' };
    return {
      success: data?.success === true,
      requestSuccess: data?.request_success,
      executionSuccess: data?.execution_success,
      goalVerified: data?.goal_verified,
      verificationUnknown: data?.verification_unknown,
      goalLifecycleState: data?.goal_lifecycle_state,
      assistantReply: data?.assistant_reply,
      reason: data?.reason || data?.verification?.reason,
    };
  } catch (error) {
    return { success: false, reason: error instanceof Error ? error.message : 'Execution request failed' };
  }
}
