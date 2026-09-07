import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { loadResponseFeedback, recordResponseUsefulness, recordTaskEvaluation } from '../../services/responseFeedback';

vi.mock('../../services/api', () => ({
  apiUrl: (path: string) => `/backend${path}`,
  apiKeyHeader: () => ({ 'X-API-Key': 'test-owner-key' }),
}));

const fetchMock = vi.fn();
const response = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body });
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock); });
afterEach(() => vi.unstubAllGlobals());

describe('response feedback API', () => {
  it('loads only exact-trace history in both task splits with authentication', async () => {
    fetchMock.mockResolvedValueOnce(response({ success: true, feedback: [{ trace_id: 'trace/a', feedback_id: 'f' }] }))
      .mockResolvedValueOnce(response({ success: true, evaluations: [{ trace_id: 'trace/a', evaluation_id: 'held', created_at: '2026-01-01' }] }))
      .mockResolvedValueOnce(response({ success: true, evaluations: [{ trace_id: 'wrong', evaluation_id: 'other', created_at: '2026-01-02' }] }));
    const result = await loadResponseFeedback('trace/a');
    expect(result.feedback).toHaveLength(1);
    expect(result.evaluations).toHaveLength(1);
    expect(fetchMock.mock.calls[0][0]).toBe('/backend/cognition/traces/trace%2Fa/usefulness');
    expect(fetchMock.mock.calls[1][0]).toContain('trace_id=trace%2Fa&split=held_out');
    expect(fetchMock.mock.calls[2][0]).toContain('trace_id=trace%2Fa&split=contract');
    for (const [, options] of fetchMock.mock.calls) {
      expect(options.headers['X-API-Key']).toBe('test-owner-key');
    }
  });

  it('passes the same retry ID through and requires a matching receipt', async () => {
    fetchMock.mockResolvedValue(response({ success: true, feedback: { feedback_id: 'f', trace_id: 'trace-a' } }));
    const submission = { usefulness: 'helpful' as const, note: '', submission_id: 'web-test-123' };
    await recordResponseUsefulness('trace-a', submission);
    await recordResponseUsefulness('trace-a', submission);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(submission);
    expect(fetchMock.mock.calls[1][1].body).toBe(fetchMock.mock.calls[0][1].body);
    fetchMock.mockResolvedValue(response({ success: true, feedback: { feedback_id: 'wrong', trace_id: 'trace-b' } }));
    await expect(recordResponseUsefulness('trace-a', submission)).rejects.toThrow('No matching feedback receipt');
  });

  it('records task assessment without silently sending strategy-learning feedback', async () => {
    fetchMock.mockResolvedValue(response({ success: true, evaluation: { evaluation_id: 'e', trace_id: 'trace-a' } }));
    await recordTaskEvaluation('trace-a', {
      task_key: 'held-out-task', split: 'held_out', condition: 'baseline',
      observed_outcome: 'unknown', usefulness: 'unknown', correction_received: false,
      note: '', evidence_ids: [], submission_id: 'web-test-123',
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('/backend/benchmarks/phase1/tasks/evaluations');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ trace_id: 'trace-a', observed_outcome: 'unknown' });
  });

  it('does not report save success from HTTP failure or success:false', async () => {
    const payload = { usefulness: 'helpful' as const, note: '', submission_id: 'web-test-123' };
    fetchMock.mockResolvedValue(response({ detail: 'Trace not found' }, 404));
    await expect(recordResponseUsefulness('trace-a', payload)).rejects.toThrow('Trace not found');
    fetchMock.mockResolvedValue(response({ success: false, error: 'Not saved' }));
    await expect(recordResponseUsefulness('trace-a', payload)).rejects.toThrow('Not saved');
  });

  it('rejects malformed history rather than treating failed loading as empty evidence', async () => {
    fetchMock.mockResolvedValue(response({ success: true }));
    await expect(loadResponseFeedback('trace-a')).rejects.toThrow('invalid feedback history');
  });
});
