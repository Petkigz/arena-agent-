# Arena Agent — Measured Status

**Updated:** 2026-08-23 · Branch `arena/01a02b25-arena-agent`
**This is the canonical status document.** It supersedes the percentage-based status
files that previously lived at the repo root (`AGI_STATUS.md`, `AGI_LEVEL_ASSESSMENT.md`,
`AGI_FINAL_SUMMARY.md`, `PHASES.md`, `PROJECT_REVIEW.md`, and the recovered branch's
`HUMAN_LEVEL_AGI_ACHIEVED.md` / `FINAL_AGI_STATUS.md`). Those used invented "% AGI"
and test-count figures that did not match the code; they are now archived under
`docs/archive/`. This document is measured.

> **2026-08-23 remediation update:** The release blockers found by the latest
> audit have been repaired locally: one authoritative runtime now serves REST and
> WebSocket paths; model-generated tools reject simulated completions; the
> unified server starts with core dependencies; native safety fields match the
> backend; conversation identifiers require auth; approvals persist without
> persisting authority; and the software-only dependency set runs the complete
> backend suite. GitHub Actions run `32635400747` then passed from a clean runner
> after dependency installation and the full pytest job. See
> [`docs/FULL_AUDIT_2026-08-23.md`](docs/FULL_AUDIT_2026-08-23.md).

---

## What this system is

A **local-first, full-capability coworker / friend** with a closed-loop cognitive architecture. Owner-defined approval gates, not a restricted demo: nothing is off-limits, but sensitive/irreversible actions require explicit owner approval (Level 3).

**Owner hardware target:** Intel Core i9-14900K · RX 580 8 GB (CPU inference) · 48 GB RAM · LM Studio · Qwen fast + reasoning routes. Runtime values are probed rather than trusted from this document.

---

## Measured facts (verified, not claimed)

| Metric | Value | How it was measured |
|---|---|---|
| Backend tests passing | **1589 passed, 2 skipped, 4 deselected e2e** | Clean software-only environment: `python -m pytest -q` on 2026-08-23; 2 notifier warnings only |
| Frontend tests passing | **184** | `cd frontend && npm test -- --run` → `184 passed` on 2026-08-23 |
| Frontend build | ✅ | `npm run build` (tsc + vite) succeeded on 2026-08-23 |
| Python source | ~50,000 lines / 220 files | `find app backend -name '*.py' -exec cat {} + | wc -l` |
| Tools in the manifest | **150** | `len(get_tool_manifest())` — added detect_objects, detect_faces, analyze_image_grounded, analyze_prosody, vlm_analyze, vlm_status, list_loras, lora_status, activate_lora, deactivate_lora, prepare_lora_dataset, create_lora_job (P1-1, P2, P3) |
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
      → capability execution (150 manifest tools)
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
- **tools_wired** — 150 tools registered in the capability registry (from the manifest) — was 118
- **tier1_tool_manifest** — all expected deterministic tools present (data, PDF, process, backup, finance, network, messaging, agents)
- **deterministic_degradation** — invalid inputs to deterministic tools return typed `{success: False}` results, never raise
- **persistence_roundtrip** — a structured lesson survives a SQLite save/reload (robustness)
- **capability_generalization** — the capability matcher behaves correctly on unseen/adversarial inputs (no "port"→"teleportation" false positive)
- **learning_changes_behavior** — repeated failures lower an action's future utility weight (longitudinal calibration)
- **perception_grounding** — ObjectDetectorTool.analyze_image_grounded() + language_grounding wired (P1-1)
- **causal_learning** — CausalInferenceEngine learns from execution + surprisal (Bayesian, not just storage) (P1-2)
- **memory_association** — consolidate_memory() creates co_occurs_with associations + causal stats (P1-3)
- **curiosity_info_gain** — information-gain curiosity with outcome-calibrated thresholds and owner-bounded exploration budget (P1-4)
- **resource_aware_planning** — RESOURCE_COSTS + hardware pressure penalties (P2)
- **prosody_emotion** — ProsodyAnalyzerTool (pitch/energy/ZCR→emotion) + social_cognition wired (P2)
- **multimodal_chat** — text/image/file chat plus persistent stream-isolated object tracking and temporal events through ONE brain (P2)
- **self_evolution_verified** — SelfEvolvingAgent verified loop: synthesize→pytest→hotload only if green (P2)
- **project_management** — ProjectManager + GoalDecomposer wired — complex goals → sub-goals DAG → Project (P2)
- **vlm_integration** — VlmAnalyzerTool (Moondream2/Llava) with OCR+LLM fallback — true VLM when installed (P3)
- **lora_continual_learning** — verified outcomes propose redacted examples; owner review gates reproducible LoRA train/eval dataset export; PEFT training/selection is available, while external-runtime loading remains explicitly unverified (P3)

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

- ✅ **P1-3 Evidence-linked semantic memory consolidation**: Every terminal GoalVerifier result now records a structured episodic memory. Sleep-like consolidation promotes only verifier-authored terminal episodes into provenance-linked semantic memories or failure lessons; repeated verified successes create reusable procedures. A consolidation-link ledger makes this idempotent and prevents unverified/self-reported episodes from being promoted or starving the queue. Retrieval now combines exact tokens, normalized concepts, character n-grams, and importance locally, with no cloud/model dependency. Causal statistics and `co_occurs_with` world associations remain part of the same maintenance pass.

- ✅ **Owner-sovereign autonomy**: Limits are optional and disabled by default. The owner may create persistent directives, inspect the queue, approve/reject planning, reprioritize, and separately request execution. A timezone-aware persistent calendar releases one-time, daily, or weekly owner directives with explicit missed-run policy. Owner priority is authoritative in queue selection: critical/high directives preempt higher-scored normal/low goals before execution begins. Goal/schedule approval never authorizes actions. A run ledger records observation, consideration, recommendation, planning approval, execution, blocking, budget stops, and outcomes. Multi-goal allocation makes owner priority dominant, excludes incomplete dependencies, and uses CPU/RAM pressure only among comparable ready work. Approved plan revisions persist environment assumptions—owner policy, tool contracts/availability, interfaces, capability count, and goal priority—and fail closed across sessions when those assumptions drift. Urgent owner goals can preempt active work through cooperative cancellation receipts; resume is separately requested only after cancellation observation, remains evidence-reconciliation gated, and never automatically replays uncertain side effects. Exact sovereign grants may override owner policy, while emergency pause, physical availability, critical resources, payload integrity, and evidence honesty remain absolute.

- ✅ **P1-4 Adaptive curiosity via information gain**: Structured signals cover unknown entities, low-confidence groundings, unexplored files, weak causal edges, and prediction-error clusters. Prediction-error, low-success, and goal auto-approval thresholds now calibrate from verified strategy outcomes after a minimum sample count, using bounded smoothing and conservative clamps. A persistent owner maximum caps the combined exploratory goals per cycle (including zero), and free-text keyword generation is a true fallback rather than an extra unbounded channel.

- ✅ **P2 Resource-aware planning**: Hardware tiers and resource limits are live-probed rather than fixed at 16 GB. A 32GB+ / 20-thread host receives the high-memory profile; 40GB+ can schedule up to six CPU tasks and consider 14B Q4 CPU inference while retaining a faster 9B route. Pressure remains percentage-based, so 48 GB naturally permits more work without disabling critical 95–98% safety checks. Counterfactual planning still penalizes actual CPU/RAM/disk pressure.

- ✅ **P2 Social from real signals**: New `prosody_analyzer.py` — rms, pitch (autocorr), ZCR, speaking rate → emotion (joy/sadness/anger/fear/surprise/neutral) + intensity. `VoiceService._transcribe_remote_utterance()` analyzes prosody before STT and feeds to `social_cognition`. Runtime `_integrate_phase_modules()` infers emotion from text keywords.

- ✅ **P2 Multimodal + temporal vision**: Chat accepts text, image paths, and attachments through one runtime. `TemporalVisionTracker` now assigns persistent label/IoU track IDs per explicit visual stream and records appeared/moved/disappeared events, confidence, frame counts, and bounding-box evidence in SQLite. Desktop sight and live screenshot streams feed the tracker; events enter the blackboard and WorldModel as inferred perception. Static unrelated uploads are deliberately not treated as a temporal sequence. This is object continuity, not person identity, depth, intent, facial emotion, or full video understanding.

- ✅ **P2 Self-evolution verified**: `self_evolving_agent.py` generates pytest contract (3 tests), runs in `DisposableSandbox`, only hotloads if green, saves to `app/tools/` + `data/plugins/`, rebuilds manifest cache.

- ✅ **P2 Project management**: `ProjectManager` + `GoalDecomposer` + `ProjectDAGScheduler` are wired into runtime. Complex goals become persistent dependency DAGs; owner-enabled projects resume bounded ready steps across autonomous cycles. Exact action/payload steps pass Owner Control and the full observation/verification loop. Unverified tool success enters `waiting_evidence`; later cycles run capability-specific observation probes only—never the action again—and can complete/fail the sub-goal when new evidence appears. Level-3 steps wait for exact authorization, failures block dependents, and verified outcomes reconcile milestones/session history idempotently. Approve-each-plan mode exposes exact action/payload revisions for owner editing before execution. Background scheduling is explicit opt-in to prevent duplication of the foreground request.

- ✅ **Owner authority and verified authorization execution**: Persistent control modes, emergency pause, per-action block/approval lists, revision-bound editable plan approval, and short-lived exact-payload authorization grants. Executing a grant now returns through the authoritative ActionGate → capability → independent observation → tri-state verification → prediction error → reflection/outcome/lesson/causal learning path. Tool success remains separate from goal verification, and retries/alternatives require fresh authorization.

- ✅ **Simulated-success removal**: Screenshot capture, desktop mouse/keyboard/hotkeys, Win32 HWND operations, browser navigation, TTS, research digests, SVG generation, device pairing/onboarding, wake-word training, and speaker identification now fail or display unavailable explicitly instead of fabricating artifacts, windows, navigation, speech, connections, models, or confidence. LLM-offline responses carry `success=false`/`simulated=true`, and conversational ANSWER goals defer rather than becoming verified from placeholder text. Cross-domain similarity is now `predicted_success` with `verified=false`; it cannot update transfer success history until external evidence is recorded.

- ✅ **Reviewed and evaluation-gated LoRA pipeline**: Verified successful outcomes propose deduplicated prompt/response candidates with deterministic secret, email, phone, and home-path redaction. Simulated/unverified responses are rejected. Candidates remain pending until the owner edits and approves the exact pair. Export requires at least five approved examples and produces reproducible train/eval JSONL plus a provenance manifest. Provider evaluation compares distinct base and adapter/merged model identifiers on the skill holdout and an unrelated-domain regression set, stores scores and hashes rather than raw outputs, and blocks deployment on model-identity mismatch, insufficient improvement, or excessive regression. Passing evaluation still does not deploy: the owner must separately deploy, which performs a fresh provider probe and applies an in-memory model route that is deliberately cleared on restart.

- ✅ **Evidence-linked functional self-knowledge and commitments**: A revisioned SQLite ledger records hardware, capability, authority, and limitation claims only with source type, evidence, confidence, timestamp, and freshness. Contradicting observations create structured revisions containing old/new values, evidence, confidence delta, and a deterministic explanation. Predicted competence is now recorded against verified outcomes and reported with ECE, evidence sufficiency, per-action samples, and improving/stable/worsening trend. Agency attribution distinguishes self-caused, owner-caused, external, and unknown changes; temporal proximity alone remains unknown. A restart-safe commitment ledger reconciles persistent projects and exact authorized actions; completion requires verification evidence and blocked work retains a reason. Introspection uses persisted trace facts and denies access to hidden chain-of-thought. An embodied-boundary ledger separates Arena interfaces, owner devices, shared actuators, and external state. Persistent OS grounding links owner tasks to verified executable paths, process IDs, and optional window/display/region evidence; ambiguous process names do not resolve. Semantic accessibility snapshots support bounded Windows UIA and Linux AT-SPI capture, unique role/name resolution, and observed bounds. Browser sessions/tabs persist URL, title, profile type, popup ancestry, accessibility links, and transfer events; authentication remains unknown and owner takeover blocks automation. Browser downloads require a real Playwright event, workspace-confined non-overwriting destination, observed file/hash, and hash-guarded rollback. Upload submission is a separate Level-3 action; success requires an observed service-specific success selector, while missing confirmation remains unknown with remote side effects explicitly possible. A command alone never proves control. This is operational introspection, not consciousness or biological embodiment.

- ✅ **Longitudinal intelligence regression history**: An isolated deterministic suite now measures 14 checks: paraphrased memory retrieval, success/failure utility adaptation, outcome-calibrated autonomy, evidence-linked consolidation, authorization replay resistance, temporal continuity, LoRA review boundaries, project dependency unlocking, owner curiosity limits, conservative agency attribution, restart-safe commitment continuity, longitudinal self-belief calibration, and embodied-boundary integrity. Each run persists per-check evidence/metrics/duration and reports pass→fail regressions against the previous run. It reports factual pass counts, never an “AGI percentage,” and does not mutate the live brain.

- ✅ **Transactional and privilege-aware OS changes**: File moves, copies, and archives reject overwrite/missing-source conflicts, verify path state and content hashes, and emit exact compensation facts. Copy/archive rollback removes only an unchanged hash-matching artifact under fresh Level-3 approval. Backup restore verifies recorded SHA-256, ZIP CRC, and path containment to block corrupted archives and zip-slip traversal; restore side effects are never claimed automatically reversible. Process identity includes owner, executable, parent PID, creation time, and launch provenance; verified termination binds the exact instance, waits for exit, rejects PID reuse, and admits rollback is impossible. Clipboard inspection is read-only; sensitive clearing is a separate Level-3 action that verifies empty state and retains no secret for fake rollback. Software updates now report command success separately from before/after or expected installed-version verification; unobservable versions remain unknown.

- ✅ **Cooperative execution control + rollback receipts**: Every runtime capability execution now receives a persistent execution ID, cancellation state, and rollback receipt. Owner stop requests are visible while work runs; ToolRegistry checks cancellation around handlers. A shared cancellable process-group runner covers disposable sandbox, package manager, ADB/device, system update, git, ping, and traceroute subprocesses. A cancellable blocking-call bridge now covers local model HTTP, browser HTTP fallback, multi-engine research, messaging/webhooks, weather/location/prices/RSS/media, and local HTTP calls; owned clients are closed to interrupt transport where possible, while browser steps check cancellation between Playwright operations. Cancellation arriving after dispatch is reported honestly because remote side effects may already exist. Rollback is never implied: unsupported actions receive a reason, while supported compensation creates a new exact approval request rather than auto-running.

- ✅ **Optional-tool startup isolation**: The API, manifest, `ToolRegistry`, and `CognitiveRuntime` no longer import every optional tool package at startup. Tool classes resolve only when invoked or explicitly probed; missing packages return typed `dependency_unavailable` results for that capability alone. `GET /tools/availability` reports per-tool status without probing by default. Full and core-only requirement sets are now separate while `requirements.txt` preserves the full-install behavior.

- ✅ **Bounded collection pagination**: Projects now use stable updated-time/id ordering with limit, offset, total, and continuation metadata; web and desktop project views load 50 at a time. Memory/Pansophy and workspace-file APIs expose separate bounded page endpoints while retaining backward-compatible unpaged routes for existing clients. Category, project-status, and file-extension filters are applied before pagination so page counts and continuation remain correct.

- ✅ **Native Owner Control operations**: Desktop and Android expose policy mode, autonomous safety ceiling, exploration cap, emergency pause/resume, exact recommendation approval/rejection, revision-bound exact plan-step JSON editing, plan approval/rejection, separate approved-plan execution, active authorization execution/revocation, execution cancellation, and rollback-request creation. Reviewed grants expose their original payload only when it still hashes to the immutable authorization digest; direct grants never invent a payload. Both native clients explicitly preserve authorization versus execution, report goal verification separately from tool success, and keep rollback as a new approval. Desktop API credentials are now local QSettings connection state applied to every HTTP request—not synced into backend preferences—so these controls work with an authenticated server.

- ✅ **P1 bugs from full audit**: B6 magic-byte duplicate keys → ordered list, B7/B8 useVoice stale closure + context conflict → separate refs, B9 blob leak when replaced, B10/B11 conversationStore ack/merge, B12 desktop WS version, B13 QSettings bool, V3/V4 TTS speed + voice_enabled, V1 VAD degrade, F2 AppearanceSettingsPage theme drift, D2 VisionWorker thread-safety.

Still open (future):

1. Install and exercise the optional tiny VLM on the owner's hardware. The integration and honest OCR+detector fallback exist, but model quality/performance on the RX 580 has not been live-verified in this sandbox.
2. Exercise LoRA training, base/adapter held-out evaluation, and provider deployment against the owner's real LM Studio models and hardware. The evaluation/deployment gate now exists, but no adapter improvement or RX 580 performance is claimed from sandbox-only deterministic tests.
3. Extend immediate cancellation into third-party model/media calls and Playwright operations that expose no safe cross-thread interrupt. HTTP calls now return control promptly through a cancellable bridge and close owned transports where possible; Playwright checks between operations, but an in-progress synchronous navigation can still run until its bounded timeout.
4. Full end-to-end browser test of the multimodal round trip (text + image → grounded detection → reply) against a live server.
5. Exercise external-API tools against live endpoints on the owner's machine.
6. Extend the new pagination contracts to any remaining high-volume audit, conversation, and temporal-history views as real owner datasets grow.
7. Live-test the native Owner Control screens against a running authenticated backend, including stale plan revision conflicts, grant expiry while visible, cancellation during a real process, and rollback approval creation. Static/API contracts are covered here; Android could not compile in this sandbox because Java/Android SDK tooling is absent.

Python CI is defined in `.github/workflows/tests.yml`. An Android workflow is
still pending because the connected GitHub App cannot create workflow files
without `workflows` permission; Android builds therefore still need to be run
locally or after that permission is granted.

