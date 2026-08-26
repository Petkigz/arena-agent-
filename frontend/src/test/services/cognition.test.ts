import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockedFetch = vi.fn();
vi.stubGlobal('fetch', mockedFetch);

import {
  answerOwnerQuestion,
  decideInducedSkill,
  fetchInducedSkills,
  fetchLearningProgress,
  fetchOwnerCharter,
  fetchOwnerModel,
  fetchOwnerQuestions,
  updateOwnerCharter,
} from '../../services/cognition';

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

describe('cognition services', () => {
  beforeEach(() => {
    mockedFetch.mockReset();
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the charter from the owner API', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({ charter: { mission: 'm', revision: 2 } }));
    const charter = await fetchOwnerCharter();
    expect(charter.revision).toBe(2);
    expect(mockedFetch).toHaveBeenCalledWith('/owner-control/charter', expect.anything());
  });

  it('updates the charter with a PUT and a JSON body', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({ charter: { revision: 3 } }));
    const result = await updateOwnerCharter({ mission: 'new mission' });
    expect(result.revision).toBe(3);
    const [path, init] = mockedFetch.mock.calls[0];
    expect(path).toBe('/owner-control/charter');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body)).toEqual({ mission: 'new mission' });
  });

  it('answers a question with the exact answer payload', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({ success: true }));
    await answerOwnerQuestion('oq/9', 'approve', 'go ahead');
    const [path, init] = mockedFetch.mock.calls[0];
    expect(path).toBe('/owner-control/questions/oq%2F9/answer');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ answer: 'approve', note: 'go ahead' });
  });

  it('accepts and rejects induced skills on the right endpoints', async () => {
    mockedFetch.mockResolvedValue(jsonResponse({ success: true }));
    await decideInducedSkill('isk 1', true);
    await decideInducedSkill('isk 1', false);
    expect(mockedFetch.mock.calls[0][0]).toBe('/owner-control/induced-skills/isk%201/accept');
    expect(mockedFetch.mock.calls[1][0]).toBe('/owner-control/induced-skills/isk%201/reject');
  });

  it('lists questions, skills, progress, and the owner model', async () => {
    mockedFetch.mockResolvedValueOnce(jsonResponse({ questions: [{ question_id: 'q' }] }));
    mockedFetch.mockResolvedValueOnce(jsonResponse({ candidates: [{ candidate_id: 'c' }] }));
    mockedFetch.mockResolvedValueOnce(jsonResponse({ targets: [{ action_type: 'a' }] }));
    mockedFetch.mockResolvedValueOnce(jsonResponse({ consistently_approves: [] }));
    expect((await fetchOwnerQuestions()).length).toBe(1);
    expect((await fetchInducedSkills()).length).toBe(1);
    expect((await fetchLearningProgress()).length).toBe(1);
    expect((await fetchOwnerModel()).consistently_approves).toEqual([]);
    expect(mockedFetch.mock.calls[0][0]).toBe('/owner-control/questions?status=pending');
    expect(mockedFetch.mock.calls[1][0]).toBe('/owner-control/induced-skills?status=pending');
    expect(mockedFetch.mock.calls[2][0]).toBe('/owner-control/learning-progress');
    expect(mockedFetch.mock.calls[3][0]).toBe('/owner-control/owner-model');
  });

  it('throws honestly on failure instead of returning fake data', async () => {
    mockedFetch.mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({}) });
    await expect(fetchOwnerCharter()).rejects.toThrow('409');
  });
});
