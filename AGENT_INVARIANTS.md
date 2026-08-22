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

## 6. Typed, honest, degradable responses

- Every tool/agent returns a `{"success": bool, ...}` dict, not exceptions and not
  bare strings.
- Validate inputs first; fail fast with a clear error.
- Degrade gracefully: offline LLM → simulated/empty reply handled; missing file →
  clean error; git unavailable → continue best-effort.

## 7. Permissions are capability-aware, not "no gates"

Nothing is off-limits, but **sensitive/irreversible actions require explicit
owner approval** (Level 3). The tool manifest's `safety_level` is authoritative:

- `0` read / `1` draft / `2` reversible → auto-allowed.
- `≥ 3` sensitive/irreversible → approval required (owner decides via the
  `action_approval` WebSocket message).

## 8. Honesty over AGI theater

- Never claim "human-level AGI", "conscious", or "zero bugs". None of those are
  true today.
- Measure progress in **tested capabilities** (`measure_capabilities()`
  scorecard), never percentages.
- Flag what cannot be verified in-sandbox (real GPU, real LLM, Android compile,
  GUI launch) instead of implying it works.

## 9. Consideration is not authority

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

---

*Where this is enforced:* `app/agents/*` (loops), `app/cognition/runtime.py`
(one brain), `app/llm.py` (single `llm_client` + `extract_reply`),
`app/tools/manifest.py` (authoritative safety levels), `app/cognition/action_proposal.py`
(Level-3 gate), `app/cognition/approval_store.py` (owner approval).
