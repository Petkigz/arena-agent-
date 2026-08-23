import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../../components/ui';
import { usePrivacySettingsStore } from '../../stores';
import { ArrowLeft, Database, BarChart3, Lock, FileText, Download, Upload } from 'lucide-react';
import { notifications } from '../../services/notifications';
import { apiKeyHeader } from '../../services/api';
import {
  decidePendingApproval,
  decideReviewedPlan,
  editReviewedPlan,
  executeReviewedPlan,
  listPendingApprovals,
  listReviewedPlans,
  revokeReviewedPlan,
  type PendingApproval,
  type ReviewedPlan,
  type ReviewedPlanStep,
} from '../../services/ownerControl';

type ControlMode =
  | 'observe_only'
  | 'suggest_only'
  | 'approve_every_action'
  | 'approve_each_plan'
  | 'bounded_autonomy'
  | 'custom';

interface ControlledExecution {
  execution_id: string;
  proposal_id: string;
  action_type: string;
  status: string;
  started_at: string;
  cancel_requested: boolean;
  cancellation_observed: boolean;
  note: string;
  rollback_receipt?: {
    supported: boolean;
    reason: string;
    compensation_action?: string;
  } | null;
}

interface IntelligenceBenchmarkReport {
  run_id: string;
  created_at: string;
  passed_count: number;
  total_count: number;
  regressions: string[];
  checks: Array<{
    name: string;
    category: string;
    passed: boolean;
    evidence: string;
    duration_ms: number;
  }>;
}

interface AdaptiveAutonomyProfile {
  prediction_error_threshold: number;
  low_success_rate_threshold: number;
  goal_auto_approve_threshold: number;
  exploration_budget: number;
  owner_max_exploration_goals: number;
  sample_count: number;
  observed_success_rate: number;
  source: string;
}

interface AutonomousGoalItem {
  goal_id: string; title: string; description: string; priority: string; status: string;
  source: string; overall_score: number; requires_owner_approval: boolean;
}
interface AutonomyRunEvent {
  event_id: string; cycle_id: string; goal_id?: string; stage: string; reason: string;
  details: Record<string, unknown>; created_at: string;
}
interface ScheduledDirectiveItem {
  schedule_id: string; title: string; next_run_at: string; recurrence: string;
  missed_policy: string; status: string; priority: string;
}

interface OwnerControlPolicy {
  mode: ControlMode;
  paused: boolean;
  max_autonomous_level: number;
  require_approval_actions: string[];
  blocked_actions: string[];
  custom_autonomous_actions: string[];
  revision: number;
}

export function PrivacySettingsPage() {
  const navigate = useNavigate();
  const {
    dataRetentionDays,
    autoDeleteOldData,
    enableTelemetry,
    shareUsageStats,
    logAllActions,
    setDataRetentionDays,
    setAutoDeleteOldData,
    setEnableTelemetry,
    setShareUsageStats,
    setLogAllActions,
    exportSettings,
    importSettings,
  } = usePrivacySettingsStore();

  const [importData, setImportData] = useState('');
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [ownerPolicy, setOwnerPolicy] = useState<OwnerControlPolicy | null>(null);
  const [adaptiveProfile, setAdaptiveProfile] = useState<AdaptiveAutonomyProfile | null>(null);
  const [benchmarkReport, setBenchmarkReport] = useState<IntelligenceBenchmarkReport | null>(null);
  const [benchmarkBusy, setBenchmarkBusy] = useState(false);
  const [controlledExecutions, setControlledExecutions] = useState<ControlledExecution[]>([]);
  const [executionBusy, setExecutionBusy] = useState<string | null>(null);
  const [controlBusy, setControlBusy] = useState(false);
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([]);
  const [approvalBusy, setApprovalBusy] = useState<string | null>(null);
  const [reviewedPlans, setReviewedPlans] = useState<ReviewedPlan[]>([]);
  const [planDrafts, setPlanDrafts] = useState<Record<string, ReviewedPlanStep[]>>({});
  const [planBusy, setPlanBusy] = useState<string | null>(null);
  const [autonomousGoals, setAutonomousGoals] = useState<AutonomousGoalItem[]>([]);
  const [autonomyEvents, setAutonomyEvents] = useState<AutonomyRunEvent[]>([]);
  const [autonomySchedule, setAutonomySchedule] = useState<ScheduledDirectiveItem[]>([]);
  const [autonomyBusy, setAutonomyBusy] = useState<string | null>(null);
  const [newDirective, setNewDirective] = useState({ title: '', description: '', priority: 'normal' });
  const [newSchedule, setNewSchedule] = useState({ title: '', run_at: '', recurrence: 'none', missed_policy: 'run_once' });

  useEffect(() => {
    let cancelled = false;
    fetch('/owner-control', { headers: apiKeyHeader() })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('Control policy unavailable')))
      .then((data) => { if (!cancelled) setOwnerPolicy(data.policy); })
      .catch(() => { if (!cancelled) notifications.error('Could not load owner control policy'); });
    fetch('/owner-control/adaptive-autonomy', { headers: apiKeyHeader() })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (!cancelled && data?.profile) setAdaptiveProfile(data.profile); })
      .catch(() => {});
    fetch('/benchmarks/intelligence/latest', { headers: apiKeyHeader() })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (!cancelled && data?.report) setBenchmarkReport(data.report); })
      .catch(() => {});
    const loadExecutions = () => fetch('/owner-control/executions?limit=20', { headers: apiKeyHeader() })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (!cancelled && Array.isArray(data?.executions)) setControlledExecutions(data.executions); })
      .catch(() => {});
    loadExecutions();
    const executionTimer = window.setInterval(loadExecutions, 3000);
    listPendingApprovals().then((approvals) => {
      if (!cancelled) setPendingApprovals(approvals);
    });
    listReviewedPlans().then((plans) => {
      if (!cancelled) {
        setReviewedPlans(plans);
        setPlanDrafts(Object.fromEntries(plans.map((plan) => [
          plan.plan_id,
          plan.snapshot.steps.map((step) => ({ ...step })),
        ])));
      }
    });
    Promise.all([
      fetch('/owner-control/autonomous-goals?limit=50', { headers: apiKeyHeader() }).then((r) => r.json()),
      fetch('/owner-control/autonomy-runs?limit=50', { headers: apiKeyHeader() }).then((r) => r.json()),
      fetch('/owner-control/autonomy-schedule?limit=50', { headers: apiKeyHeader() }).then((r) => r.json()),
    ]).then(([goals, events, schedule]) => {
      if (!cancelled) {
        setAutonomousGoals(Array.isArray(goals?.goals) ? goals.goals : []);
        setAutonomyEvents(Array.isArray(events?.events) ? events.events : []);
        setAutonomySchedule(Array.isArray(schedule?.schedule) ? schedule.schedule : []);
      }
    }).catch(() => {});
    return () => {
      cancelled = true;
      window.clearInterval(executionTimer);
    };
  }, []);

  const updateScheduleStatus = async (scheduleId: string, status: string) => {
    setAutonomyBusy(scheduleId);
    const response = await fetch(`/owner-control/autonomy-schedule/${encodeURIComponent(scheduleId)}/status`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ status }),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) setAutonomySchedule((current) => current.map((item) => item.schedule_id === scheduleId ? data.schedule : item));
    else notifications.error(data?.detail || 'Could not update schedule');
    setAutonomyBusy(null);
  };

  const executeNextAutonomousGoal = async () => {
    setAutonomyBusy('execute-next');
    const response = await fetch('/owner-control/autonomous-goals/execute-next', { method: 'POST', headers: apiKeyHeader() });
    const data = await response.json().catch(() => ({}));
    if (response.ok && data?.plan) notifications.success(`Goal processed through action gates — plan ${data.plan.plan_id || ''}`);
    else notifications.error(data?.detail || data?.note || 'No approved goal is ready');
    setAutonomyBusy(null);
  };

  const createOwnerDirective = async () => {
    if (!newDirective.title.trim()) return;
    setAutonomyBusy('create-directive');
    const response = await fetch('/owner-control/autonomous-goals', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ ...newDirective, approve_for_planning: true }),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) {
      setAutonomousGoals((current) => [data.goal, ...current]);
      setNewDirective({ title: '', description: '', priority: 'normal' });
      notifications.success('Owner directive added and approved for planning; actions remain gated');
    } else notifications.error(data?.detail || 'Could not create directive');
    setAutonomyBusy(null);
  };

  const createScheduledDirective = async () => {
    if (!newSchedule.title.trim() || !newSchedule.run_at) return;
    setAutonomyBusy('create-schedule');
    const response = await fetch('/owner-control/autonomy-schedule', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ ...newSchedule, run_at: new Date(newSchedule.run_at).toISOString(), approve_for_planning: true }),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) {
      setAutonomySchedule((current) => [...current, data.schedule]);
      setNewSchedule({ title: '', run_at: '', recurrence: 'none', missed_policy: 'run_once' });
      notifications.success('Scheduled directive saved; execution actions remain separately gated');
    } else notifications.error(data?.detail || 'Could not create schedule');
    setAutonomyBusy(null);
  };

  const decideAutonomousGoal = async (goalId: string, approved: boolean) => {
    setAutonomyBusy(goalId);
    try {
      const response = await fetch(`/owner-control/autonomous-goals/${encodeURIComponent(goalId)}/decision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
        body: JSON.stringify({ approved }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || 'Goal decision failed');
      setAutonomousGoals((current) => current.map((goal) => goal.goal_id === goalId ? data.goal : goal));
      notifications.success(approved ? 'Goal approved for planning only' : 'Goal rejected');
    } catch (error) { notifications.error(error instanceof Error ? error.message : 'Goal decision failed'); }
    finally { setAutonomyBusy(null); }
  };

  const prioritizeAutonomousGoal = async (goalId: string, priority: string) => {
    setAutonomyBusy(goalId);
    const response = await fetch(`/owner-control/autonomous-goals/${encodeURIComponent(goalId)}/priority`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
      body: JSON.stringify({ priority }),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok) setAutonomousGoals((current) => current.map((goal) => goal.goal_id === goalId ? data.goal : goal));
    else notifications.error(data?.detail || 'Could not reprioritize goal');
    setAutonomyBusy(null);
  };

  const decideApproval = async (approval: PendingApproval, approved: boolean) => {
    setApprovalBusy(approval.action_id);
    try {
      await decidePendingApproval(
        approval.action_id,
        approved,
        approved ? 'Approved from Owner Control' : 'Denied from Owner Control',
      );
      setPendingApprovals((current) => current.filter((item) => item.action_id !== approval.action_id));
      notifications.success(approved ? 'Exact action scope authorized' : 'Action denied');
    } catch (error) {
      notifications.error(error instanceof Error ? error.message : 'Could not decide action');
    } finally {
      setApprovalBusy(null);
    }
  };

  const replaceReviewedPlan = (plan: ReviewedPlan) => {
    setReviewedPlans((current) => current.map((item) => item.plan_id === plan.plan_id ? plan : item));
    setPlanDrafts((current) => ({
      ...current,
      [plan.plan_id]: plan.snapshot.steps.map((step) => ({ ...step })),
    }));
  };

  const savePlanEdits = async (plan: ReviewedPlan) => {
    setPlanBusy(plan.plan_id);
    try {
      replaceReviewedPlan(await editReviewedPlan(plan, planDrafts[plan.plan_id] || plan.snapshot.steps));
      notifications.success('Plan edits saved; fresh approval is required');
    } catch (error) {
      notifications.error(error instanceof Error ? error.message : 'Could not edit plan');
    } finally {
      setPlanBusy(null);
    }
  };

  const decidePlan = async (plan: ReviewedPlan, approved: boolean) => {
    setPlanBusy(plan.plan_id);
    try {
      replaceReviewedPlan(await decideReviewedPlan(plan, approved));
      notifications.success(approved ? 'Plan approved' : 'Plan rejected');
    } catch (error) {
      notifications.error(error instanceof Error ? error.message : 'Could not decide plan');
    } finally {
      setPlanBusy(null);
    }
  };

  const revokePlan = async (plan: ReviewedPlan) => {
    setPlanBusy(plan.plan_id);
    try {
      replaceReviewedPlan(await revokeReviewedPlan(plan.plan_id, 'Revoked from Owner Control'));
      notifications.success('Plan authorization revoked');
    } catch (error) {
      notifications.error(error instanceof Error ? error.message : 'Could not revoke plan');
    } finally {
      setPlanBusy(null);
    }
  };

  const executePlan = async (plan: ReviewedPlan) => {
    setPlanBusy(plan.plan_id);
    try {
      const execution = await executeReviewedPlan(plan.plan_id);
      const status = String(execution.plan_status || 'unknown');
      notifications.success(`Approved plan processed — status: ${status}`);
      const plans = await listReviewedPlans();
      setReviewedPlans(plans);
    } catch (error) {
      notifications.error(error instanceof Error ? error.message : 'Could not execute plan');
    } finally {
      setPlanBusy(null);
    }
  };

  const refreshExecutions = async () => {
    const response = await fetch('/owner-control/executions?limit=20', { headers: apiKeyHeader() });
    if (response.ok) {
      const data = await response.json();
      if (Array.isArray(data?.executions)) setControlledExecutions(data.executions);
    }
  };

  const cancelExecution = async (executionId: string) => {
    setExecutionBusy(executionId);
    const response = await fetch(`/owner-control/executions/${encodeURIComponent(executionId)}/cancel`, {
      method: 'POST', headers: apiKeyHeader(),
    });
    if (response.ok) notifications.success('Cancellation requested; waiting for a cooperative checkpoint');
    else notifications.error('Could not cancel execution');
    await refreshExecutions();
    setExecutionBusy(null);
  };

  const requestRollback = async (executionId: string) => {
    setExecutionBusy(executionId);
    const response = await fetch(`/owner-control/executions/${encodeURIComponent(executionId)}/request-rollback`, {
      method: 'POST', headers: apiKeyHeader(),
    });
    if (response.ok) notifications.success('Rollback compensation added to pending approvals');
    else notifications.error('No deterministic rollback is available');
    await refreshExecutions();
    setExecutionBusy(null);
  };

  const runIntelligenceBenchmark = async () => {
    setBenchmarkBusy(true);
    try {
      const response = await fetch('/benchmarks/intelligence/run', {
        method: 'POST',
        headers: apiKeyHeader(),
      });
      if (!response.ok) throw new Error();
      const data = await response.json();
      setBenchmarkReport(data.report);
      notifications.success(
        data.report.regressions.length
          ? `Benchmark completed with ${data.report.regressions.length} regression(s)`
          : 'Benchmark completed without detected regressions',
      );
    } catch {
      notifications.error('Could not run intelligence benchmark');
    } finally {
      setBenchmarkBusy(false);
    }
  };

  const updateExplorationBudget = async (maximum: number) => {
    setControlBusy(true);
    try {
      const response = await fetch('/owner-control/adaptive-autonomy/exploration-budget', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
        body: JSON.stringify({ max_exploration_goals: maximum }),
      });
      if (!response.ok) throw new Error();
      const data = await response.json();
      setAdaptiveProfile(data.profile);
      notifications.success('Exploration budget updated');
    } catch {
      notifications.error('Could not update exploration budget');
    } finally {
      setControlBusy(false);
    }
  };

  const updateOwnerPolicy = async (patch: Partial<OwnerControlPolicy>) => {
    setControlBusy(true);
    try {
      const response = await fetch('/owner-control', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
        body: JSON.stringify(patch),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      setOwnerPolicy(data.policy);
      notifications.success('Owner control policy updated');
    } catch {
      notifications.error('Could not update owner control policy');
    } finally {
      setControlBusy(false);
    }
  };

  const setEmergencyPause = async (paused: boolean) => {
    setControlBusy(true);
    try {
      const response = await fetch('/owner-control/pause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...apiKeyHeader() },
        body: JSON.stringify({ paused }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      setOwnerPolicy(data.policy);
      notifications.success(paused ? 'All action execution paused' : 'Execution resumed under your policy');
    } catch {
      notifications.error('Could not change emergency pause');
    } finally {
      setControlBusy(false);
    }
  };

  const handleExport = () => {
    const data = exportSettings();
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `arena-privacy-settings-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = () => {
    const success = importSettings(importData);
    if (success) {
      notifications.success('Settings imported successfully!');
      setShowImportDialog(false);
      setImportData('');
    } else {
      notifications.error('Failed to import settings. Please check the format.');
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-background-primary">
      <div className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => navigate('/settings')}
            className="flex items-center gap-2 text-text-secondary hover:text-text-primary mb-4"
          >
            <ArrowLeft className="w-5 h-5" />
            <span>Back to Settings</span>
          </button>
          <h1 className="text-3xl font-bold text-text-primary">Privacy & Security</h1>
          <p className="text-text-secondary mt-2">
            Configure data retention, telemetry, and security settings
          </p>
        </div>

        {/* Owner Control Plane */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Lock className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Owner Control</h2>
          </div>
          <Card className="space-y-5">
            <p className="text-sm text-text-secondary">
              The agent may consider and explain broad alternatives, but recommendation,
              authorization, and execution remain separate. This policy controls execution.
            </p>

            {!ownerPolicy ? (
              <p className="text-sm text-text-muted">Loading effective policy…</p>
            ) : (
              <>
                <div className={`rounded border p-4 ${ownerPolicy.paused ? 'border-red-500 bg-red-500/10' : 'border-border'}`}>
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <h3 className="font-medium text-text-primary">
                        {ownerPolicy.paused ? 'Emergency pause active' : 'Execution active'}
                      </h3>
                      <p className="text-xs text-text-muted mt-1">
                        Emergency pause stops every capability before prediction or resource work.
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={controlBusy}
                      onClick={() => setEmergencyPause(!ownerPolicy.paused)}
                      className={`px-4 py-2 rounded text-white disabled:opacity-50 ${ownerPolicy.paused ? 'bg-green-600' : 'bg-red-600'}`}
                    >
                      {ownerPolicy.paused ? 'Resume' : 'Pause all actions'}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-2">Control mode</label>
                  <select
                    value={ownerPolicy.mode}
                    disabled={controlBusy}
                    onChange={(event) => updateOwnerPolicy({ mode: event.target.value as ControlMode })}
                    className="w-full px-3 py-2 bg-background-surface border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent-primary"
                  >
                    <option value="observe_only">Observe only — no execution</option>
                    <option value="suggest_only">Suggest only — recommendations, no execution</option>
                    <option value="approve_every_action">Approve every action</option>
                    <option value="approve_each_plan">Approve each plan</option>
                    <option value="bounded_autonomy">Bounded autonomy</option>
                    <option value="custom">Custom action allowlist</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-2">
                    Highest autonomous safety level: {ownerPolicy.max_autonomous_level}
                  </label>
                  <select
                    value={ownerPolicy.max_autonomous_level}
                    disabled={controlBusy || !['bounded_autonomy', 'custom'].includes(ownerPolicy.mode)}
                    onChange={(event) => updateOwnerPolicy({ max_autonomous_level: Number(event.target.value) })}
                    className="w-full px-3 py-2 bg-background-surface border border-border rounded disabled:opacity-50"
                  >
                    <option value={0}>Level 0 — read and observe only</option>
                    <option value={1}>Level 1 — include drafts</option>
                    <option value={2}>Level 2 — include reversible actions</option>
                  </select>
                  <p className="text-xs text-text-muted mt-1">
                    Level 3 always requires explicit approval and cannot be delegated here.
                  </p>
                </div>

                {adaptiveProfile && (
                  <div className="rounded border border-border bg-background-secondary p-4 space-y-2">
                    <h3 className="text-sm font-medium text-text-primary">Adaptive curiosity</h3>
                    <p className="text-xs text-text-muted">
                      Thresholds calibrate from verified outcomes, while your maximum exploration budget is absolute.
                    </p>
                    <label className="block text-xs text-text-secondary">
                      Maximum exploratory goals per cycle: {adaptiveProfile.owner_max_exploration_goals}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="10"
                      value={adaptiveProfile.owner_max_exploration_goals}
                      disabled={controlBusy}
                      onChange={(event) => setAdaptiveProfile({
                        ...adaptiveProfile,
                        owner_max_exploration_goals: Number(event.target.value),
                      })}
                      onMouseUp={(event) => updateExplorationBudget(Number(event.currentTarget.value))}
                      onTouchEnd={(event) => updateExplorationBudget(Number(event.currentTarget.value))}
                      onBlur={(event) => updateExplorationBudget(Number(event.currentTarget.value))}
                      className="w-full"
                    />
                    <div className="grid grid-cols-2 gap-2 text-xs text-text-muted">
                      <span>Current budget: {adaptiveProfile.exploration_budget}</span>
                      <span>Samples: {adaptiveProfile.sample_count}</span>
                      <span>Surprisal trigger: {adaptiveProfile.prediction_error_threshold.toFixed(2)}</span>
                      <span>Goal approval: {adaptiveProfile.goal_auto_approve_threshold.toFixed(2)}</span>
                      <span>Observed success: {(adaptiveProfile.observed_success_rate * 100).toFixed(0)}%</span>
                      <span>Source: {adaptiveProfile.source}</span>
                    </div>
                  </div>
                )}

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-text-secondary mb-2">
                      Always require approval
                    </label>
                    <textarea
                      value={ownerPolicy.require_approval_actions.join(', ')}
                      disabled={controlBusy}
                      onBlur={(event) => updateOwnerPolicy({
                        require_approval_actions: event.target.value.split(',').map((v) => v.trim()).filter(Boolean),
                      })}
                      onChange={(event) => setOwnerPolicy({
                        ...ownerPolicy,
                        require_approval_actions: event.target.value.split(',').map((v) => v.trim()),
                      })}
                      className="w-full h-24 px-3 py-2 bg-background-surface border border-border rounded text-sm"
                      placeholder="run_command, open_application"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-text-secondary mb-2">
                      Absolutely blocked actions
                    </label>
                    <textarea
                      value={ownerPolicy.blocked_actions.join(', ')}
                      disabled={controlBusy}
                      onBlur={(event) => updateOwnerPolicy({
                        blocked_actions: event.target.value.split(',').map((v) => v.trim()).filter(Boolean),
                      })}
                      onChange={(event) => setOwnerPolicy({
                        ...ownerPolicy,
                        blocked_actions: event.target.value.split(',').map((v) => v.trim()),
                      })}
                      className="w-full h-24 px-3 py-2 bg-background-surface border border-border rounded text-sm"
                      placeholder="delete_file, trade_action"
                    />
                  </div>
                </div>

                {ownerPolicy.mode === 'custom' && (
                  <div>
                    <label className="block text-sm font-medium text-text-secondary mb-2">
                      Custom autonomous action allowlist
                    </label>
                    <textarea
                      value={ownerPolicy.custom_autonomous_actions.join(', ')}
                      disabled={controlBusy}
                      onBlur={(event) => updateOwnerPolicy({
                        custom_autonomous_actions: event.target.value.split(',').map((v) => v.trim()).filter(Boolean),
                      })}
                      onChange={(event) => setOwnerPolicy({
                        ...ownerPolicy,
                        custom_autonomous_actions: event.target.value.split(',').map((v) => v.trim()),
                      })}
                      className="w-full h-24 px-3 py-2 bg-background-surface border border-border rounded text-sm"
                      placeholder="read_file, web_search"
                    />
                  </div>
                )}

                <p className="text-xs text-text-muted">Policy revision {ownerPolicy.revision}</p>
              </>
            )}
          </Card>
        </section>

        {/* Autonomous queue, calendar, and run ledger */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <BarChart3 className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Autonomy Operations</h2>
          </div>
          <Card className="space-y-5">
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm text-text-secondary">
                Planning approval never authorizes actions. Every resulting action still passes Owner Control, exact authorization when required, observation, and verification.
              </p>
              <button disabled={autonomyBusy === 'execute-next'} onClick={executeNextAutonomousGoal} className="shrink-0 px-3 py-1.5 bg-accent-primary text-white rounded text-xs disabled:opacity-50">Process next approved goal</button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded border border-border p-3 space-y-2">
                <h3 className="text-sm font-medium text-text-primary">Create owner directive</h3>
                <input value={newDirective.title} onChange={(e) => setNewDirective({ ...newDirective, title: e.target.value })} placeholder="Task title" className="w-full px-2 py-1 bg-background-surface border border-border rounded text-sm" />
                <textarea value={newDirective.description} onChange={(e) => setNewDirective({ ...newDirective, description: e.target.value })} placeholder="Description" className="w-full px-2 py-1 bg-background-surface border border-border rounded text-sm" />
                <select value={newDirective.priority} onChange={(e) => setNewDirective({ ...newDirective, priority: e.target.value })} className="w-full px-2 py-1 bg-background-surface border border-border rounded text-sm">
                  {['low', 'normal', 'high', 'critical'].map((p) => <option key={p}>{p}</option>)}
                </select>
                <button disabled={autonomyBusy === 'create-directive'} onClick={createOwnerDirective} className="px-3 py-1.5 bg-accent-primary text-white rounded text-xs disabled:opacity-50">Add to planning queue</button>
              </div>
              <div className="rounded border border-border p-3 space-y-2">
                <h3 className="text-sm font-medium text-text-primary">Schedule owner directive</h3>
                <input value={newSchedule.title} onChange={(e) => setNewSchedule({ ...newSchedule, title: e.target.value })} placeholder="Task title" className="w-full px-2 py-1 bg-background-surface border border-border rounded text-sm" />
                <input type="datetime-local" value={newSchedule.run_at} onChange={(e) => setNewSchedule({ ...newSchedule, run_at: e.target.value })} className="w-full px-2 py-1 bg-background-surface border border-border rounded text-sm" />
                <div className="flex gap-2">
                  <select value={newSchedule.recurrence} onChange={(e) => setNewSchedule({ ...newSchedule, recurrence: e.target.value })} className="flex-1 px-2 py-1 bg-background-surface border border-border rounded text-sm">{['none', 'daily', 'weekly'].map((v) => <option key={v}>{v}</option>)}</select>
                  <select value={newSchedule.missed_policy} onChange={(e) => setNewSchedule({ ...newSchedule, missed_policy: e.target.value })} className="flex-1 px-2 py-1 bg-background-surface border border-border rounded text-sm">{['run_once', 'skip'].map((v) => <option key={v}>{v}</option>)}</select>
                </div>
                <button disabled={autonomyBusy === 'create-schedule'} onClick={createScheduledDirective} className="px-3 py-1.5 bg-accent-primary text-white rounded text-xs disabled:opacity-50">Save schedule</button>
              </div>
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="space-y-2">
                <h3 className="font-medium text-text-primary">Goal queue</h3>
                {autonomousGoals.length === 0 ? <p className="text-xs text-text-muted">No queued goals.</p> : autonomousGoals.slice(0, 12).map((goal) => (
                  <div key={goal.goal_id} className="rounded border border-border p-2 text-xs space-y-2">
                    <div className="font-medium text-text-primary">{goal.title}</div>
                    <div className="text-text-muted">{goal.source} · {goal.status} · score {goal.overall_score.toFixed(2)}</div>
                    <select value={goal.priority} disabled={autonomyBusy === goal.goal_id} onChange={(e) => prioritizeAutonomousGoal(goal.goal_id, e.target.value)} className="w-full bg-background-surface border border-border rounded p-1">
                      {['low', 'normal', 'high', 'critical'].map((p) => <option key={p}>{p}</option>)}
                    </select>
                    {['proposed', 'evaluated', 'deferred'].includes(goal.status) && <div className="flex gap-2">
                      <button onClick={() => decideAutonomousGoal(goal.goal_id, true)} className="px-2 py-1 bg-accent-primary text-white rounded">Approve planning</button>
                      <button onClick={() => decideAutonomousGoal(goal.goal_id, false)} className="px-2 py-1 border border-border rounded">Reject</button>
                    </div>}
                    {goal.status === 'approved' && <button onClick={async () => {
                      const response = await fetch(`/owner-control/autonomous-goals/${encodeURIComponent(goal.goal_id)}/defer`, { method: 'POST', headers: apiKeyHeader() });
                      const data = await response.json().catch(() => ({}));
                      if (response.ok) setAutonomousGoals((current) => current.map((item) => item.goal_id === goal.goal_id ? data.goal : item));
                    }} className="px-2 py-1 border border-border rounded">Defer before execution</button>}
                  </div>
                ))}
              </div>
              <div className="space-y-2">
                <h3 className="font-medium text-text-primary">Schedule</h3>
                {autonomySchedule.length === 0 ? <p className="text-xs text-text-muted">No scheduled directives.</p> : autonomySchedule.slice(0, 12).map((item) => (
                  <div key={item.schedule_id} className="rounded border border-border p-2 text-xs space-y-2">
                    <div className="font-medium text-text-primary">{item.title}</div>
                    <div className="text-text-muted">{item.next_run_at} · {item.recurrence} · {item.status}</div>
                    {!['completed', 'cancelled'].includes(item.status) && <div className="flex gap-2">
                      <button disabled={autonomyBusy === item.schedule_id} onClick={() => updateScheduleStatus(item.schedule_id, item.status === 'paused' ? 'active' : 'paused')} className="px-2 py-1 border border-border rounded">{item.status === 'paused' ? 'Resume' : 'Pause'}</button>
                      <button disabled={autonomyBusy === item.schedule_id} onClick={() => updateScheduleStatus(item.schedule_id, 'cancelled')} className="px-2 py-1 border border-red-500 text-red-500 rounded">Cancel</button>
                    </div>}
                  </div>
                ))}
              </div>
              <div className="space-y-2">
                <h3 className="font-medium text-text-primary">Run evidence</h3>
                {autonomyEvents.length === 0 ? <p className="text-xs text-text-muted">No cycle events.</p> : autonomyEvents.slice(0, 20).map((event) => (
                  <div key={event.event_id} className="rounded border border-border p-2 text-xs">
                    <div className="font-medium text-text-primary">{event.stage}</div>
                    <div className="text-text-muted">{event.goal_id || event.cycle_id}</div>
                    {event.reason && <div className="text-text-secondary">{event.reason}</div>}
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </section>

        {/* Cooperative execution control and rollback receipts */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Lock className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Active Execution Control</h2>
          </div>
          <Card className="space-y-3">
            <p className="text-sm text-text-secondary">
              Cancellation is cooperative: Arena stops at registered checkpoints and terminates supported sandbox process groups. Side effects before a checkpoint may already exist. Rollback is offered only when a deterministic compensation receipt exists and always requires a new approval.
            </p>
            <button type="button" onClick={refreshExecutions} className="px-3 py-1.5 text-xs border border-border rounded">
              Refresh executions
            </button>
            {controlledExecutions.length === 0 ? (
              <p className="text-xs text-text-muted">No controlled execution history yet.</p>
            ) : controlledExecutions.map((execution) => (
              <div key={execution.execution_id} className="rounded border border-border bg-background-secondary p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-medium text-text-primary">{execution.action_type}</h3>
                    <p className="text-xs text-text-muted">{execution.execution_id} · {execution.status}</p>
                    {execution.note && <p className="text-xs text-text-secondary mt-1">{execution.note}</p>}
                  </div>
                  <div className="flex gap-2">
                    {execution.status === 'running' && (
                      <button
                        disabled={executionBusy === execution.execution_id}
                        onClick={() => cancelExecution(execution.execution_id)}
                        className="px-2 py-1 text-xs bg-red-600 text-white rounded disabled:opacity-50"
                      >
                        Request stop
                      </button>
                    )}
                    {execution.rollback_receipt?.supported && (
                      <button
                        disabled={executionBusy === execution.execution_id}
                        onClick={() => requestRollback(execution.execution_id)}
                        className="px-2 py-1 text-xs border border-amber-500 text-amber-600 rounded disabled:opacity-50"
                      >
                        Request rollback
                      </button>
                    )}
                  </div>
                </div>
                {execution.rollback_receipt && (
                  <p className="text-xs text-text-muted mt-2">
                    Rollback: {execution.rollback_receipt.supported ? execution.rollback_receipt.compensation_action : 'unavailable'} — {execution.rollback_receipt.reason}
                  </p>
                )}
              </div>
            ))}
          </Card>
        </section>

        {/* Longitudinal intelligence benchmark */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <BarChart3 className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Intelligence Regression Benchmark</h2>
          </div>
          <Card className="space-y-4">
            <p className="text-sm text-text-secondary">
              Runs isolated deterministic checks for memory benefit, learning from success and failure,
              adaptive thresholds, consolidation, authorization replay, temporal continuity, project dependencies,
              LoRA review boundaries, and owner curiosity limits. This is a pass count—not an “AGI percentage.”
            </p>
            <button
              type="button"
              disabled={benchmarkBusy}
              onClick={runIntelligenceBenchmark}
              className="px-4 py-2 rounded bg-accent-primary text-white disabled:opacity-50"
            >
              {benchmarkBusy ? 'Running isolated checks…' : 'Run benchmark now'}
            </button>
            {benchmarkReport && (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-4 text-sm text-text-primary">
                  <span>{benchmarkReport.passed_count}/{benchmarkReport.total_count} checks passed</span>
                  <span>{benchmarkReport.regressions.length} regression(s)</span>
                  <span className="text-text-muted">{new Date(benchmarkReport.created_at).toLocaleString()}</span>
                </div>
                {benchmarkReport.regressions.length > 0 && (
                  <p className="text-sm text-red-500">Regressions: {benchmarkReport.regressions.join(', ')}</p>
                )}
                <div className="grid gap-2 md:grid-cols-2">
                  {benchmarkReport.checks.map((check) => (
                    <div key={check.name} className="rounded border border-border bg-background-secondary p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-medium text-text-primary">{check.name}</span>
                        <span className={check.passed ? 'text-green-500' : 'text-red-500'}>
                          {check.passed ? 'PASS' : 'FAIL'}
                        </span>
                      </div>
                      <p className="text-xs text-text-muted mt-1">{check.category} · {check.duration_ms.toFixed(1)} ms</p>
                      <p className="text-xs text-text-secondary mt-1">{check.evidence}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </section>

        {/* Pending exact-action approvals, including project DAG steps */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Lock className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Pending Action Approvals</h2>
          </div>
          <Card className="space-y-4">
            {pendingApprovals.length === 0 ? (
              <p className="text-sm text-text-muted">No actions are waiting for authorization.</p>
            ) : pendingApprovals.map((approval) => (
              <div key={approval.action_id} className="rounded border border-amber-500/50 bg-amber-500/10 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-medium text-text-primary">{approval.goal_text || approval.action_type}</h3>
                    <p className="text-xs text-text-muted mt-1">{approval.reason}</p>
                    <code className="text-xs text-text-secondary">{approval.action_type}</code>
                  </div>
                  <span className="text-xs text-text-muted">{approval.conversation_id}</span>
                </div>
                <pre className="mt-3 max-h-40 overflow-auto rounded bg-background-primary p-2 text-xs text-text-secondary">
                  {JSON.stringify(approval.payload, null, 2)}
                </pre>
                <div className="flex gap-2 mt-3">
                  <button
                    type="button"
                    disabled={approvalBusy === approval.action_id}
                    onClick={() => decideApproval(approval, false)}
                    className="px-3 py-2 rounded bg-red-600 text-white disabled:opacity-50"
                  >
                    Deny
                  </button>
                  <button
                    type="button"
                    disabled={approvalBusy === approval.action_id}
                    onClick={() => decideApproval(approval, true)}
                    className="px-3 py-2 rounded bg-green-600 text-white disabled:opacity-50"
                  >
                    Authorize exact scope once
                  </button>
                </div>
              </div>
            ))}
          </Card>
        </section>

        {/* Editable plan approval */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <FileText className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Plan Review</h2>
          </div>
          <Card className="space-y-4">
            <p className="text-sm text-text-secondary">
              In “Approve each plan” mode, no plan step runs until you review the full sequence.
              Editing any step creates a new revision and invalidates prior approval. Level-3
              actions still require their own exact-payload authorization.
            </p>
            {reviewedPlans.length === 0 ? (
              <p className="text-sm text-text-muted">No execution plans are waiting for review.</p>
            ) : reviewedPlans.map((plan) => {
              const draft = planDrafts[plan.plan_id] || plan.snapshot.steps;
              const busy = planBusy === plan.plan_id;
              return (
                <div key={plan.plan_id} className="rounded border border-border p-4 space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="font-medium text-text-primary">{plan.goal_title}</h3>
                      <p className="text-xs text-text-muted">
                        {plan.plan_id} · revision {plan.revision}
                      </p>
                    </div>
                    <span className="text-xs px-2 py-1 rounded bg-background-secondary text-text-secondary">
                      {plan.status}
                    </span>
                  </div>

                  <div className="space-y-3">
                    {draft.map((step, index) => (
                      <div key={step.step_id} className="rounded bg-background-secondary p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-medium text-text-muted">Step {index + 1} · {step.task_type}</span>
                          <code className="text-xs text-text-muted">{step.step_id}</code>
                        </div>
                        <select
                          value={step.task_type}
                          disabled={busy || plan.status === 'executed'}
                          onChange={(event) => setPlanDrafts((current) => ({
                            ...current,
                            [plan.plan_id]: draft.map((item, itemIndex) =>
                              itemIndex === index ? { ...item, task_type: event.target.value } : item
                            ),
                          }))}
                          className="w-full mb-2 px-3 py-2 bg-background-primary border border-border rounded text-sm"
                        >
                          <option value="analysis">Analysis</option>
                          <option value="information_gathering">Information gathering</option>
                          <option value="optimization">Optimization</option>
                          <option value="maintenance">Maintenance</option>
                          <option value="exploration">Exploration</option>
                          <option value="user_assistance">User assistance</option>
                        </select>
                        {step.action_type && (
                          <>
                            <input
                              value={step.action_type}
                              disabled={busy || plan.status === 'executed'}
                              onChange={(event) => setPlanDrafts((current) => ({
                                ...current,
                                [plan.plan_id]: draft.map((item, itemIndex) =>
                                  itemIndex === index ? { ...item, action_type: event.target.value } : item
                                ),
                              }))}
                              className="w-full mb-2 px-3 py-2 bg-background-primary border border-border rounded font-mono text-xs"
                              aria-label={`Action type for step ${index + 1}`}
                            />
                            <textarea
                              key={`${plan.plan_id}-${plan.revision}-${step.step_id}-payload`}
                              defaultValue={JSON.stringify(step.payload, null, 2)}
                              disabled={busy || plan.status === 'executed'}
                              onBlur={(event) => {
                                try {
                                  const payload = JSON.parse(event.target.value);
                                  if (!payload || Array.isArray(payload) || typeof payload !== 'object') throw new Error();
                                  setPlanDrafts((current) => ({
                                    ...current,
                                    [plan.plan_id]: draft.map((item, itemIndex) =>
                                      itemIndex === index ? { ...item, payload } : item
                                    ),
                                  }));
                                } catch {
                                  notifications.error('Step payload must be a valid JSON object');
                                }
                              }}
                              className="w-full mb-2 min-h-24 px-3 py-2 bg-background-primary border border-border rounded font-mono text-xs"
                              aria-label={`Payload for step ${index + 1}`}
                            />
                          </>
                        )}
                        <textarea
                          value={step.description}
                          disabled={busy || plan.status === 'executed'}
                          onChange={(event) => setPlanDrafts((current) => ({
                            ...current,
                            [plan.plan_id]: draft.map((item, itemIndex) =>
                              itemIndex === index ? { ...item, description: event.target.value } : item
                            ),
                          }))}
                          className="w-full min-h-20 px-3 py-2 bg-background-primary border border-border rounded text-sm"
                        />
                        <input
                          value={step.success_criteria.join(', ')}
                          disabled={busy || plan.status === 'executed'}
                          onChange={(event) => setPlanDrafts((current) => ({
                            ...current,
                            [plan.plan_id]: draft.map((item, itemIndex) => itemIndex === index ? {
                              ...item,
                              success_criteria: event.target.value.split(',').map((value) => value.trim()).filter(Boolean),
                            } : item),
                          }))}
                          className="w-full mt-2 px-3 py-2 bg-background-primary border border-border rounded text-xs"
                          placeholder="Success criteria, comma separated"
                        />
                        {step.depends_on.length > 0 && (
                          <p className="text-xs text-text-muted mt-1">Depends on: {step.depends_on.join(', ')}</p>
                        )}
                      </div>
                    ))}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {plan.status !== 'executed' && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => savePlanEdits(plan)}
                        className="px-3 py-2 rounded border border-border text-text-primary disabled:opacity-50"
                      >
                        Save edits as new revision
                      </button>
                    )}
                    {plan.status === 'pending' && (
                      <>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => decidePlan(plan, false)}
                          className="px-3 py-2 rounded bg-red-600 text-white disabled:opacity-50"
                        >
                          Reject plan
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => decidePlan(plan, true)}
                          className="px-3 py-2 rounded bg-green-600 text-white disabled:opacity-50"
                        >
                          Approve revision {plan.revision}
                        </button>
                      </>
                    )}
                    {plan.status === 'approved' && (
                      <>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => revokePlan(plan)}
                          className="px-3 py-2 rounded border border-red-500 text-red-500 disabled:opacity-50"
                        >
                          Revoke approval
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => executePlan(plan)}
                          className="px-3 py-2 rounded bg-accent-primary text-white disabled:opacity-50"
                        >
                          Execute approved plan
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </Card>
        </section>

        {/* Data Retention */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Database className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Data Retention</h2>
          </div>
          <Card className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Data Retention Period
              </label>
              <select
                value={dataRetentionDays}
                onChange={(e) => setDataRetentionDays(Number(e.target.value))}
                className="w-full px-3 py-2 bg-background-surface border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent-primary"
              >
                <option value={30}>30 days</option>
                <option value={60}>60 days</option>
                <option value={90}>90 days</option>
                <option value={180}>180 days</option>
                <option value={365}>1 year</option>
              </select>
              <p className="text-xs text-text-muted mt-1">
                Automatically delete data older than this period
              </p>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Auto-Delete Old Data</h3>
                <p className="text-xs text-text-muted mt-1">
                  Automatically delete data older than retention period
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoDeleteOldData}
                  onChange={(e) => setAutoDeleteOldData(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="relative w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
              </label>
            </div>
          </Card>
        </section>

        {/* Telemetry */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <BarChart3 className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Telemetry</h2>
          </div>
          <Card className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Enable Telemetry</h3>
                <p className="text-xs text-text-muted mt-1">
                  Send anonymous usage data to help improve Arena
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={enableTelemetry}
                  onChange={(e) => setEnableTelemetry(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="relative w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
              </label>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Share Usage Statistics</h3>
                <p className="text-xs text-text-muted mt-1">
                  Share aggregated usage statistics (no personal data)
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={shareUsageStats}
                  onChange={(e) => setShareUsageStats(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="relative w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
              </label>
            </div>
          </Card>
        </section>

        {/* Security */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <Lock className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Security</h2>
          </div>
          <Card className="space-y-4">
            <div className="rounded border border-border p-3">
              <h3 className="text-sm font-medium text-text-primary">Sensitive-action boundary</h3>
              <p className="text-xs text-text-muted mt-1">
                Manifest Level-3 actions always require explicit authorization. Use Owner Control above to make lower levels stricter.
              </p>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Log All Actions</h3>
                <p className="text-xs text-text-muted mt-1">
                  Log all actions for audit purposes
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={logAllActions}
                  onChange={(e) => setLogAllActions(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="relative w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
              </label>
            </div>
          </Card>
        </section>

        {/* Backup/Restore */}
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <FileText className="w-6 h-6 text-accent-primary" />
            <h2 className="text-2xl font-semibold text-text-primary">Backup & Restore</h2>
          </div>
          <Card className="space-y-4">
            <div>
              <h3 className="text-sm font-medium text-text-primary mb-2">Export Settings</h3>
              <p className="text-xs text-text-muted mb-3">
                Export your privacy settings to a JSON file
              </p>
              <button
                onClick={handleExport}
                className="flex items-center gap-2 px-4 py-2 bg-accent-primary text-white rounded hover:bg-accent-primary/90 transition-colors"
              >
                <Download className="w-4 h-4" />
                <span>Export Settings</span>
              </button>
            </div>

            <div className="border-t border-border pt-4">
              <h3 className="text-sm font-medium text-text-primary mb-2">Import Settings</h3>
              <p className="text-xs text-text-muted mb-3">
                Import privacy settings from a JSON file
              </p>
              <button
                onClick={() => setShowImportDialog(true)}
                className="flex items-center gap-2 px-4 py-2 bg-background-surface text-text-primary border border-border rounded hover:bg-background-surface/80 transition-colors"
              >
                <Upload className="w-4 h-4" />
                <span>Import Settings</span>
              </button>
            </div>
          </Card>
        </section>

        {/* Import Dialog */}
        {showImportDialog && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <Card className="max-w-2xl w-full mx-4">
              <h2 className="text-xl font-semibold text-text-primary mb-4">Import Settings</h2>
              <p className="text-sm text-text-secondary mb-4">
                Paste your settings JSON below:
              </p>
              <textarea
                value={importData}
                onChange={(e) => setImportData(e.target.value)}
                className="w-full h-64 px-3 py-2 bg-background-surface border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent-primary font-mono text-xs"
                placeholder='{"dataRetentionDays": 90, "autoDeleteOldData": true, ...}'
              />
              <div className="flex gap-3 mt-4">
                <button
                  onClick={handleImport}
                  className="px-4 py-2 bg-accent-primary text-white rounded hover:bg-accent-primary/90 transition-colors"
                >
                  Import
                </button>
                <button
                  onClick={() => {
                    setShowImportDialog(false);
                    setImportData('');
                  }}
                  className="px-4 py-2 bg-background-surface text-text-primary border border-border rounded hover:bg-background-surface/80 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
