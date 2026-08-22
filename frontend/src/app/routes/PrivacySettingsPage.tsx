import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../../components/ui';
import { usePrivacySettingsStore } from '../../stores';
import { ArrowLeft, Database, BarChart3, Lock, FileText, Download, Upload } from 'lucide-react';
import { notifications } from '../../services/notifications';
import { apiKeyHeader } from '../../services/api';

type ControlMode =
  | 'observe_only'
  | 'suggest_only'
  | 'approve_every_action'
  | 'approve_each_plan'
  | 'bounded_autonomy'
  | 'custom';

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
  const [controlBusy, setControlBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch('/owner-control', { headers: apiKeyHeader() })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('Control policy unavailable')))
      .then((data) => { if (!cancelled) setOwnerPolicy(data.policy); })
      .catch(() => { if (!cancelled) notifications.error('Could not load owner control policy'); });
    return () => { cancelled = true; };
  }, []);

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
