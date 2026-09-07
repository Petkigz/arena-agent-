import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { ClipboardCheck, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '../ui/Button';
import {
  loadResponseFeedback, newSubmissionId, recordResponseUsefulness, recordTaskEvaluation, getResponseExplanation,
  type EvaluationCondition, type EvaluationSplit, type TaskEvaluation,
  type TaskOutcome, type Usefulness, type UsefulnessFeedback, type ResponseExplanation,
} from '../../services/responseFeedback';

const fieldClass = 'mt-1 w-full rounded-lg border border-border-subtle bg-background-primary px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary disabled:opacity-50';
const ratingLabels = { helpful: 'Helpful', partially_helpful: 'Partly helpful', not_helpful: 'Not helpful', unknown: 'Not rated' };
type Attempt = { fingerprint: string; id: string };

function submissionId(attempt: { current: Attempt | null }, payload: unknown): string {
  const fingerprint = JSON.stringify(payload);
  if (!attempt.current || attempt.current.fingerprint !== fingerprint) {
    attempt.current = { fingerprint, id: newSubmissionId() };
  }
  return attempt.current.id;
}

export function ResponseFeedback({ traceId }: { traceId: string }) {
  const [open, setOpen] = useState(false);
  const [visited, setVisited] = useState(false);
  const panelId = useId();
  return (
    <div className="mt-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => { setVisited(true); setOpen(!open); }}
        className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-text-secondary hover:bg-background-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary"
      >
        <ClipboardCheck className="h-3.5 w-3.5" aria-hidden="true" />
        Review response
        {open ? <ChevronUp className="h-3 w-3" aria-hidden="true" /> : <ChevronDown className="h-3 w-3" aria-hidden="true" />}
      </button>
      {/* Keep the panel mounted after opening so closing it does not discard
          a pending request or its retry identity. No requests before first use. */}
      <div id={panelId} hidden={!open}>
        {visited && <FeedbackPanel key={traceId} traceId={traceId} />}
      </div>
    </div>
  );
}

function FeedbackPanel({ traceId }: { traceId: string }) {
  const id = useId();
  const [explanation, setExplanation] = useState<ResponseExplanation | null>(null);
  const [explanationBusy, setExplanationBusy] = useState(false);
  const [explanationError, setExplanationError] = useState('');

  const explain = async () => {
    if (explanationBusy) return;
    setExplanationBusy(true);
    setExplanationError('');
    try { setExplanation(await getResponseExplanation(traceId)); }
    catch (error) { setExplanationError(error instanceof Error ? error.message : 'Could not load the recorded evidence.'); }
    finally { setExplanationBusy(false); }
  };
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadError, setLoadError] = useState('');
  const [feedback, setFeedback] = useState<UsefulnessFeedback[]>([]);
  const [evaluations, setEvaluations] = useState<TaskEvaluation[]>([]);
  const [rating, setRating] = useState<Usefulness | ''>('');
  const [ratingNote, setRatingNote] = useState('');
  const [ratingBusy, setRatingBusy] = useState(false);
  const [ratingError, setRatingError] = useState('');
  const ratingInFlight = useRef(false);
  const ratingAttempt = useRef<Attempt | null>(null);
  const [taskKey, setTaskKey] = useState('');
  const [split, setSplit] = useState<EvaluationSplit | ''>('');
  const [condition, setCondition] = useState<EvaluationCondition>('single');
  const [outcome, setOutcome] = useState<TaskOutcome>('unknown');
  const [taskRating, setTaskRating] = useState<Usefulness | 'unknown'>('unknown');
  const [corrected, setCorrected] = useState(false);
  const [evidence, setEvidence] = useState('');
  const [taskNote, setTaskNote] = useState('');
  const [taskBusy, setTaskBusy] = useState(false);
  const [taskError, setTaskError] = useState('');
  const taskInFlight = useRef(false);
  const taskAttempt = useRef<Attempt | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadResponseFeedback(traceId, controller.signal).then((history) => {
      if (controller.signal.aborted) return;
      setFeedback(history.feedback);
      setEvaluations(history.evaluations);
      setLoadState('ready');
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      setLoadError(error instanceof Error ? error.message : 'Could not load recorded feedback.');
      setLoadState('error');
    });
    return () => controller.abort();
  }, [traceId, loadAttempt]);

  const latestRating = feedback.at(-1);
  const existingTask = evaluations.find((item) =>
    item.task_key === taskKey.trim() && item.split === split && (
      item.condition === condition || (item.condition !== 'single' && condition !== 'single')
    ),
  );

  const saveRating = async (event: FormEvent) => {
    event.preventDefault();
    if (!rating || ratingInFlight.current || latestRating || loadState !== 'ready') return;
    ratingInFlight.current = true;
    setRatingBusy(true);
    setRatingError('');
    const payload = { usefulness: rating, note: ratingNote.trim() };
    try {
      const receipt = await recordResponseUsefulness(traceId, {
        ...payload, submission_id: submissionId(ratingAttempt, payload),
      });
      setFeedback((items) => [...items.filter((item) => item.feedback_id !== receipt.feedback_id), receipt]);
    } catch (error) {
      setRatingError(error instanceof Error ? error.message : 'Feedback was not confirmed. Retry the same submission.');
    } finally {
      ratingInFlight.current = false;
      setRatingBusy(false);
    }
  };

  const saveTask = async (event: FormEvent) => {
    event.preventDefault();
    if (taskKey.trim().length < 3 || !split || taskInFlight.current || existingTask || loadState !== 'ready') return;
    const evidenceIds = evidence.split('\n').map((value) => value.trim()).filter(Boolean);
    if (evidenceIds.length > 20) {
      setTaskError('Use at most 20 evidence references. Nothing was submitted.');
      return;
    }
    taskInFlight.current = true;
    setTaskBusy(true);
    setTaskError('');
    const payload = {
      task_key: taskKey.trim(), split, condition, observed_outcome: outcome,
      usefulness: taskRating, correction_received: corrected,
      evidence_ids: evidenceIds, note: taskNote.trim(),
    };
    try {
      const receipt = await recordTaskEvaluation(traceId, {
        ...payload, submission_id: submissionId(taskAttempt, payload),
      });
      setEvaluations((items) => [...items.filter((item) => item.evaluation_id !== receipt.evaluation_id), receipt]);
    } catch (error) {
      setTaskError(error instanceof Error ? error.message : 'Evaluation was not confirmed. Retry the same submission.');
    } finally {
      taskInFlight.current = false;
      setTaskBusy(false);
    }
  };

  return (
    <section aria-label="Response review" className="mt-2 space-y-4 rounded-lg border border-border-subtle bg-background-secondary p-4 text-sm text-text-secondary">
      <div>
        <h3 className="font-medium text-text-primary">Your assessment of this response</h3>
        <p className="mt-1 text-xs">Feedback never changes verified truth, authorizes an action, or approves training.</p>
        <details className="mt-2 text-xs text-text-muted">
          <summary className="cursor-pointer">Exact trace reference</summary>
          <code className="mt-1 block break-all">{traceId}</code>
        </details>
      </div>

      <div className="space-y-2 border-t border-border-subtle pt-3">
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" variant="secondary" size="sm" isLoading={explanationBusy} onClick={explain}>
            Why this response?
          </Button>
          <a className="text-xs text-accent-primary underline" href={`/settings/models?correctionTrace=${encodeURIComponent(traceId)}`}>
            Correct this response
          </a>
        </div>
        {explanationError && <p role="alert" className="text-accent-error">{explanationError}</p>}
        {explanation && <div aria-label="Recorded response evidence" className="space-y-1 text-xs">
          <p className="font-medium text-text-primary">Recorded evidence — not private reasoning</p>
          <ul className="list-disc space-y-1 pl-4">
            {explanation.explanation.slice(0, 12).map((line, index) => <li key={index}>{line}</li>)}
          </ul>
          <p className="text-text-muted">Confidence basis: {explanation.epistemic_presentation?.calibration_status || 'unrecorded'}.</p>
        </div>}
      </div>

      {loadState === 'loading' && <p role="status">Loading recorded feedback…</p>}
      {loadState === 'error' && (
        <div>
          <p role="alert" className="text-accent-error">{loadError}</p>
          <Button type="button" variant="secondary" size="sm" className="mt-2" onClick={() => {
            setLoadState('loading'); setLoadError(''); setLoadAttempt((attempt) => attempt + 1);
          }}>Retry loading</Button>
        </div>
      )}

      {loadState === 'ready' && <>
        {latestRating ? (
          <div role="status" className="rounded-lg bg-background-primary p-3">
            <p>Usefulness recorded: <strong>{ratingLabels[latestRating.usefulness]}</strong></p>
            <p className="mt-1 text-xs text-text-muted">{latestRating.note || 'No note added.'}</p>
          </div>
        ) : (
          <form onSubmit={saveRating} aria-label="Response usefulness">
            <fieldset disabled={ratingBusy} className="space-y-3">
              <div>
                <label htmlFor={`${id}-rating`}>How useful was this response?</label>
                <select id={`${id}-rating`} required value={rating} onChange={(event) => setRating(event.target.value as Usefulness)} className={fieldClass}>
                  <option value="" disabled>Choose a rating</option>
                  <option value="helpful">Helpful</option>
                  <option value="partially_helpful">Partly helpful</option>
                  <option value="not_helpful">Not helpful</option>
                </select>
              </div>
              <div>
                <label htmlFor={`${id}-rating-note`}>Feedback note (optional)</label>
                <textarea id={`${id}-rating-note`} maxLength={2000} rows={2} value={ratingNote} onChange={(event) => setRatingNote(event.target.value)} className={fieldClass} />
              </div>
              <p className="text-xs text-text-muted">Repeated owner feedback can influence the existing strategy ranking. A rating is not proof that an answer is correct.</p>
              {ratingError && <p role="alert" className="text-accent-error">{ratingError}</p>}
              <Button type="submit" size="sm" disabled={!rating} isLoading={ratingBusy}>Save usefulness</Button>
            </fieldset>
          </form>
        )}

        <details className="border-t border-border-subtle pt-3">
          <summary className="cursor-pointer font-medium text-text-primary">Record a task evaluation</summary>
          <p className="mt-2 text-xs">Measurement only: this does not submit a strategy-learning rating. Baseline/adapted labels describe work you already tested; they do not switch models, reset memory, or run tasks.</p>
          <form onSubmit={saveTask} aria-label="Task evaluation" className="mt-3">
            <fieldset disabled={taskBusy} className="space-y-3">
              <div>
                <label htmlFor={`${id}-task`}>Task comparison key</label>
                <input id={`${id}-task`} required minLength={3} maxLength={200} value={taskKey} onChange={(event) => setTaskKey(event.target.value)} placeholder="e.g. report-search-round-1" className={fieldClass} />
                <p className="mt-1 text-xs text-text-muted">Use the same key on the separate baseline and adapted responses for one comparison.</p>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label htmlFor={`${id}-split`}>Evaluation type</label>
                  <select id={`${id}-split`} required value={split} onChange={(event) => setSplit(event.target.value as EvaluationSplit)} className={fieldClass}>
                    <option value="" disabled>Choose a task type</option>
                    <option value="held_out">Held-out task (selected beforehand)</option>
                    <option value="contract">Routine / contract check</option>
                  </select>
                </div>
                <div>
                  <label htmlFor={`${id}-condition`}>Comparison condition</label>
                  <select id={`${id}-condition`} value={condition} onChange={(event) => setCondition(event.target.value as EvaluationCondition)} className={fieldClass}>
                    <option value="single">Single observation</option>
                    <option value="baseline">Baseline</option>
                    <option value="adapted">Adapted</option>
                  </select>
                </div>
                <div>
                  <label htmlFor={`${id}-outcome`}>Observed task outcome</label>
                  <select id={`${id}-outcome`} value={outcome} onChange={(event) => setOutcome(event.target.value as TaskOutcome)} className={fieldClass}>
                    <option value="unknown">Unknown / not verified by me</option>
                    <option value="success">Success — I checked the result</option>
                    <option value="failure">Failure — I checked the result</option>
                  </select>
                </div>
                <div>
                  <label htmlFor={`${id}-task-rating`}>Task usefulness</label>
                  <select id={`${id}-task-rating`} value={taskRating} onChange={(event) => setTaskRating(event.target.value as Usefulness | 'unknown')} className={fieldClass}>
                    <option value="unknown">Not rated</option>
                    <option value="helpful">Helpful</option>
                    <option value="partially_helpful">Partly helpful</option>
                    <option value="not_helpful">Not helpful</option>
                  </select>
                </div>
              </div>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={corrected} onChange={(event) => setCorrected(event.target.checked)} className="accent-accent-primary" />
                I needed a correction
              </label>
              <div>
                <label htmlFor={`${id}-evidence`}>Evidence references (optional, one per line)</label>
                <textarea id={`${id}-evidence`} rows={2} maxLength={4000} value={evidence} onChange={(event) => setEvidence(event.target.value)} className={fieldClass} />
              </div>
              <div>
                <label htmlFor={`${id}-task-note`}>What did you check? (optional)</label>
                <textarea id={`${id}-task-note`} rows={2} maxLength={1000} value={taskNote} onChange={(event) => setTaskNote(event.target.value)} className={fieldClass} />
              </div>
              {taskError && <p role="alert" className="text-accent-error">{taskError}</p>}
              {existingTask && <p role="status">
                {existingTask.condition === condition
                  ? `Evaluation already recorded for this response, task key, and condition: ${existingTask.observed_outcome}.`
                  : 'Baseline and adapted evaluations must use different responses. This response already has a paired condition recorded.'}
              </p>}
              <Button type="submit" size="sm" disabled={taskKey.trim().length < 3 || !split || !!existingTask} isLoading={taskBusy}>Save task evaluation</Button>
            </fieldset>
          </form>
          {evaluations.length > 0 && (
            <div className="mt-3 text-xs text-text-muted">
              <p className="font-medium">Recorded evaluations for this response</p>
              <ul className="mt-1 space-y-1">
                {evaluations.slice(-5).map((item) => <li key={item.evaluation_id}>
                  {item.task_key} · {item.split === 'held_out' ? 'held-out' : 'contract'} · {item.condition} · {item.observed_outcome}
                </li>)}
              </ul>
            </div>
          )}
          <p className="mt-3 text-xs text-text-muted">Owner-recorded observations are descriptive evidence, not proof of causality or general intelligence. Avoid secrets in notes and references.</p>
        </details>
      </>}
    </section>
  );
}
