# Arena Agent Invariants

The non-negotiable design rules every agent, tool, and future change must obey.
These are not aspirations — they are the contract that keeps the system honest on
weak local hardware (Qwen 3B/9B, CPU inference). If a change violates one, the
change is wrong until it's fixed.

---

## 1. One brain, always

There is exactly **one** `CognitiveRuntime` in the process (`get_instance()`
returns the server's singleton). Agents and tools never construct a second
runtime, never keep their own memory store, and never run a private cognition
stack.

- Agents call `CognitiveRuntime.get_instance()` to *record* into the brain
  (`memory` / `outcomes` / `lessons`), never to replace it.
- Recording is always **best-effort**: a failed record never fails the task.

## 2. Thin agents, not mini cognitive systems

An "agent" is a **loop**, not a brain:

```
plan (small LLM step) → act via deterministic tools → verify by running things → repeat → report
```

- An agent may add a *task-specific loop* (e.g. write-code-then-test, or
  query-data-then-read-rows). It may **not** add beliefs, attention, planning
  patterns, goals, or any cognition the runtime already owns.
- If you find yourself adding a "reasoning step" to an agent, stop — that belongs
  in deterministic code or the shared runtime.

## 3. One loaded model, no per-instruction swapping

- LM Studio runs with **Max Loaded Models = 1**. Only `FAST_MODEL`
  (`qwen2.5-3b-instruct`) or `MAIN_MODEL` (`qwen2.5-9b-instruct`) is loaded at a
  time; the `fast`/`main` route is chosen by the runtime's **hardware-aware**
  selection, not by the instruction.
- **Never** hot-swap models per request. On CPU-only hardware the load cost
  dominates any quality gain from a slightly bigger small model. The model router
  is intentionally left alone.

## 4. Strong tools, thin model

Reasoning lives in **deterministic code**, not prompts. The model only
orchestrates, picks tools, and relays results.

- Computation (stats, SQL, file I/O, scheduling, image/audio handling) is done by
  code. Correctness is checked by **running** the code/query/tests — never by
  asking the model whether its output is right.
- The model is shown **exact results already computed** and told to repeat only
  those numbers. Never let the model invent figures, percentages, or trends.

## 5. Deterministic verification

Every non-trivial agent step is verified by an executor, not by the model:

- Coding: run the test command in `DisposableSandbox`.
- Data analysis: run read-only SQL via `SQLQueryTool` / pandas and inspect real rows.
- Anything else: add a real checker before trusting the output.

## 6. Evidence-linked memory consolidation

Temporal visual tracking is stream-isolated and may claim only detector-backed
continuity (appeared/moved/disappeared). It must not infer identity, depth,
intent, or emotion from bounding-box association alone.

Automatic consolidation may promote only verifier-authored terminal episodes.
Every semantic/procedural/lesson target keeps source-memory links; UNKNOWN,
self-reported, and conversational claims are not promoted as facts. Repeated
maintenance must be idempotent and must never teach the system from its own
measurement probes. Longitudinal benchmarks run only against throwaway stores,
persist evidence and metrics separately, and report pass counts/regressions—not
an invented intelligence or AGI percentage.

Verified success may propose a LoRA example, but never approve or train it.
Training candidates are redacted, deduplicated, owner-editable, and excluded
until explicitly approved. Dataset export includes a held-out evaluation split;
adapter selection is not claimed to affect behavior until the inference provider
actually loads it and before/after evaluation demonstrates improvement.

## 7. Typed, honest, degradable responses

- Every tool/agent returns a `{"success": bool, ...}` dict, not exceptions and not
  bare strings.
- Validate inputs first; fail fast with a clear error.
- Degrade gracefully: offline LLM → simulated/empty reply handled; missing file →
  clean error; git unavailable → continue best-effort.

## 8. Permissions are owner-controlled and capability-aware

Nothing is off-limits for consideration, but execution authority belongs to the
owner. The tool manifest's `safety_level` is authoritative, while the persistent
Owner Control Plane may always impose a stricter rule:

- Default bounded autonomy: `0` read / `1` draft / `2` reversible are delegated;
  `≥ 3` sensitive/irreversible requires explicit approval.
- The owner may switch to observe-only, suggest-only, approve-every-action,
  approve-each-plan, bounded-autonomy, or a custom action allowlist.
- Per-action approval and block lists override the default delegation.
- Emergency pause blocks all capability execution before resource or prediction
  work. A malformed control policy fails closed in paused mode.
- Cancellation is cooperative and must report whether a checkpoint observed it;
  never claim a late cancellation undid prior side effects. Rollback exists only
  with a deterministic compensation receipt and always requires fresh approval.
- Curiosity thresholds may adapt only from verified outcomes, within conservative
  clamps. The owner's exploration maximum is absolute and may be set to zero.
- Autonomous resource limits are optional and disabled by default. When the owner
  enables them, every cycle obeys the configured duration, cooldown, execution,
  project, and failure budgets; a zero budget stays zero.
- The owner may mint an explicit exact-payload `override_owner_policy` grant to
  override their own block/mode/level policy. It remains short-lived and single-use,
  cannot bypass emergency pause, resource-critical shutdown, unavailable capability,
  payload binding, or evidence/verification honesty.
- Autonomous goals remain an owner-visible queue. The owner can approve planning,
  reject, reprioritize, or request the next goal; goal approval never authorizes its actions.
- Every autonomous cycle persists stage events for observation, consideration,
  recommendation, planning approval, execution, blocking, budget stops, and outcome.
- Owner schedules are timezone-aware and persistent. Recurrence and missed-run
  policy release owner-directive goals; schedule approval still authorizes planning only.
- Explicit approval mints only a short-lived, revocable grant bound to the exact
  action type and canonical payload digest. It is single-use by default; changed
  parameters, replay, expiry, restart, or revocation invalidate it.
- Authorized execution must return through the same capability → independent
  observation → tri-state verification → outcome/lesson/causal-learning loop.
  Tool success is never reported as goal verification, and retries or Plan B
  require a fresh recommendation and authorization.
- In approve-each-plan mode, the complete step graph—including exact action type
  and payload—is revisioned and owner-editable. No step runs before approval of
  that exact revision; edits invalidate approval, and plan approval never covers
  Level-3 or per-action-gated operations.
- Persistent project DAG execution is explicit owner opt-in, bounded per cycle,
  dependency-aware, and restart-safe. UNKNOWN triggers later observation-only
  reconciliation—not re-execution; sensitive steps wait for exact single-use
  authorization.

## 9. Honesty over AGI theater

- Never claim "human-level AGI", "conscious", or "zero bugs". None of those are
  true today.
- Measure progress in **tested capabilities** (`measure_capabilities()`
  scorecard), never percentages.
- Flag what cannot be verified in-sandbox (real GPU, real LLM, Android compile,
  GUI launch) instead of implying it works.
- Unimplemented or unavailable execution/model/training/identification features
  return typed `success: false` / unavailable responses. Never create placeholder
  artifacts, windows, navigation, speech, device connections, or identities; never
  invent accuracy/confidence. Hypothetical simulations are labeled predicted and
  cannot update verified success history.

## 10. Consideration is not authority

The agent may consider uncomfortable, sensitive, or policy-restricted
alternatives in its private counterfactual analysis. It should explain why an
alternative might be useful and rank its expected benefit, risk, uncertainty,
and other consequences instead of hiding it merely because execution is gated.

Four stages remain structurally separate:

1. **Consideration** — compare possible approaches, including restricted ones.
2. **Recommendation** — select and explain a preferred approach; this grants no authority.
3. **Authorization** — owner policy or explicit owner approval permits an exact, scoped action.
4. **Execution** — only the authorized action and payload may touch the environment.

A recommendation is never approval. Mentioning, ranking, simulating, planning,
or explaining a restricted action is never permission to execute it. The
`ActionGate` applies after recommendation and before capability execution; a
restricted alternative remains visible in the decision record even when it is
not authorized.

## 11. Self-knowledge is evidence, not model narration

- Every factual self-claim has a source type, evidence references, confidence,
  timestamp, freshness/expiry, and revision history.
- Free-form model statements such as “I can,” “I remember,” or “I caused” are not
  privileged introspection and cannot create self-knowledge by themselves.
- Changed self-beliefs supersede rather than erase earlier claims. A structured
  revision records old/new values, evidence, confidence delta, and why the belief
  changed.
- Competence claims derive from prediction/outcome calibration. Sample-poor
  estimates remain explicitly insufficient and cannot become confident ability
  claims.
- Temporal proximity never proves agency. Arena may mark a change `self_caused`
  only when a controlled execution is followed by environmental observation and
  goal-verifying evidence; otherwise causation remains unknown.
- Owner-caused and identified external changes remain distinct from self-caused
  changes.
- Commitments originate only from explicit owner entries, exact authorized
  actions, approved plans, or persistent projects. Model prose cannot create a
  promise. Completion requires verification evidence; blocked work keeps its
  reason across restart.
- Introspection summaries quote persisted trace facts, actions, gates, evidence,
  and lessons. They never claim access to private chain-of-thought.
- Sensor and actuator interfaces are modeled as Arena interfaces, owner devices,
  shared surfaces, external environment, or unknown. Sending a command does not
  prove control; an Arena-controlled event requires authority plus observed effect.
- Restart continuity compares claim predicates, commitments, interfaces, capability count, and owner-policy revision. Missing state is flagged, never silently rationalized.
- Recovery assessments persist for owner review. They are advisory only; requesting a recovery action creates an exact pending approval and never executes it.
- Functional self-knowledge never implies consciousness, sentience, emotion, a
  biological body, persistent subjective identity, or subjective experience. The absence of measurement remains explicit.

---

*Where this is enforced:* `app/agents/*` (loops), `app/cognition/runtime.py`
(one brain), `app/llm.py` (single `llm_client` + `extract_reply`),
`app/tools/manifest.py` (authoritative safety levels), `app/cognition/action_proposal.py`
(Level-3 gate), `app/cognition/approval_store.py` (owner approval).
