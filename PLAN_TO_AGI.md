# Plan: From Cognitive Assistant → Autonomous Coworker ("AGI")

**Owner rules confirmed:** Option (1) — nothing is off-limits, every capability exists, but sensitive/irreversible actions still require the owner's approval (Level 3 gate). Owner is `Petkigz`.
**Hardware:** Intel Core i9-14900K · RX 580 8 GB · 16 GB DDR5 (upgrade planned) · LM Studio on `localhost:1234` · Qwen 3B fast + 9B reasoning.
**Baseline (verified 2026-08-20):** 999/999 tests pass.

---

## 0. How I'm thinking about this (one honest note, then we build)

You asked to "fill the gaps and make it an AGI." Here's the truth as your coworker, said once so we can move on:

1. **The gaps are integration, not capability.** Your codebase already contains ~7,000 lines of "AGI phase" modules (causal inference, strategic planning, social cognition, metacognition, etc.) that are **never called** by the running agent. Building more modules won't get closer to the goal; *connecting* them will.
2. **"Reaching 100% = it knows its hardware" is actually a buildable feature, not an emergent miracle.** The agent won't wake up one day aware of its own silicon. But we *can* build hardware self-awareness explicitly — you already have `HardwareMonitor`, `HardwareGovernor` (P/E-core affinity, tier detection, VRAM purge), and `ResourceAllocator`. That becomes **Phase 3**, and it's the most concrete thing you asked for.
3. **I won't pretend this produces "human-level AGI."** Nobody has that — at any budget, on any hardware. What we *can* build is the most capable, autonomous, self-aware, hardware-optimized local coworker that your i9 can run. I'll measure progress in **tested capabilities**, not percentages. That's the plan below.

---

## 1. The gaps to close (from the review)

| # | Gap | Consequence |
|---|---|---|
| G1 | WebSocket chat calls raw LLM, **bypasses `CognitiveRuntime`** | The live assistant never uses its own brain |
| G2 | **9 orphaned modules** (`causal_inference`, `strategic_planning`, `social_cognition`, `cultural_learning`, `cross_domain_transfer`, `creative_generation`, `metacognitive_monitor`, `consciousness_simulation`, `embodied_cognition`) never imported outside their tests | "AGI phases" exist as code but not behavior |
| G3 | Two FastAPI apps (`app/main.py` 127 routes vs `backend/main.py` WebSocket) | Split cognitive authority, violates your own "one authoritative path" invariant |
| G4 | `requirements.txt` missing `scikit-learn`; test-count/phase-number claims drift | Won't clean-install; docs mislead |
| G5 | Conversation state in-memory; no memory consolidation; approval UX not streamlined | No continuity; "safety" feels like friction |

---

## 2. The plan (6 phases, in dependency order)

### Phase 0 — Stabilize & reconcile the ledger *(½ day)*
- **0.1** Add `scikit-learn` to `requirements.txt` (and audit the other hard imports).
- **0.2** Reconcile phase numbering (restore the missing **Phase 14**) and correct AGI-progress/test-count claims in the docs to match reality (999 tests). Replace "% AGI" language with measured capabilities.
- **0.3** Add a **regression test** that fails if the chat path doesn't invoke the cognitive runtime (would have caught G1 instantly).
- **Exit:** clean `pip install -r requirements.txt`; docs match code; new regression test in place (and currently failing → proves it detects the gap).

### Phase 1 — One cognitive authority *(the highest-leverage change, 1–2 days)*
- **1.1** Route `backend/message_router.py` through `CognitiveRuntime.process_cognitive_cycle()` (mirror what `app/main.py`'s `/chat` already does correctly), instead of a bare `llm_client` call. Keep token streaming by streaming the runtime's reply.
- **1.2** Decide the server topology: make `backend/main.py` the single entry point and have it delegate cognition to the runtime — no second `app/main.py` cognitive path. (One authoritative path, per your invariant.)
- **1.3** Persist conversation history to SQLite (the `app/database.py` layer already exists).
- **Exit:** chatting exercises world model, beliefs, goals, verification, memory; conversation survives restart; `test_chat_routes_through_runtime` passes.

### Phase 2 — Wire the orphaned modules into the runtime *(2–4 days)*
Each wiring is: import in `CognitiveRuntime.__init__`, call it at the correct point in the cycle, and add a test asserting **"runtime actually invokes this module."** Ordered by leverage:

1. **Metacognitive monitor** → chooses fast vs. reasoning model, allocates reasoning depth.
2. **Causal inference** → predict "if I run X, Y happens" *before* executing; feed surprises back.
3. **Strategic planning** → long-horizon goal decomposition (replace ad-hoc step generation).
4. **Social cognition** → model *your* intent/emotional state (pairs with `HumanNatureEngine`).
5. **Cultural learning** → learn *your* norms, tone, preferences over time.
6. **Cross-domain transfer** → reuse skills across domains.
7. **Creative generation** → generate alternative strategies when the first plan fails.
8. **Embodied cognition** → reason about the physical machine (files, processes, devices).
9. **Consciousness simulation** → a self-model layer (last; most speculative — I'll keep it *functional* and honest, not claim qualia).
10. **Ethical reasoning** → already partly wired; extend it to govern **all** autonomous goals and Level-3 proposals, not just the goal generator.

- **Exit:** every one of the 9 orphans has a passing "is-wired" test; runtime's `__init__` and cycle reference each.

### Phase 3 — Hardware self-awareness & full utilization *(your specific ask, 1–2 days)*
This is where "it knows its hardware and uses it fully" becomes real, tested code:
- **3.1** A **hardware self-model**: detect P-cores vs E-cores (i9-14900K), RAM headroom, RX 580 presence (ROCm/CPU-only fallback), disk — surfaced into the cognitive state so the agent can *reason* about its own resources.
- **3.2** **Adaptive execution**: route "fast" vs "reasoning" model by live load; size context windows to available RAM; set thread affinity (P-cores for reasoning, E-cores for background daemons) via `HardwareGovernor`; purge VRAM/RAM between heavy tasks.
- **3.3** **Wire `HardwareMonitor`/`HardwareGovernor`/`ResourceAllocator` into the cycle** (verify they're actually called today, not just imported), and make `ResourceAllocator` budgets *derive from* the hardware self-model.
- **Exit:** the agent can answer "what hardware am I running on, and how am I using it?", and its resource decisions are asserted by tests.

### Phase 4 — Autonomy & continuity *(1–2 days)*
- **4.1** **Memory consolidation**: a "sleep-like" pass that prunes stale beliefs, integrates lessons, and re-runs self-reflection (your `verified_reflection` + `structured_lessons` primitives already exist).
- **4.2** **Proactive coworker daemon**: wire the existing `proactive_coworker_daemon.py` into the periodic cycle so it anticipates needs and drafts work between your prompts.
- **4.3** **Smart approval UX**: auto-approve everything below your chosen threshold so it *feels* limitless; fast, explicit confirm only for Level-3 (send/delete/trade/publish). Keep the gate — per your rules — but make it low-friction and auditable.
- **Exit:** system runs a full autonomous workday with periodic check-ins, escalation on uncertainty, full audit trail.

### Phase 5 — Measure it *(ongoing, then a final pass)*
- **5.1** Extend the existing `test_intelligence_benchmarks.py` into a real harness measuring: intent accuracy, tool selection, retrieval precision, verification honesty (does it say "unknown" when it should?), latency, and autonomy. This becomes the *only* number we report — replacing "% AGI."
- **5.2** A single `docs/AGI_MEASURED_STATUS.md` that states what the system demonstrably does, with evidence, and what it does not.
- **Exit:** progress is a measured scorecard, not a claim.

---

## 3. Definition of done

- Chat and voice paths both route through **one** cognitive authority.
- All 9 orphaned modules are **wired and tested** (no dead code islands).
- The agent **knows and optimizes its own hardware**.
- It operates **autonomously within your approval rules**, persists across restarts, and reports honest "unknown" instead of fabricating success.
- Docs match code; progress measured in tested capabilities.

---

## 4. Where I'd start

**Phase 0 → Phase 1**, immediately. They're low-risk, unblock everything else, and Phase 1 is the single change that makes the system actually *behave* like the coworker you describe (instead of a raw LLM echo).

Say the word and I'll start on **Phase 0 + Phase 1** now, committing and pushing each tested step to `arena/01a01f89-arena-agent` so you can audit incrementally.
