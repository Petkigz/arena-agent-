import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../services/cognition', () => ({
  fetchOwnerCharter: vi.fn().mockResolvedValue({
    mission: 'full owner sovereignty',
    values: [],
    priorities: ['stability', 'speed'],
    communication_style: '',
    standing_directives: ['never fake evidence'],
    revision: 3,
    content_digest: 'd'.repeat(64),
    updated_at: '2026-08-26T00:00:00+00:00',
  }),
  updateOwnerCharter: vi.fn().mockResolvedValue({ revision: 4 }),
  fetchOwnerQuestions: vi.fn().mockResolvedValue([
    {
      question_id: 'oq_1', action_type: 'search_files',
      question_text: 'I am only 30% confident about executing search_files. Should I proceed?',
      reason: 'below threshold', calibrated_confidence: 0.3, threshold: 0.45,
      status: 'pending', created_at: '2026-08-26T00:00:00+00:00',
    },
  ]),
  answerOwnerQuestion: vi.fn().mockResolvedValue({ approval_action_id: 'act_9' }),
  fetchInducedSkills: vi.fn().mockResolvedValue([
    {
      candidate_id: 'isk_1', skill_name: 'induced_copy_then_compress',
      action_sequence: ['copy_file_verified', 'compress_files'],
      occurrences: 4, context_success_rate: 1.0, status: 'pending',
    },
  ]),
  decideInducedSkill: vi.fn().mockResolvedValue({ success: true }),
  fetchLearningProgress: vi.fn().mockResolvedValue([
    { action_type: 'browser_upload', earlier_rate: 0.3, recent_rate: 0.8, progress: 0.5,
      overall_rate: 0.55, learning_value: 0.4, status: 'improving' },
  ]),
  fetchOwnerModel: vi.fn().mockResolvedValue({
    consistently_approves: ['create_backup'],
    consistently_denies: ['delete_file'],
    peak_activity_hours_utc: [{ hour_utc: 9, actions: 12 }],
    counted_preferences: [],
  }),
}));

import { CognitionPage } from '../../app/routes/CognitionPage';
import {
  answerOwnerQuestion,
  decideInducedSkill,
  updateOwnerCharter,
} from '../../services/cognition';

function renderPage() {
  return render(
    <MemoryRouter>
      <CognitionPage />
    </MemoryRouter>,
  );
}

describe('CognitionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the charter with its revision and loads all panels', async () => {
    renderPage();
    expect(await screen.findByText(/revision 3/)).toBeTruthy();
    expect(screen.getByDisplayValue('full owner sovereignty')).toBeTruthy();
    expect(await screen.findByText(/30% confident/)).toBeTruthy();
    expect(await screen.findByText('induced_copy_then_compress')).toBeTruthy();
    expect(await screen.findByText('browser_upload')).toBeTruthy();
    expect(await screen.findByText(/create_backup/)).toBeTruthy();
  });

  it('saving the charter sends parsed priorities and directives', async () => {
    renderPage();
    await screen.findByText(/revision 3/);
    fireEvent.change(screen.getByLabelText(/Priorities/), {
      target: { value: 'stability\nnew priority' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Save charter/ }));
    await waitFor(() => expect(updateOwnerCharter).toHaveBeenCalled());
    expect(updateOwnerCharter).toHaveBeenCalledWith(
      expect.objectContaining({ priorities: ['stability', 'new priority'] }));
  });

  it('answering a question states that approval is not execution', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Approve exactly/ }));
    await waitFor(() => expect(answerOwnerQuestion).toHaveBeenCalledWith('oq_1', 'approve'));
    expect(await screen.findByText(/execution stays a separate action/)).toBeTruthy();
  });

  it('accepting an induced skill notes the gates still apply', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Accept skill/ }));
    await waitFor(() => expect(decideInducedSkill).toHaveBeenCalledWith('isk_1', true));
    expect(await screen.findByText(/still passes all gates/)).toBeTruthy();
  });

  it('shows honest empty states when nothing is pending', async () => {
    const { fetchOwnerQuestions } = await import('../../services/cognition');
    (fetchOwnerQuestions as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
    renderPage();
    expect(await screen.findByText(/No pending questions/)).toBeTruthy();
  });
});
