# Arena Agent — Measured Status

**Updated:** 2026-08-21 · Branch `arena/01a01f89-arena-agent`
**This is the canonical status document.** It supersedes the percentage-based status
files that previously lived at the repo root (`AGI_STATUS.md`, `AGI_LEVEL_ASSESSMENT.md`,
`AGI_FINAL_SUMMARY.md`, `PHASES.md`, `PROJECT_REVIEW.md`, and the recovered branch's
`HUMAN_LEVEL_AGI_ACHIEVED.md` / `FINAL_AGI_STATUS.md`). Those used invented "% AGI"
and test-count figures that did not match the code; they are now archived under
`docs/archive/`. This document is measured.

---

## What this system is

A **local-first, full-capability coworker / friend** with a closed-loop cognitive architecture. Owner-defined approval gates, not a restricted demo: nothing is off-limits, but sensitive/irreversible actions require explicit owner approval (Level 3).

**Hardware:** Intel Core i9-14900K · RX 580 8 GB (CPU inference) · 16 GB DDR5 · LM Studio · Qwen 3B fast + 9B reasoning.

---

## Measured facts (verified, not claimed)

| Metric | Value | How it was measured |
|---|---|---|
| Backend tests passing | **1414** (+4 deselected e2e) | `python -m pytest tests/ -q` → `1414 passed, 4 deselected` |
| Frontend tests passing | **184** | `cd frontend && npm test -- --run` → `184 passed` |
| Frontend build | ✅ | `npm run build` (tsc + vite) succeeds |
| Python source | ~45,000 lines / 209 files | `find app backend -name '*.py' -exec cat {} + | wc -l` |
| Tools in the manifest | **121** | `len(get_tool_manifest())` (incl. 3 deterministic recipes) |
| Live verification of external APIs | script | `scripts/live_check.py` + `LIVE_VERIFICATION.md` |
| Deterministic Tier-1 tools | ✅ all present | `runtime.measure_capabilities()` → `tier1_tool_manifest = verified` |
| Deterministic degradation | ✅ | `runtime.measure_capabilities()` → `deterministic_degradation = verified` |
| Cognition modules wired into the cycle | **15/15** | `runtime.measure_capabilities()` → `module_wiring = verified` |
| Capability scorecard | **21/21 verified** across 7 evidence categories | `runtime.measure_capabilities()` → `verified_count == total_count`, per-category summary |
| Chat path uses cognitive runtime | ✅ | `tests/test_message_router_cognitive.py` (regression guard) |
| Chat history persists across restart | ✅ | `tests/test_conversation_persistence.py` (SQLite-backed) |
| Conversation list syncs FE↔BE | ✅ | `db.get_conversation_previews()` + `useConversationSync` hook + store tests |
| Hardware self-awareness | ✅ | `tests/test_hardware_self_awareness.py` |
| Thread-safe singleton | ✅ | `tests/test_phase14_22_wiring.py::test_get_instance_is_thread_safe` |
| Memory consolidation | ✅ | `tests/test_phase4_autonomy.py` |
| Verification honesty (UNKNOWN stays UNKNOWN) | ✅ | `runtime.measure_capabilities()` → `verification_honesty = verified` |
| Autonomous cycle scheduled (hourly) | ✅ | `tests/test_scheduler_wiring.py` |
| Approval gate (Level 3 → approval) | ✅ | `tests/test_policy.py`, `tests/test_phase4_autonomy.py` |

---

## The cognitive loop (what actually runs)

```
User / WebSocket chat
  → CognitiveRuntime.process_cognitive_cycle()
      → semantic goal interpretation
      → world model + belief ingestion
      → reasoning loop (ANSWER / INVESTIGATE / DEFER / ACT)
      → counterfactual strategy simulation
      → action gate (policy: Level 0–3)
      → capability execution
      → observation → tri-state verification (SATISFIED / FAILED / UNKNOWN)
      → replan on failure
      → reflection + memory learning
      → _integrate_phase_modules(): 15 modules contribute/learn
  → (hourly) autonomous cycle: observe → generate goals → execute → reflect
      → memory consolidation (decay + prune + integrate)
      → proactive coworker maintenance (idle self-heal)
```

The 15 wired modules: common-sense KB, autonomous goal generation/execution, self-reflection, metacognitive monitor, causal inference, strategic planning, cross-domain transfer, creative generation, social cognition, consciousness simulation, embodied cognition, cultural learning, advanced cognition (Phase 14), language grounding (Phase 22).

---

## The capability scorecard (what "done" means here)

Run `runtime.measure_capabilities()`. Each entry is **probed at runtime**, not copied from a doc:

- **tri_state_verification** — no fabricated success; UNKNOWN stays UNKNOWN
- **verification_honesty** — a no-evidence environmental condition resolves to UNKNOWN (behavioral probe)
- **belief_evidence_discipline** — probe evidence → belief; self-reported claim → hypothesis only
- **memory_retrieval** — semantic memory add + search round-trip
- **causal_reasoning** — causal edge → root_cause_analysis recovers it
- **goal_verification_behavioral** — a delivered reply resolves SATISFIED
- **approval_gate** — Level 3 actions require owner approval
- **module_wiring** — all 15 modules instantiated (no orphans)
- **hardware_self_awareness** — self-model of CPU/RAM/GPU present
- **memory_consolidation** — decay + prune + episodic integration
- **autonomy_loop** — generate → execute → reflect wired
- **tools_wired** — 118 tools registered in the capability registry (from the manifest)
- **tier1_tool_manifest** — all expected deterministic tools present (data, PDF, process, backup, finance, network, messaging, agents)
- **deterministic_degradation** — invalid inputs to deterministic tools return typed `{success: False}` results, never raise
- **persistence_roundtrip** — a structured lesson survives a SQLite save/reload (robustness)
- **capability_generalization** — the capability matcher behaves correctly on unseen/adversarial inputs (no "port"→"teleportation" false positive)
- **learning_changes_behavior** — repeated failures lower an action's future utility weight (longitudinal calibration)

Each check is tagged with one of seven evidence categories — structural / integration / behavioral / robustness / transfer / generalization / longitudinal — and the report returns a per-category summary so "the module exists" is never conflated with "it performs, transfers, or improves."

---

## What this is NOT (honest boundaries)

- **Not "human-level AGI."** No system is. The phrase in earlier docs was a label, not an engineering result.
- **Not conscious.** `consciousness_simulation` is a functional self-model, not phenomenal awareness.
- **Not "100% complete."** Progress is measured in the scorecard above, which will grow as capabilities are wired and tested.

The highest-value remaining work is **more integration and measurement**, not more self-contained modules. Closed this round:

- ✅ Conversation history persists to SQLite (`conversations` table + router wiring).
- ✅ Autonomous cycle scheduled hourly via `ProactiveScheduler` in the backend lifespan.
- ✅ End-to-end chat → runtime test.
- ✅ Behavioral scorecard checks (verification honesty, belief discipline, memory retrieval, causal reasoning, goal verification).
- ✅ FE↔BE conversation sync: backend lists SQLite-persisted conversations; frontend hydrates via `useConversationSync` + store actions (`hydrateFromServer`, `hydrateMessages`) and requests history on open.
- ✅ **Tier-1 tool expansion complete** (see `TOOL_EXPANSION_PLAN.md`): the two levers (local executor + plugin registry) plus 14 hand-built deterministic tools — contacts, spreadsheet, PDF toolkit, process manager, database connector (read + gated write), invoice generator, network diagnostics, budget tracker, backup & restore, presentation generator, package installer, RSS aggregator, fact-check, price lookup, messaging. Tool count grew 67 → 118.
- ✅ **Agent invariants codified** (`AGENT_INVARIANTS.md`): one brain, thin agents, one loaded model, strong-tools-thin-model, deterministic verification.
- ✅ **Two thin agents** (`app/agents/`): coding agent + data-analysis agent (read-only), both sharing the ONE `CognitiveRuntime` + `llm_client`.
- ✅ **Capability matcher fixed** to match on token boundaries (no more "port"→"teleportation" bare-substring false positives).
- ✅ **Autonomous execution integrity (P0)**: the goal executor now consumes the cycle's `goal_verified` verdict — steps are `COMPLETED` only when the environment was verified, `FAILED` on definitive failure, `UNVERIFIED` when there's no evidence, and `WAITING_APPROVAL` when a Level-3 action is gated. A plan is `COMPLETED` only when every step is verified.
- ✅ **Goal-approval ≠ action-approval (P0)**: documented + enforced — auto-approving a goal never authorizes its actions; every action still passes `ActionGate`, and gated actions are recorded as `WAITING_APPROVAL`, never completed.
- ✅ **Server hardened (P0)**: the 127-route core router is now gated by the same `verify_api_key` as the `/api/*` routers (so a set `ARENA_API_KEY` protects everything, not just newer routes); unauthenticated instances reject non-loopback clients by default (localhost-only), with `ARENA_ALLOW_INSECURE_LAN=1` as an explicit opt-out and `ARENA_ENFORCE_AUTH=1` as fail-closed mode.
- ✅ **Provenance persistence (P1)**: `observation_type` now survives the SQLite save/load round-trip; first belief insertion goes through the same `revise()` path as subsequent observations (one- and two-observation semantics are identical).
- ✅ **Goal-approval boundary (P0)**: a `GoalApproval` record now makes explicit that approving a goal authorizes *planning only* — `max_action_level` (default 2) caps auto-executable safety, and Level-3 actions always require owner approval at execution time. Persisted per goal.
- ✅ **Measurement isolation (P1)**: `measure_capabilities()` runs its behavioral probes against throwaway stores in a temp dir (beliefs/memory/causal/cross-domain/patterns) and discards them — measurement no longer teaches/mutates the system it measures. The proactive-maintenance probe was made structural (it writes to RAG memory).
- ✅ **Plan dependencies (P1)**: `execute_plan` now halts after an `UNVERIFIED` or `WAITING_APPROVAL` step instead of blindly continuing — later steps that depend on an unverified precondition are not executed.
- ✅ **Resumable approval (P1)**: `WAITING_APPROVAL` plans map the goal to a distinct `WAITING_APPROVAL` state (not `DEFERRED`), and `resume_plan()` re-attempts the gated step once the owner approves.
- ✅ **Explicit autonomy mode**: `AUTONOMY_MODE` (default `supervised`) governs whether the hourly autonomous cycle is scheduled; `off` disables it.
- ✅ **Explicit step dependencies (P1)**: `ExecutionStep` now declares `depends_on` / `requires_evidence` / `produces_evidence` / `success_criteria` / `failure_conditions`; generated plans are linked into an explicit chain, and `execute_plan` blocks any step whose declared prerequisite isn't `COMPLETED`.
- ✅ **Split UNVERIFIED vs WAITING_APPROVAL recovery (P1)**: `resume_plan` re-attempts only owner-approved (WAITING_APPROVAL) steps; `reconcile_plan` re-runs UNVERIFIED steps in verify-only (observe, don't re-execute) mode — no blind re-execution of unconfirmed actions.
- ✅ **Lessons now influence replanning (closed the learning loop)**: `GoalReplanner.execute_reassessment_and_replan` forwards `lesson_store` into `ActionPlanner` → `CounterfactualSimulator`, so a recorded past failure lowers the utility of that same action in future Plan-B selection (previously lessons were written but never read back).
- ✅ **Evidence-driven goal generation**: `generate_goals_from_signals` produces goals from structured signals (resource pressure, stale beliefs, failed actions, prediction error, low success rate) with threshold gates — not string keyword matching. Wired into the autonomous cycle ahead of the keyword fallback.
- ✅ **Outcome-calibrated goal scoring**: `evaluate_goal` blends each goal source's historical success rate into feasibility once ≥3 outcomes exist, closing "predicted value → actual utility → prediction error → calibration → better future decisions."
- ✅ **StepVerifier separates step from goal verification (P0)**: a new `StepVerifier` evaluates each step's OWN success/failure criteria and evidence contract; a step declaring evidence is `UNVERIFIED` (not `COMPLETED`) when the cycle only produced a conversational ANSWER. Confidence is now evidence-derived (0.9 observed / 0.7 conversational / 0.5 unverified / 0.0 failed), never a hard-coded 1.0 on success.
- ✅ **Evidence as real data-flow**: generated plans populate `requires_evidence`/`produces_evidence` (current_state → root_cause → optimization_plan → change_applied → …), and `execute_plan` blocks any step whose required evidence was never produced by a COMPLETED step — not just its `depends_on` order.

Still open (future):

1. Complete the Android Gradle wrapper (`gradlew` script + `gradle-wrapper.jar` binary — needs the Gradle distribution).
2. Deliver the held `.github/workflows/{tests,android}.yml` files — blocked on the GitHub App's `workflows` permission.
3. Continue extending the scorecard with behavioral (not just presence) checks across more domains.
4. Full end-to-end browser test of the conversation round-trip (backend list → frontend hydrate → history on open) against a live server.
5. Exercise the external-API tools (CoinGecko/Stooq/Telegram/Twilio/search) against live endpoints on the owner's machine — sandbox network is restricted, so those paths are verified for parsing/validation/degradation only.
