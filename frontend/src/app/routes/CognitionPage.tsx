import { useCallback, useEffect, useState } from 'react';
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
import type {
  InducedSkill,
  LearningTarget,
  OwnerCharter,
  OwnerModelReport,
  OwnerQuestion,
} from '../../services/cognition';

/**
 * Cognition page: owner surfaces for the F1 cognitive loops.
 * Charter (values → every reasoning cycle), uncertainty questions
 * (approve authorizes exactly — never executes), induced skills
 * (experience → reusable skill, owner-accepted), and measured learning
 * progress + counted owner patterns.
 */
export function CognitionPage() {
  const [charter, setCharter] = useState<OwnerCharter | null>(null);
  const [missionDraft, setMissionDraft] = useState('');
  const [prioritiesDraft, setPrioritiesDraft] = useState('');
  const [directivesDraft, setDirectivesDraft] = useState('');
  const [charterBusy, setCharterBusy] = useState(false);
  const [charterMessage, setCharterMessage] = useState('');

  const [questions, setQuestions] = useState<OwnerQuestion[]>([]);
  const [induced, setInduced] = useState<InducedSkill[]>([]);
  const [progress, setProgress] = useState<LearningTarget[]>([]);
  const [ownerModel, setOwnerModel] = useState<OwnerModelReport | null>(null);
  const [actionMessage, setActionMessage] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [c, q, i, p, m] = await Promise.all([
        fetchOwnerCharter(),
        fetchOwnerQuestions(),
        fetchInducedSkills(),
        fetchLearningProgress(),
        fetchOwnerModel(),
      ]);
      setCharter(c);
      setMissionDraft(c.mission ?? '');
      setPrioritiesDraft((c.priorities ?? []).join('\n'));
      setDirectivesDraft((c.standing_directives ?? []).join('\n'));
      setQuestions(q);
      setInduced(i);
      setProgress(p);
      setOwnerModel(m);
    } catch {
      setCharterMessage('Could not load cognition state — is the server running?');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const saveCharter = async () => {
    setCharterBusy(true);
    setCharterMessage('');
    try {
      const result = await updateOwnerCharter({
        mission: missionDraft,
        priorities: prioritiesDraft.split('\n').map((line) => line.trim()).filter(Boolean),
        standing_directives: directivesDraft.split('\n').map((line) => line.trim()).filter(Boolean),
      });
      setCharterMessage(`Charter saved as revision ${result.revision}. It informs every cycle; policy gates remain the authority.`);
      await refresh();
    } catch {
      setCharterMessage('Charter save failed.');
    } finally {
      setCharterBusy(false);
    }
  };

  const answerQuestion = async (questionId: string, answer: 'approve' | 'deny' | 'observe') => {
    try {
      const result = await answerOwnerQuestion(questionId, answer);
      const approval = (result as { approval_action_id?: string | null }).approval_action_id;
      setActionMessage(
        answer === 'approve' && approval
          ? `Exact approval created (${approval}); execution stays a separate action.`
          : `Answer recorded: ${answer}.`,
      );
      await refresh();
    } catch {
      setActionMessage('Answer failed.');
    }
  };

  const decideSkill = async (candidateId: string, accept: boolean) => {
    try {
      await decideInducedSkill(candidateId, accept);
      setActionMessage(accept ? 'Skill accepted into the taught library; execution still passes all gates.' : 'Candidate rejected.');
      await refresh();
    } catch {
      setActionMessage('Decision failed.');
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      <header>
        <h1 className="text-2xl font-bold">Cognition</h1>
        <p className="text-sm opacity-70">
          The learning loops: your values inform every cycle, uncertainty becomes a question,
          experience becomes skill, and progress is measured.
        </p>
      </header>

      <section aria-label="Owner charter" className="space-y-3">
        <h2 className="text-lg font-semibold">Owner Charter {charter ? `(revision ${charter.revision})` : ''}</h2>
        <p className="text-xs opacity-60">
          Your mission, priorities, and directives are loaded into every reasoning cycle. They inform;
          policy gates and your exact grants remain the authority.
        </p>
        <label className="block text-sm font-medium" htmlFor="charter-mission">Mission</label>
        <textarea
          id="charter-mission"
          className="w-full rounded border p-2 bg-transparent text-sm"
          rows={2}
          value={missionDraft}
          onChange={(event) => setMissionDraft(event.target.value)}
        />
        <label className="block text-sm font-medium" htmlFor="charter-priorities">Priorities (one per line, highest first)</label>
        <textarea
          id="charter-priorities"
          className="w-full rounded border p-2 bg-transparent text-sm"
          rows={3}
          value={prioritiesDraft}
          onChange={(event) => setPrioritiesDraft(event.target.value)}
        />
        <label className="block text-sm font-medium" htmlFor="charter-directives">Standing directives (one per line)</label>
        <textarea
          id="charter-directives"
          className="w-full rounded border p-2 bg-transparent text-sm"
          rows={3}
          value={directivesDraft}
          onChange={(event) => setDirectivesDraft(event.target.value)}
        />
        <button
          type="button"
          onClick={() => void saveCharter()}
          disabled={charterBusy}
          className="rounded bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-50"
        >
          {charterBusy ? 'Saving…' : 'Save charter'}
        </button>
        {charterMessage && <p role="status" className="text-sm">{charterMessage}</p>}
      </section>

      <section aria-label="Uncertainty questions" className="space-y-3">
        <h2 className="text-lg font-semibold">Uncertainty Questions ({questions.length})</h2>
        {questions.length === 0 && <p className="text-sm opacity-70">No pending questions — nothing acted on weak evidence.</p>}
        <ul className="space-y-3">
          {questions.map((question) => (
            <li key={question.question_id} className="rounded border p-3 text-sm space-y-2">
              <p>{question.question_text}</p>
              <p className="text-xs opacity-60">
                {question.action_type} · confidence {Math.round(question.calibrated_confidence * 100)}% vs threshold {Math.round(question.threshold * 100)}%
              </p>
              <div className="flex gap-2">
                <button type="button" className="rounded border px-3 py-1" onClick={() => void answerQuestion(question.question_id, 'approve')}>Approve exactly</button>
                <button type="button" className="rounded border px-3 py-1" onClick={() => void answerQuestion(question.question_id, 'deny')}>Deny</button>
                <button type="button" className="rounded border px-3 py-1" onClick={() => void answerQuestion(question.question_id, 'observe')}>Observe more</button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Induced skills" className="space-y-3">
        <h2 className="text-lg font-semibold">Induced Skills ({induced.length})</h2>
        {induced.length === 0 && <p className="text-sm opacity-70">No candidates yet — repeated successful sequences appear here for your review.</p>}
        <ul className="space-y-3">
          {induced.map((skill) => (
            <li key={skill.candidate_id} className="rounded border p-3 text-sm space-y-2">
              <p className="font-medium">{skill.skill_name}</p>
              <p className="text-xs opacity-60">
                {skill.action_sequence.join(' → ')} · {skill.occurrences} verified occurrences · {Math.round(skill.context_success_rate * 100)}% context success
              </p>
              <div className="flex gap-2">
                <button type="button" className="rounded border px-3 py-1" onClick={() => void decideSkill(skill.candidate_id, true)}>Accept skill</button>
                <button type="button" className="rounded border px-3 py-1" onClick={() => void decideSkill(skill.candidate_id, false)}>Reject</button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Learning progress" className="space-y-3">
        <h2 className="text-lg font-semibold">Learning Progress</h2>
        {progress.length === 0 && <p className="text-sm opacity-70">No measured domains yet — outcome evidence accumulates as work is verified.</p>}
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left opacity-60">
              <th className="py-1">Action</th>
              <th>Recent</th>
              <th>Progress</th>
              <th>Status</th>
              <th>Learning value</th>
            </tr>
          </thead>
          <tbody>
            {progress.map((target) => (
              <tr key={target.action_type} className="border-t">
                <td className="py-1">{target.action_type}</td>
                <td>{target.recent_rate === null ? '—' : `${Math.round(target.recent_rate * 100)}%`}</td>
                <td>{target.progress === null ? '—' : `${target.progress > 0 ? '+' : ''}${Math.round(target.progress * 100)}%`}</td>
                <td>{target.status}</td>
                <td>{target.learning_value.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {ownerModel && (
        <section aria-label="Owner model" className="space-y-2">
          <h2 className="text-lg font-semibold">Owner Patterns (counted, never assumed)</h2>
          <p className="text-sm">
            Consistently approves: {ownerModel.consistently_approves.length ? ownerModel.consistently_approves.join(', ') : '—'}
          </p>
          <p className="text-sm">
            Consistently denies: {ownerModel.consistently_denies.length ? ownerModel.consistently_denies.join(', ') : '—'}
          </p>
          <p className="text-xs opacity-60">
            Peak hours (UTC): {ownerModel.peak_activity_hours_utc.map((h) => `${String(h.hour_utc).padStart(2, '0')}:00`).join(', ') || '—'}
          </p>
        </section>
      )}

      {actionMessage && <p role="status" className="text-sm">{actionMessage}</p>}
    </div>
  );
}
