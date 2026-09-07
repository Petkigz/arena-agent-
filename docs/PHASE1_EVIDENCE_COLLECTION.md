# Phase 1.4 — Owner evidence collection

**Updated:** 2026-09-07

**Status:** collection workflow implemented; real-task usefulness and longitudinal improvement remain **unverified**.

This runbook uses the existing trace feedback and task-evaluation stores. It does
not introduce a second brain, authorize actions, approve training candidates, or
turn a helpful response into a verified success.

## 1. Start the owner installation

Build the web client from `frontend/` (commands shown separately for PowerShell):

```text
npm ci
npm run build
```

Start the unified backend from the repository root using the existing virtual
environment and inference profile. For example, on Windows:

```text
.venv\Scripts\python -m uvicorn app.server:app --host 127.0.0.1 --port 8000
```

On Linux/macOS, use `.venv/bin/python` instead. Open
`http://127.0.0.1:8000/chat`. Use LM Studio on the owner machine for real model
behavior. Offline responses can be rated as unavailable/unhelpful but are not
proof of model quality or generalization.

For LAN access, keep the existing API-key protections and configure the web
client's API key before building. Do not disable authentication to collect
feedback. No new packages or model downloads are required by this feature.

## 2. Review the exact response

1. Ask a task and wait for the assistant reply to finish.
2. Click **Review response** under that reply.
3. **Exact trace reference** shows the runtime-authored trace attached to that
   message. Never substitute the newest trace from another turn.
4. The panel loads existing records before enabling submission. A loading error
   is not treated as an empty history; use **Retry loading**.

New streamed message IDs and trace references persist in the existing
`conversations` table. They survive browser hydration and a backend restart.
Older rows retain their numeric IDs and have **no invented trace link**. Replies
without a trace or still streaming do not offer the review control. Send a new
request rather than trying to infer an old reply's trace by timestamp or text.

The web client consumes `cognitive_metadata` by **conversation ID + message ID**.
A metadata event can arrive before tokens, after tokens, or alongside history
hydration without selecting the latest message by position. Failed/traceless
cycles cannot reuse a preceding response's trace.

## 3. Two deliberately separate submissions

### Response usefulness — an owner feedback signal

Choose **Helpful**, **Partly helpful**, or **Not helpful**, optionally add a note,
and press **Save usefulness**.

- Writes to the existing `cognitive_trace_usefulness` table through
  `POST /cognition/traces/{trace_id}/usefulness`.
- Does not rewrite `goal_verified`, grounding, or execution evidence.
- Does not submit a held-out task evaluation or approve training.
- Repeated owner signals can influence the existing bounded strategy ranking.
  This is why the UI does not silently turn every task assessment into a learning
  signal.
- The normal web form shows the saved rating instead of offering another rating
  for the same response. Existing append-only API behavior is retained for
  explicit owner integrations.

### Task evaluation — measurement only

Expand **Record a task evaluation**. Enter:

- **Task comparison key:** a stable key for this specific comparison; use a new
  key for another repetition. Use the same key on the separate baseline/adapted
  responses belonging to one pair.
- **Evaluation type:** choose explicitly. A held-out task must have been selected
  before using its outcome to tune the system. Ordinary checks belong under
  **Routine / contract check**; do not relabel a fitted demonstration as held-out.
- **Comparison condition:** single, baseline, or adapted. These are descriptive
  labels, not commands to reset memory, switch models, or run tasks.
- **Observed task outcome:** defaults to **Unknown**. Only select success/failure
  after checking the result yourself.
- **Task usefulness:** defaults to **Not rated** and is stored only in the task
  evaluation, not in the strategy-learning feedback table.
- Optional correction flag, evidence references, and what you checked.

Press **Save task evaluation**. The existing
`POST /benchmarks/phase1/tasks/evaluations` endpoint records the observation.
Blank strategy/routing metadata is filled from the linked persisted trace when
available; absent facts remain absent. No model narration supplies these fields.

A baseline/adapted comparison needs different responses/traces. The web form will
not record both paired conditions for the same response and task. The backend
remains a descriptive owner-recorded ledger, not an experiment controller: the
owner is responsible for choosing valid tasks and maintaining the conditions.

Use only non-sensitive references and notes. Do not paste credentials or private
file contents into evaluation notes. References are owner statements, not
independent environmental verification.

## 4. Repeated real-task protocol

Before collecting outcomes, write down the task set, success criteria, evidence
checks, and which condition is baseline/adapted. Keep task families and model,
policy, environment, and memory changes explicit.

For each pair:

1. Run the baseline task and retain its exact trace and independent result check.
2. Record its task evaluation. For measurement-only collection, do **not** also
   send a usefulness-learning rating just because the evaluation has a usefulness
   field.
3. Apply only the intended reviewed change. The UI does not create or enforce a
   no-compounding baseline; document how you kept the conditions distinct.
4. Run the adapted task as a separate response and record it under the same
   comparison key with its own trace and evidence.
5. Repeat with new keys and genuinely held-out tasks. Keep failures, regressions,
   unavailable capabilities, and UNKNOWN outcomes rather than cherry-picking.

One pair or a small deterministic fixture does not demonstrate robust transfer.
There is no automatic maturity upgrade or numerical sample threshold here that
certifies Phase 1.4 complete.

## 5. Inspect the collected evidence

The existing authenticated API surfaces remain authoritative:

| Endpoint | What it reports |
|---|---|
| `GET /cognition/traces/{trace_id}/usefulness` | Explicit response usefulness events |
| `GET /benchmarks/phase1/tasks/evaluations?trace_id={trace_id}&split=held_out` | Held-out assessments for one exact response |
| `GET /benchmarks/phase1/tasks/evaluations?trace_id={trace_id}&split=contract` | Routine/contract assessments for that response |
| `GET /benchmarks/phase1/tasks/evaluations?split=held_out` | Aggregate held-out outcome/usefulness counts and descriptive paired comparisons |
| `GET /benchmarks/phase1/evidence` | Recorded trace grounding, outcomes, route corrections, and learning-feedback volume |
| `GET /cognition/corrections/measurements` | Existing correction receipt/latency and strategy-link telemetry |

Task-evaluation usefulness and response-feedback usefulness are intentionally
separate metrics. A task-only assessment does not increase the trace feedback
count. Missing ratings stay unmeasured; unsupported-claim entries are not
necessarily independently demonstrated hallucinations.

Both submission endpoints accept optional `submission_id` (8–128 ASCII letters,
numbers, hyphens, or underscores). The web sends one ID per attempted payload.
An exact retry returns the original receipt; changing the content or trace under
that ID is rejected. Detection and insertion share a SQLite transaction, so
concurrent retries cannot inflate counts. Integrations omitting the optional ID
retain the legacy append-per-request behavior. A lost response is not proof that
a write was undone: retry with the same ID/payload or inspect the recorded history.

## 6. Verification boundaries

Automated coverage includes legacy database migration, restart-safe message/trace
binding, failed-cycle cache clearing, exact-trace history filtering, concurrent
submission retries, truth-field preservation, metadata/token/history races,
owner-only form submission, UNKNOWN defaults, and visible load/save failures.

Web controls are implemented in this slice. Native desktop and Android retain
protocol compatibility but do not yet expose these response-review controls.
Trace-linked correction submission is still available through the existing API;
a new inline correction editor is not part of this slice.

Unit/integration fixtures are **contract evidence**, not owner held-out results.
Real LM Studio outcomes, usefulness volume, cross-task improvement, and supported
host/device behavior must still be measured on the owner installation.

### Current software-only validation (2026-09-07)

- Backend: **3,133 passed, 14 skipped, 4 e2e deselected**, 3 environment/dependency warnings.
- Frontend: **246 passed**; production build passed; lint **0 errors**, 18 existing warnings.
- Inherited CI opener test is now deterministic on Linux/macOS/Windows branches
  using mocks (not real application launches). The GitHub backend checks passed.
  `scripts/ci/frontend.yml` contains the updated Node 22 test/build/lint template,
  but it is **not active**: GitHub rejected an active-workflow update because the
  Arena GitHub App connection lacks workflow-edit permission. Update/reconnect
  that integration with the required permission before installing the template
  in `.github/workflows/`. No credentials should be shared in chat.
- No runtime dependencies were added. The only database schema migration is the
  additive message/trace identity columns and index in the existing conversations
  table. Feedback and evaluation retry receipts reuse their existing tables.
