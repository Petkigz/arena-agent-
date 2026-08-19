import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../../components/ui';
import { usePrivacySettingsStore } from '../../stores';
import { ArrowLeft, Database, BarChart3, Lock, FileText, Download, Upload } from 'lucide-react';
import { notifications } from '../../services/notifications';

export function PrivacySettingsPage() {
  const navigate = useNavigate();
  const {
    dataRetentionDays,
    autoDeleteOldData,
    enableTelemetry,
    shareUsageStats,
    requireApprovalForSensitiveActions,
    logAllActions,
    setDataRetentionDays,
    setAutoDeleteOldData,
    setEnableTelemetry,
    setShareUsageStats,
    setRequireApprovalForSensitiveActions,
    setLogAllActions,
    exportSettings,
    importSettings,
  } = usePrivacySettingsStore();

  const [importData, setImportData] = useState('');
  const [showImportDialog, setShowImportDialog] = useState(false);

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
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary">Require Approval for Sensitive Actions</h3>
                <p className="text-xs text-text-muted mt-1">
                  Ask for approval before executing sensitive actions
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={requireApprovalForSensitiveActions}
                  onChange={(e) => setRequireApprovalForSensitiveActions(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="relative w-11 h-6 bg-background-surface peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-accent-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-accent-primary"></div>
              </label>
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
