import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ResponseFeedback } from '../../components/chat/ResponseFeedback';
import { MessageBubble } from '../../components/chat/MessageBubble';
import * as api from '../../services/responseFeedback';

vi.mock('../../services/responseFeedback', () => ({
  loadResponseFeedback: vi.fn(), recordResponseUsefulness: vi.fn(), recordTaskEvaluation: vi.fn(),
  newSubmissionId: vi.fn(),
}));

const ratingReceipt: api.UsefulnessFeedback = {
  feedback_id: 'feedback-web-test', trace_id: 'trace-a', usefulness: 'helpful',
  outcome_signal: '', retrieval_useful: null, note: '', created_at: '2026-09-07T10:00:00Z',
};
const taskReceipt: api.TaskEvaluation = {
  evaluation_id: 'evaluation-web-test', trace_id: 'trace-a', task_key: 'report-search-round-1',
  split: 'held_out', condition: 'baseline', observed_outcome: 'unknown', usefulness: 'unknown',
  correction_received: false, note: '', created_at: '2026-09-07T10:00:00Z',
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.loadResponseFeedback).mockResolvedValue({ feedback: [], evaluations: [] });
  vi.mocked(api.recordResponseUsefulness).mockResolvedValue(ratingReceipt);
  vi.mocked(api.recordTaskEvaluation).mockResolvedValue(taskReceipt);
  vi.mocked(api.newSubmissionId).mockReturnValue('web-test-123');
});
afterEach(cleanup);

async function openReview() {
  render(<ResponseFeedback traceId="trace-a" />);
  fireEvent.click(screen.getByRole('button', { name: 'Review response' }));
  await screen.findByLabelText('How useful was this response?');
}
function fillTask() {
  fireEvent.click(screen.getByText('Record a task evaluation'));
  fireEvent.change(screen.getByLabelText('Task comparison key'), { target: { value: 'report-search-round-1' } });
  fireEvent.change(screen.getByLabelText('Evaluation type'), { target: { value: 'held_out' } });
  fireEvent.change(screen.getByLabelText('Comparison condition'), { target: { value: 'baseline' } });
}

describe('response feedback controls', () => {
  it('does not load or record anything until the owner opens the review', async () => {
    render(<ResponseFeedback traceId="trace-a" />);
    expect(api.loadResponseFeedback).not.toHaveBeenCalled();
    expect(api.recordResponseUsefulness).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Review response' }));
    await screen.findByLabelText('How useful was this response?');
    expect(api.loadResponseFeedback).toHaveBeenCalledWith('trace-a', expect.any(AbortSignal));
    expect(screen.getByRole('button', { name: 'Save usefulness' })).toBeDisabled();
    expect(screen.getByLabelText('Observed task outcome')).toHaveValue('unknown');
    expect(screen.getByLabelText('Evaluation type')).toHaveValue('');
  });

  it('saves an explicit rating to this trace and displays the real receipt', async () => {
    await openReview();
    fireEvent.change(screen.getByLabelText('How useful was this response?'), { target: { value: 'helpful' } });
    fireEvent.change(screen.getByLabelText('Feedback note (optional)'), { target: { value: 'Clear answer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save usefulness' }));
    await screen.findByText(/Usefulness recorded:/);
    expect(api.recordResponseUsefulness).toHaveBeenCalledWith('trace-a', {
      usefulness: 'helpful', note: 'Clear answer', submission_id: 'web-test-123',
    });
    expect(api.recordTaskEvaluation).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Save usefulness' })).toBeNull();
  });

  it('guards double clicks while the submission is in flight', async () => {
    let finish!: (receipt: api.UsefulnessFeedback) => void;
    vi.mocked(api.recordResponseUsefulness).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    await openReview();
    fireEvent.change(screen.getByLabelText('How useful was this response?'), { target: { value: 'helpful' } });
    const button = screen.getByRole('button', { name: 'Save usefulness' });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(api.recordResponseUsefulness).toHaveBeenCalledTimes(1);
    expect(button).toBeDisabled();
    await act(async () => finish(ratingReceipt));
    await screen.findByText(/Usefulness recorded:/);
  });

  it('shows a failed request honestly and reuses the retry identity', async () => {
    vi.mocked(api.recordResponseUsefulness).mockRejectedValueOnce(new Error('Connection lost; save not confirmed'));
    await openReview();
    fireEvent.change(screen.getByLabelText('How useful was this response?'), { target: { value: 'helpful' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save usefulness' }));
    await screen.findByRole('alert');
    expect(screen.queryByText(/Usefulness recorded:/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Save usefulness' }));
    await screen.findByText(/Usefulness recorded:/);
    expect(api.newSubmissionId).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.recordResponseUsefulness).mock.calls[0]).toEqual(vi.mocked(api.recordResponseUsefulness).mock.calls[1]);
  });

  it('loads an existing rating without recording a duplicate after reopening', async () => {
    vi.mocked(api.loadResponseFeedback).mockResolvedValue({ feedback: [ratingReceipt], evaluations: [] });
    render(<ResponseFeedback traceId="trace-a" />);
    fireEvent.click(screen.getByRole('button', { name: 'Review response' }));
    await screen.findByText(/Usefulness recorded:/);
    expect(screen.queryByRole('button', { name: 'Save usefulness' })).toBeNull();
    expect(api.recordResponseUsefulness).not.toHaveBeenCalled();
  });

  it('records UNKNOWN task results separately, without a learning rating or automatic success', async () => {
    await openReview();
    fillTask();
    fireEvent.click(screen.getByRole('button', { name: 'Save task evaluation' }));
    await screen.findByText(/Evaluation already recorded/);
    expect(api.recordTaskEvaluation).toHaveBeenCalledWith('trace-a', {
      task_key: 'report-search-round-1', split: 'held_out', condition: 'baseline',
      observed_outcome: 'unknown', usefulness: 'unknown', correction_received: false,
      evidence_ids: [], note: '', submission_id: 'web-test-123',
    });
    expect(api.recordResponseUsefulness).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Save task evaluation' })).toBeDisabled();
  });

  it('does not let the same response stand for both baseline and adapted conditions', async () => {
    vi.mocked(api.loadResponseFeedback).mockResolvedValue({ feedback: [], evaluations: [taskReceipt] });
    await openReview();
    fillTask();
    fireEvent.change(screen.getByLabelText('Comparison condition'), { target: { value: 'adapted' } });
    expect(screen.getByText(/Baseline and adapted evaluations must use different responses/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save task evaluation' })).toBeDisabled();
    expect(api.recordTaskEvaluation).not.toHaveBeenCalled();
  });

  it('requires explicit task classification and preserves owner-supplied evidence', async () => {
    await openReview();
    fireEvent.click(screen.getByText('Record a task evaluation'));
    fireEvent.change(screen.getByLabelText('Task comparison key'), { target: { value: 'report-search-round-1' } });
    expect(screen.getByRole('button', { name: 'Save task evaluation' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Evaluation type'), { target: { value: 'contract' } });
    fireEvent.change(screen.getByLabelText('Observed task outcome'), { target: { value: 'success' } });
    fireEvent.change(screen.getByLabelText('Evidence references (optional, one per line)'), { target: { value: ' file:report.pdf\nowner:checked-hash ' } });
    fireEvent.click(screen.getByLabelText('I needed a correction'));
    fireEvent.click(screen.getByRole('button', { name: 'Save task evaluation' }));
    await waitFor(() => expect(api.recordTaskEvaluation).toHaveBeenCalled());
    expect(vi.mocked(api.recordTaskEvaluation).mock.calls[0][1]).toMatchObject({
      split: 'contract', observed_outcome: 'success', correction_received: true,
      evidence_ids: ['file:report.pdf', 'owner:checked-hash'],
    });
  });

  it('blocks new submissions when history loading fails, with an explicit retry', async () => {
    vi.mocked(api.loadResponseFeedback).mockRejectedValueOnce(new Error('Backend unavailable'));
    render(<ResponseFeedback traceId="trace-a" />);
    fireEvent.click(screen.getByRole('button', { name: 'Review response' }));
    await screen.findByRole('alert');
    expect(screen.queryByRole('button', { name: 'Save usefulness' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading' }));
    await screen.findByLabelText('How useful was this response?');
    expect(api.loadResponseFeedback).toHaveBeenCalledTimes(2);
  });

  it('keeps legacy and unfinished messages unreviewable, but reacts to a late exact trace', () => {
    const message = { id: 'reply', role: 'assistant' as const, content: 'Answer', timestamp: '2026-09-07', status: 'complete' as const };
    const { rerender } = render(<MessageBubble message={message} />);
    expect(screen.queryByRole('button', { name: 'Review response' })).toBeNull();
    rerender(<MessageBubble message={{ ...message, traceId: 'trace-a' }} />);
    expect(screen.getByRole('button', { name: 'Review response' })).toBeInTheDocument();
    rerender(<MessageBubble message={{ ...message, traceId: 'trace-a', status: 'streaming' }} />);
    expect(screen.queryByRole('button', { name: 'Review response' })).toBeNull();
  });
});
