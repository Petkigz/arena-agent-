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

export async function executeAuthorizedAction(input: AuthorizedExecutionInput): Promise<{
  success: boolean;
  reason?: string;
  result?: unknown;
}> {
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
    return { success: data?.success === true, reason: data?.reason, result: data?.result };
  } catch (error) {
    return { success: false, reason: error instanceof Error ? error.message : 'Execution request failed' };
  }
}
