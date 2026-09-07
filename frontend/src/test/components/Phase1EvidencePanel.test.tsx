import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Phase1EvidencePanel } from '../../components/evidence/Phase1EvidencePanel';
import * as api from '../../services/phase1Evidence';

vi.mock('../../services/phase1Evidence', () => ({
  fetchPhase1Evidence: vi.fn(),
  fetchCorrectionMeasurements: vi.fn(),
}));

const measuredReport: api.Phase1EvidenceReport = {
  status: 'measured',
  split: 'held_out',
  recorded_evaluation_count: 6,
  evaluation_count: 5,
  known_outcome_trace_count: 3,
  evidence_sufficient: true,
  known_outcome_count: 4,
  outcome_counts: { success: 3, failure: 1 },
  outcome_success_rate: 0.75,
  known_usefulness_count: 4,
  usefulness_counts: { helpful: 3, not_helpful: 1 },
  usefulness_rate: 0.875,
  correction_received_count: 2,
  strategies: {
    'file_search|search_files': {
      evaluations: 3,
      known_outcomes: 2,
      successes: 2,
      success_rate: 1,
    },
  },
  paired_comparison_count: 1,
  paired_improved_count: 1,
  paired_regressed_count: 0,
  paired_observations: [],
  window: { order: 'most_recent', record_limit: 5000 },
  note: 'Descriptive only.',
};

const correctionMeasurements: api.CorrectionMeasurements = {
  summary: {
    total_corrections: 3,
    trace_linked_corrections: 3,
    measured_latency_count: 2,
    mean_latency_ms: 1200,
    strategy_update_count: 1,
    generalized_update_count: 0,
    correction_types: { factual: 2, routing: 1 },
  },
  note: 'latency is a bounded telemetry proxy, not human reaction time',
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.fetchPhase1Evidence).mockResolvedValue(measuredReport);
  vi.mocked(api.fetchCorrectionMeasurements).mockResolvedValue(correctionMeasurements);
});
afterEach(cleanup);

describe('Phase1EvidencePanel', () => {
  it('renders the measured aggregates and per-strategy rows', async () => {
    render(<Phase1EvidencePanel />);

    await waitFor(() => {
      expect(screen.getByText('measured')).toBeInTheDocument();
    });
    expect(screen.getByText('75.0%')).toBeInTheDocument();
    expect(screen.getByText('87.5%')).toBeInTheDocument();
    expect(screen.getByText('file_search|search_files')).toBeInTheDocument();
    expect(screen.getByText(/3 correction\(s\), 3 trace-linked/)).toBeInTheDocument();
    expect(
      screen.getByText('latency is a bounded telemetry proxy, not human reaction time'),
    ).toBeInTheDocument();
    expect(screen.getByText('Descriptive only.')).toBeInTheDocument();
    // Never claims a maturity score.
    expect(screen.getByText(/never a maturity score/i)).toBeInTheDocument();
  });

  it('renders insufficient evidence as exactly that, not zero-padded trends', async () => {
    vi.mocked(api.fetchPhase1Evidence).mockResolvedValue({
      ...measuredReport,
      status: 'insufficient_evidence',
      evidence_sufficient: false,
      outcome_success_rate: null,
      usefulness_rate: null,
      strategies: {},
    });
    render(<Phase1EvidencePanel />);

    await waitFor(() => {
      expect(screen.getByText('insufficient_evidence')).toBeInTheDocument();
    });
    expect(screen.getByText(/insufficient evidence for trends yet/)).toBeInTheDocument();
    expect(screen.getByText('No strategy-linked evaluations recorded yet.')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('shows an honest load failure and keeps the retry affordance', async () => {
    vi.mocked(api.fetchPhase1Evidence).mockRejectedValue(new Error('down'));
    render(<Phase1EvidencePanel />);

    await waitFor(() => {
      expect(
        screen.getByText('Could not load the evidence reports — is the server running?'),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled();
  });
});
