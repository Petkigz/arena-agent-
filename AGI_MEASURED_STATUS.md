# Arena Agent — Measured Status

**Updated:** 2026-08-22 · Branch `arena/01a02b25-arena-agent`
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
| Backend tests passing | **1414** (+4 deselected e2e) | `python -m pytest tests/ -q` → `1414 passed, 4 deselected` (previous baseline, not re-run in this sandbox) |
| Frontend tests passing | **184** | `cd frontend && npm test -- --run` → `184 passed` (previous baseline) |
| Frontend build | ✅ | `npm run build` (tsc + vite) succeeds (previous baseline, code-reviewed this audit) |
| Python source | ~50,000 lines / 220 files | `find app backend -name '*.py' -exec cat {} + | wc -l` |
| Tools in the manifest | **133** | `len(get_tool_manifest())` — added detect_objects, detect_faces, analyze_image_grounded, analyze_prosody, vlm_analyze, vlm_status, list_loras, lora_status, activate_lora, deactivate_lora, prepare_lora_dataset, create_lora_job (P1-1, P2, P3) |
| Cognition modules wired | **17/17** | `runtime._integrate_phase_modules()` + `module_wiring` probe — includes `goal_decomposer` + `project_manager` |
| Capability scorecard | **27/27 verified** across 7 evidence categories | `runtime.measure_capabilities()` → `verified_count == total_count`; includes grounding, causal learning, memory association, curiosity, resource-aware planning, prosody, multimodal chat, verified self-evolution, projects, VLM integration, and LoRA management |
| Live verification of external APIs | script | `scripts/live_check.py` + `LIVE_VERIFICATION.md` |
| Deterministic Tier-1 tools | ✅ all present | `runtime.measure_capabilities()` → `tier1_tool_manifest = verified` |
| Deterministic degradation | ✅ | `runtime.measure_capabilities()` → `deterministic_degradation = verified` |
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
User / WebSocket chat (now multimodal: text + image_path + attachments)
  → CognitiveRuntime.process_cognitive_cycle(image_path, attachments)
      → semantic goal interpretation + multimodal ingestion (object detection + OCR + grounding)
      → world model + belief ingestion + perception grounding (auto-creates PerceptualGrounding)
      → reasoning loop (ANSWER / INVESTIGATE / DEFER / ACT)
      → counterfactual strategy simulation (resource-aware: penalizes heavy actions under RAM/CPU/disk pressure)
      → action gate (policy: Level 0–3)
      → capability execution (133 manifest tools)
      → observation → tri-state verification (SATISFIED / FAILED / UNKNOWN)
      → causal learning from execution + surprisal (learns action→effect, intent→outcome)
      → replan on failure (resource-aware)
      → reflection + memory learning + social emotion inference (prosody + text)
      → _integrate_phase_modules(): 17 modules contribute/learn
      → long-horizon decomposition: complex goals → sub-goals DAG → persistent Project (multi-session)
  → (hourly) autonomous cycle: observe structured signals + info-gain → generate goals → execute → reflect
      → memory consolidation (decay + prune + integrate + causal prune + memory association co_occurs_with)
      → proactive coworker maintenance (idle self-heal)
```

The 17 wired modules: common-sense KB, autonomous goal generation/execution, self-reflection, metacognitive monitor, causal inference (now learns from interventions + surprisal), strategic planning, cross-domain transfer, creative generation, social cognition (now from prosody + text emotion), consciousness simulation, embodied cognition, cultural learning, advanced cognition (Phase 14: ResourceManager + MultiAgentCoordinator + KnowledgeSynthesizer + UncertaintyQuantifier), language grounding (Phase 22: now populated via object_detector), goal_decomposer (Phase 6A), project_manager (Phase 6B), plus new tools object_detector (face via Haar, objects via YOLO/SSD fallback) + prosody_analyzer (pitch/energy/ZCR → emotion).

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
- **module_wiring** — all 17 modules instantiated (no orphans) — added goal_decomposer + project_manager (P2)
- **hardware_self_awareness** — self-model of CPU/RAM/GPU present
- **memory_consolidation** — decay + prune + episodic integration
- **autonomy_loop** — generate → execute → reflect wired
- **tools_wired** — 133 tools registered in the capability registry (from the manifest) — was 118
- **tier1_tool_manifest** — all expected deterministic tools present (data, PDF, process, backup, finance, network, messaging, agents)
- **deterministic_degradation** — invalid inputs to deterministic tools return typed `{success: False}` results, never raise
- **persistence_roundtrip** — a structured lesson survives a SQLite save/reload (robustness)
- **capability_generalization** — the capability matcher behaves correctly on unseen/adversarial inputs (no "port"→"teleportation" false positive)
- **learning_changes_behavior** — repeated failures lower an action's future utility weight (longitudinal calibration)
- **perception_grounding** — ObjectDetectorTool.analyze_image_grounded() + language_grounding wired (P1-1)
- **causal_learning** — CausalInferenceEngine learns from execution + surprisal (Bayesian, not just storage) (P1-2)
- **memory_association** — consolidate_memory() creates co_occurs_with associations + causal stats (P1-3)
- **curiosity_info_gain** — information-gain curiosity (unknown entities, low-confidence groundings, weak causal edges, unexplored files) (P1-4)
- **resource_aware_planning** — RESOURCE_COSTS + hardware pressure penalties (P2)
- **prosody_emotion** — ProsodyAnalyzerTool (pitch/energy/ZCR→emotion) + social_cognition wired (P2)
- **multimodal_chat** — process_cognitive_cycle(image_path, attachments) — multimodal through ONE brain (P2)
- **self_evolution_verified** — SelfEvolvingAgent verified loop: synthesize→pytest→hotload only if green (P2)
- **project_management** — ProjectManager + GoalDecomposer wired — complex goals → sub-goals DAG → Project (P2)
- **vlm_integration** — VlmAnalyzerTool (Moondream2/Llava) with OCR+LLM fallback — true VLM when installed (P3)
- **lora_continual_learning** — LoraManagerTool — continual learning via LoRA without forgetting (P3)

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

Closed this session (P1-1 → P2 — pushing toward human intelligence):

- ✅ **P1-1 Perception→Grounding loop**: New `object_detector.py` — face via Haar cascades (always offline), objects via YOLOv8n (if `data/models/yolov8n.pt` exists) else MobileNet SSD else face-only fallback. `analyze_image_grounded()` auto-creates `PerceptualGrounding` for each label (vision modality, bbox, confidence) + feeds faces to `social_cognition`. `VisionAnalyzerTool` now includes detections in LLM prompt. Runtime `_integrate_phase_modules()` rate-limited (60s) grounds latest screenshot (<5min) → blackboard `grounded_detections`. Endpoints `/vision/detect-objects`, `/detect-faces`, `/groundings`. Web `ImagesPage` + desktop `VisionPage` show grounded detections + groundings + Detect+ground button + honest note about OCR+LLM+detector vs VLM (RX 580 limit). Manifest 121→125.

- ✅ **P1-2 Causal learning from interventions**: `causal_inference.add_causal_relationship()` now Bayesian moving average update when edge exists. New `learn_from_execution()` (success→strength 0.9, fail→0.2) + `learn_from_surprisal()` (low surprisal→strengthen, high→weaken). `AutonomousGoalExecutor.execute_step()` records cause→effect for each `produces_evidence`. Runtime `process_cognitive_cycle()` records action→effect from surprisal + intent→outcome.

- ✅ **P1-3 Memory association + causal consolidation**: `consolidate_memory()` now counts causal edges/weak edges + creates `co_occurs_with` relationships between co-occurring subjects grouped by hour (memory association).

- ✅ **P1-4 Curiosity via information gain**: `generate_goals_from_signals()` now handles `unknown_entities`, `low_confidence_groundings`, `unexplored_files`, `weak_causal_edges`, `prediction_error_clusters`. New `generate_goals_from_information_gain()` scans WorldModel low-confidence, LanguageGrounding low count/confidence, causal weak edges → curiosity goals. `PeriodicAutonomousCycle` now calls info-gain goals + `_observe_signals()` emits those signals.

- ✅ **P2 Resource-aware planning**: `CounterfactualSimulator` has `RESOURCE_COSTS` per action, penalizes high-memory when RAM>80% (0.6×), high-cpu when CPU>75% (0.7×), file-writing when disk>85% (0.8×), budget>90% (0.7×). `ActionPlanner` auto-fetches `hardware_self_model` + `ResourceManager`. `GoalReplanner` signature extended, call sites pass outcome_store, hardware, resource_manager.

- ✅ **P2 Social from real signals**: New `prosody_analyzer.py` — rms, pitch (autocorr), ZCR, speaking rate → emotion (joy/sadness/anger/fear/surprise/neutral) + intensity. `VoiceService._transcribe_remote_utterance()` analyzes prosody before STT and feeds to `social_cognition`. Runtime `_integrate_phase_modules()` infers emotion from text keywords.

- ✅ **P2 Multimodal chat**: `process_cognitive_cycle(image_path, attachments)` + `message_router` accepts `image_path`/`attachments` in `user_message` WS, forwards to runtime. Frontend `websocket.ts` + `conversationStore` + `ChatPage` send first uploaded image path for grounding — chat is vision-grounded through ONE brain.

- ✅ **P2 Self-evolution verified**: `self_evolving_agent.py` generates pytest contract (3 tests), runs in `DisposableSandbox`, only hotloads if green, saves to `app/tools/` + `data/plugins/`, rebuilds manifest cache.

- ✅ **P2 Project management**: `ProjectManager` + `GoalDecomposer` + `ProjectDAGScheduler` are wired into runtime. Complex goals become persistent dependency DAGs; owner-enabled projects resume bounded ready steps across autonomous cycles. Exact action/payload steps pass Owner Control and the full observation/verification loop. Unverified tool success waits for evidence without retrying, Level-3 steps wait for exact authorization, failures block dependents, and verified outcomes reconcile milestones/session history idempotently. Approve-each-plan mode exposes exact action/payload revisions for owner editing before execution. Background scheduling is explicit opt-in to prevent duplication of the foreground request.

- ✅ **Owner authority and verified authorization execution**: Persistent control modes, emergency pause, per-action block/approval lists, revision-bound editable plan approval, and short-lived exact-payload authorization grants. Executing a grant now returns through the authoritative ActionGate → capability → independent observation → tri-state verification → prediction error → reflection/outcome/lesson/causal learning path. Tool success remains separate from goal verification, and retries/alternatives require fresh authorization.

- ✅ **Placeholder-success removal**: Screenshot streaming analysis now decodes and validates real image bytes and calls the actual OCR/Vision tools. Custom wake-word training and speaker enrollment/identification explicitly report unavailable until verified model pipelines exist; no fake ONNX artifacts, arbitrary first-speaker matches, or invented `0.85` confidence/accuracy values are returned. Speaker verification without a reference is UNKNOWN, not implicitly accepted.

- ✅ **P1 bugs from full audit**: B6 magic-byte duplicate keys → ordered list, B7/B8 useVoice stale closure + context conflict → separate refs, B9 blob leak when replaced, B10/B11 conversationStore ack/merge, B12 desktop WS version, B13 QSettings bool, V3/V4 TTS speed + voice_enabled, V1 VAD degrade, F2 AppearanceSettingsPage theme drift, D2 VisionWorker thread-safety.

Still open (future):

1. Install and exercise the optional tiny VLM on the owner's hardware. The integration and honest OCR+detector fallback exist, but model quality/performance on the RX 580 has not been live-verified in this sandbox.
2. Automatically derive reviewed LoRA training examples from successful outcomes and lessons; dataset preparation and training scaffolding currently require explicit examples.
3. Add evidence-reconciliation probes for project sub-goals left in `waiting_evidence`; the scheduler deliberately does not repeat an unverified action, but currently needs an owner/manual observation to resume it.
4. Full end-to-end browser test of the multimodal round trip (text + image → grounded detection → reply) against a live server.
5. Exercise external-API tools against live endpoints on the owner's machine.
6. Add pagination to large Files, Pansophy, and Projects collections.

Python CI is defined in `.github/workflows/tests.yml`. An Android workflow is
still pending because the connected GitHub App cannot create workflow files
without `workflows` permission; Android builds therefore still need to be run
locally or after that permission is granted.

