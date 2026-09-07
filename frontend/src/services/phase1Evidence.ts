import { requestJson as evidenceRequest } from './http';

/**
 * Phase 1 evidence services — owner-visible measurement of collected
 * correction/adaptation effects, read from the EXISTING aggregate endpoints.
 * Strictly read-only: this panel changes no store, authorizes nothing, and
 * never scores maturity. Absence of evidence renders as absence.
 */


export interface Phase1StrategyGroup {
  evaluations: number;
  known_outcomes: number;
  successes: number;
  success_rate: number | null;
}

export interface Phase1EvidenceReport {
  status: string;                 // "measured" | "insufficient_evidence"
  split: string;
  recorded_evaluation_count: number;
  evaluation_count: number;
  known_outcome_trace_count: number;
  evidence_sufficient: boolean;
  known_outcome_count: number;
  outcome_counts: Record<string, number>;
  outcome_success_rate: number | null;
  known_usefulness_count: number;
  usefulness_counts: Record<string, number>;
  usefulness_rate: number | null;
  correction_received_count: number;
  strategies: Record<string, Phase1StrategyGroup>;
  paired_comparison_count: number;
  paired_improved_count: number;
  paired_regressed_count: number;
  paired_observations: Array<{
    task_key: string;
    baseline_trace_id: string;
    adapted_trace_id: string;
    baseline_outcome: string;
    adapted_outcome: string;
    observed_change: string;      // "improved" | "regressed" | "unchanged"
  }>;
  window: { order: string; record_limit: number };
  note: string;
}

export interface CorrectionSummaryReport {
  total_corrections: number;
  trace_linked_corrections: number;
  measured_latency_count: number;
  mean_latency_ms: number | null;
  strategy_update_count: number;
  generalized_update_count: number;
  correction_types: Record<string, number>;
}

export interface CorrectionMeasurements {
  summary: CorrectionSummaryReport;
  note: string;
}

export async function fetchPhase1Evidence(): Promise<Phase1EvidenceReport> {
  const data = await evidenceRequest<{ report: Phase1EvidenceReport }>(
    '/benchmarks/phase1/evidence',
  );
  if (!data.report || typeof data.report !== 'object') {
    throw new Error('The server returned no Phase 1 evidence report.');
  }
  return data.report;
}

export async function fetchCorrectionMeasurements(): Promise<CorrectionMeasurements> {
  const data = await evidenceRequest<{
    summary: CorrectionSummaryReport;
    note: string;
  }>('/cognition/corrections/measurements');
  if (!data.summary || typeof data.summary !== 'object') {
    throw new Error('The server returned no correction measurements.');
  }
  return { summary: data.summary, note: data.note };
}
