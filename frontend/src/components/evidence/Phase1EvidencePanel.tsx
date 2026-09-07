import { useCallback, useEffect, useState } from 'react';
import {
  fetchCorrectionMeasurements,
  fetchPhase1Evidence,
} from '../../services/phase1Evidence';
import type {
  CorrectionMeasurements,
  Phase1EvidenceReport,
} from '../../services/phase1Evidence';

/**
 * Phase 1 evidence panel (Cognition page): the owner-visible view of the
 * EXISTING aggregate reports — collected task evaluations, per-strategy
 * success rates, paired baseline/adapted changes, and correction telemetry.
 *
 * Read-only by construction: nothing here records, authorizes, or scores.
 * "Insufficient evidence" is rendered as exactly that — the honest state,
 * never a zero-padded trend. Paired changes are descriptive observations,
 * not causality claims (the report's own note is quoted below the numbers).
 */

function pct(value: number | null | undefined): string {
  return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—';
}

export function Phase1EvidencePanel() {
  const [report, setReport] = useState<Phase1EvidenceReport | null>(null);
  const [corrections, setCorrections] = useState<CorrectionMeasurements | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [r, c] = await Promise.all([
        fetchPhase1Evidence(),
        fetchCorrectionMeasurements(),
      ]);
      setReport(r);
      setCorrections(c);
    } catch {
      setMessage('Could not load the evidence reports — is the server running?');
    } finally {
      setBusy(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setBusy(true);
    await load();
  }, [load]);

  useEffect(() => {
    // Initial fetch of an external system (the evidence API). Every setState
    // in `load` fires after its first await — never during the effect body.
    // eslint-disable-next-line react/set-state-in-effect
    void load();
  }, [load]);

  const strategies = Object.entries(report?.strategies ?? {}).sort((a, b) =>
    a[0].localeCompare(b[0]),
  );

  return (
    <section aria-label="Phase 1 evidence" className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Phase 1 evidence</h2>
        <button
          type="button"
          className="rounded border px-3 py-1 text-xs disabled:opacity-50"
          onClick={() => void refresh()}
          disabled={busy}
        >
          {busy ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      <p className="text-xs opacity-60">
        Owner-recorded observations only — measured against collected evidence, never a
        maturity score. Record evaluations from the Review response controls in chat.
      </p>

      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}

      {report && (
        <div className="space-y-3 text-sm">
          <p className="text-xs opacity-70">
            Status: <strong>{report.status}</strong> · split {report.split} ·{' '}
            {report.evaluation_count} evaluation(s) · {report.known_outcome_count} with a
            known outcome
            {report.evidence_sufficient ? '' : ' — insufficient evidence for trends yet'}
          </p>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className="rounded border p-2">
              <div className="text-xs opacity-60">Outcome success rate</div>
              <div className="text-lg font-semibold">{pct(report.outcome_success_rate)}</div>
            </div>
            <div className="rounded border p-2">
              <div className="text-xs opacity-60">Usefulness rate</div>
              <div className="text-lg font-semibold">{pct(report.usefulness_rate)}</div>
            </div>
            <div className="rounded border p-2">
              <div className="text-xs opacity-60">Paired improved / regressed</div>
              <div className="text-lg font-semibold">
                {report.paired_improved_count} / {report.paired_regressed_count}
              </div>
            </div>
            <div className="rounded border p-2">
              <div className="text-xs opacity-60">Evaluations noting a correction</div>
              <div className="text-lg font-semibold">{report.correction_received_count}</div>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold">Per-strategy outcomes</h3>
            {strategies.length === 0 ? (
              <p className="text-xs opacity-60">
                No strategy-linked evaluations recorded yet.
              </p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left opacity-60">
                    <th scope="col">Strategy (goal|action)</th>
                    <th scope="col">Evaluations</th>
                    <th scope="col">Known outcomes</th>
                    <th scope="col">Success rate</th>
                  </tr>
                </thead>
                <tbody>
                  {strategies.map(([name, group]) => (
                    <tr key={name}>
                      <td className="py-0.5">{name}</td>
                      <td>{group.evaluations}</td>
                      <td>{group.known_outcomes}</td>
                      <td>{pct(group.success_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {corrections && (
            <div>
              <h3 className="text-sm font-semibold">Correction telemetry</h3>
              <p className="text-xs opacity-70">
                {corrections.summary.total_corrections} correction(s),{' '}
                {corrections.summary.trace_linked_corrections} trace-linked ·{' '}
                {corrections.summary.strategy_update_count} local strategy update(s),{' '}
                {corrections.summary.generalized_update_count} generalized after repeated
                distinct corrections ·{' '}
                {corrections.summary.measured_latency_count} with measured receipt latency
              </p>
              <p className="text-xs opacity-60">{corrections.note}</p>
            </div>
          )}

          <p className="text-xs opacity-50">{report.note}</p>
        </div>
      )}
    </section>
  );
}
