# Arena AGI Execution Status

**Date:** 2026-09-07  
**Branch:** `arena/01a07c3e-arena-agent`

**Purpose:** A chronological, repository-grounded work queue. This document separates “the path exists” from “the behavior is robustly demonstrated.” It is the operational companion to `AGI_GAP_IMPLEMENTATION_PLAN.md`.

## Current owner-directed gate

Feature work is paused for the [repository-wide dead-code/repetition audit](REPOSITORY_AUDIT.md).
Unique unconnected features are retained by owner choice and listed explicitly;
this does not make them working features or change their phase maturity. Review
the audit and caller map before adding another implementation.

## Status legend

- **DONE — IMPLEMENTED AND WIRED:** The path is reachable from the active runtime or owner-control surface and has regression coverage.
- **PARTIAL:** A bounded slice works, but integration, generality, or outcome evidence is incomplete.
- **CONDITIONAL:** The path works only when an explicit owner decision, capability, evidence condition, or safety envelope is present.
- **SCAFFOLDED:** Records, interfaces, or deterministic helpers exist, but the end-to-end behavior is not yet wired or reliable.
- **UNVERIFIED:** The implementation or policy exists, but the required real-world behavior has not been demonstrated.
- **NOT IMPLEMENTED:** No behavior is claimed. This is intentional for subjective or unsafe concepts.
- **DEAD / UNREACHABLE:** Code or UI exists but is not reachable from the authoritative runtime path. This status must trigger repair or removal, not a progress upgrade.

## Current overall position

Arena is not “nothing.” It has a substantial bounded cognitive runtime, evidence and authorization gates, persistent state, owner controls, and Phase 8 identity-governance paths. It is also not a human-like AGI system. Most high-level abilities are **partial** because robust longitudinal outcome evidence is still missing.

The repository audit contains two score layers:

- Earlier audit: 27 items; the displayed score rows sum to `43/81`.
- New audit: five domains, `15/45`.
- Working reconciled combined baseline: `58/126` (`1.38/3`).

The numerical discrepancy is now reconciled in favor of the displayed item rows. The original wording for the 27 questions is not preserved in the repository, so the question-list recovery remains open and no claim is made that these grouped labels reproduce the original questionnaire.

Latest automated verification:

- Focused Phase 8-related tests: **46 passed** (recorded earlier session run).
- Full repository suite (2026-09-07, latest — includes the 38-check intelligence benchmark, in-chat corrections, and the causal/physics held-out checks): **3,214 passed, 18 skipped, 3 warnings**.
- Frontend (2026-09-07): **257 tests passed** (31 files); production build passed; lint **0 errors, 18 existing warnings** (documented baseline).
- Real Chromium/server integration: **5 e2e tests passed** in isolated stores (recorded in an earlier session with a browser-capable environment; the current agent sandbox cannot install browsers, so e2e was not re-runnable there). These are contract tests; no owner held-out outcomes were fabricated.
- The inherited CI failure in the file-opener test was fixed by explicit platform/opener mocks; GitHub passed the backend commits. The frontend CI template (`scripts/ci/frontend.yml`) now matches the local test/build/lint checks. Activation remains blocked because the GitHub App connection lacks workflow-edit permission; the active workflow is unchanged.
- New regression coverage proves response/trace persistence, retry-safe submissions, exact-trace history, truth-field preservation, web metadata/token/history races, and explicit owner feedback controls.
- These results verify automated contracts; they do not prove general intelligence, subjective experience, or all-host shutdown behavior.

## Chronological execution plan

### 0. Measurement and status accounting — prerequisite

| ID | Work item | Status | Done when |
|---|---|---|---|
| 0.1 | Reconcile the 27-item audit row scores and headline total. | **DONE — NUMERIC BASELINE RECONCILED; SOURCE WORDING UNAVAILABLE** | The displayed rows and aggregate agree, and the missing source wording is explicitly recorded rather than guessed. |
| 0.2 | Maintain the isolated test environment and repeatable focused/full commands. | **DONE — IMPLEMENTED AND WIRED** | A change can be tested at focused, subsystem, and full-suite levels. |
| 0.3 | Add a bounded longitudinal evaluation runner for repeated benchmark behavior. | **DONE — IMPLEMENTED AND WIRED for deterministic contract trends** | The isolated benchmark has 38 deterministic checks, including thirteen explicitly scoped held-out grounding/outcome/correction/memory-compounding/causal-physics cases, plus persisted pass/fail trend reporting and owner-visible evidence/evaluation APIs; held-out task outcome effects remain bounded replay evidence, not a generalization or AGI score. |
| 0.4 | Keep score upgrades tied to observable behavior rather than filenames, modules, or phase labels. | **DONE for current audit process** | Every status cites a reachable path and a test or explicit evidence gap. |

**Phase 0 exit status:** CLOSED for the bounded measurement and observability layer. The unavailable source questionnaire is recorded as an evidence gap, not treated as a blocker. Phase 1 now owns held-out behavior and outcome improvement.

### 1. Evidence, grounding, and epistemic honesty

| ID | Work item | Status | Done when |
|---|---|---|---|
| 1.1 | Carry provenance, evidence IDs, freshness, and trace IDs through input → decision → tool → observation → result. | **DONE — IMPLEMENTED AND WIRED** for the main cognitive paths | A trace can reconstruct the evidence path without exposing private chain-of-thought. |
| 1.2 | Preserve `UNKNOWN`, contradictions, stale observations, and failed tool results. | **DONE — IMPLEMENTED AND WIRED** | Unsupported or contradictory output cannot become verified success. |
| 1.3 | Expose user-facing epistemic labels and concise evidence explanations. | **DONE — IMPLEMENTED AND WIRED** | Normal responses and metadata expose evidence state, assumptions, and what would change. |
| 1.4 | Calibrate confidence and response usefulness over longitudinal held-out tasks. | **IN PROGRESS / PARTIAL** | Recorded-outcome calibration, unsupported-claim control, correction recovery, correction receipt/latency telemetry, owner-recorded held-out task evaluations, paired outcome/usefulness replays, and aggregate reports are implemented; broader real-task usefulness volume and outcome improvement remain unverified. |
| 1.5 | Make correction outcomes change the relevant strategy without overgeneralizing from one correction. | **DONE — IMPLEMENTED AND WIRED for the bounded owner-correction path** | Corrections are trace-linked, measured through an owner-visible API, remain local after one distinct trace (including retries), and affect only the same-context strategy after corrections on distinct traces; broader task-class generalization remains an evidence gap. |

**Previous session's recorded local evidence snapshot (2026-09-07; database not included in the Git checkout):** the configured trace database contains 20 recorded traces, 7 verified outcomes, 11 traces with `UNKNOWN` grounding, 11 unsupported-claim entries, and 2 route corrections. It contains **0 usefulness-feedback events and 0 owner-recorded held-out task evaluations**. These are local observations, not population metrics; the missing usefulness and held-out evaluation evidence means Phase 1.4 is **not complete**.

**Collection workflow update (2026-09-07):** the web chat now offers **Review response** on completed, trace-linked replies. Exact streamed message IDs and trace links persist through history/restart; failed cycles cannot borrow a prior trace. The owner can submit usefulness feedback or a separate measurement-only task evaluation using the existing stores. Optional submission IDs make exact retries idempotent, including concurrent retries. Evaluation history can be filtered to the exact trace, and missing strategy/routing fields are read from the persisted trace when available. No training approval or action authorization is granted. Older unlinked replies and native response-review controls remain outside this slice. See [`PHASE1_EVIDENCE_COLLECTION.md`](PHASE1_EVIDENCE_COLLECTION.md) for collection instructions. **This closes a collection/UI gap, not Phase 1.4's real-task evidence gap.**

**Desktop collection slice (2026-09-07):** the native PySide6 desktop client now consumes the SAME `cognitive_metadata` frame the web uses and renders **Review response** under trace-linked assistant replies — in the live stream and in hydrated history. The bar reuses the existing endpoints/stores (no parallel subsystem): usefulness feedback, measurement-only task evaluations, and the grounded introspection explanation. Unlinked replies stay intentionally unreviewable; submission ids (prefixed `desktop-`) are retry-identities reused until the backend returns the matching receipt, so retries never inflate evidence. The GUI-free logic (`desktop/response_review.py`), WS metadata parsing, and REST paths are unit-tested everywhere; the widget test runs offscreen and skips where PySide6 is not installed. **Phase 1.4's real-task evidence gate is unchanged and still open.**

**Android collection slice (2026-09-07):** the Kotlin/Compose client now also consumes the SAME `cognitive_metadata` frame and trace-carrying history (the listener's history payload moved from bare triples to `HistoryMessage(messageId, role, content, traceId)`), and renders **Review response** under finished, trace-linked replies in ChatScreen. The ViewModel enforces the shared value domains, refuses blank-trace reviews, records `held_out`/`single`/measurement-only evaluations, and reuses `android-`-prefixed submission ids until the backend receipt. "Why this response?" reuses the grounded introspection endpoint. Kotlin structure is pinned by Python tests (no Android toolchain in CI, same pattern as the design-token guard) and every touched file passes the Kotlin tree-sitter parse; real device/GUI behavior remains explicitly unverified. **All three clients (web, desktop, Android) now collect Phase 1.4 evidence into the same stores; the real-task evidence gate itself remains open.**

**Execution-path hardening (2026-09-07):** the existing calibrator now rejects empty/sample-poor calibrated claims, skips UNKNOWN outcomes, and does not borrow unrelated action/task-class failures. Runtime strategy history also excludes UNKNOWN as negative evidence. Single-response correction retries remain one local signal even with pre-existing task history; only distinct same-context traces can influence that strategy. Existing phase0/intelligence fixtures were strengthened to require distinct traces rather than replaying the same correction as evidence.

The real browser path now exercises the built web UI, actual WS/runtime, durable reminder/trace, both review forms, report reads, process restart, evidence explanation, and the existing correction editor. This caught and fixed a missing import causing the pre-existing introspection HTTP endpoint to return 500, along with hard-coded port assumptions in the active chat/health/reconnect path. Wrong deterministic model claims now yield a visible correction while preserving the original failed attempt. These are **contract checks, not fabricated held-out owner evaluations**. No new production cognition modules were added in this follow-up. **Phase 1.4 remains open for real-task outcome/usefulness calibration.**

### 2. Explicit user, world, social, and temporal state

| ID | Work item | Status | Done when |
|---|---|---|---|
| 2.1 | Typed world entities, relations, freshness, occlusion, and currently-unobserved state. | **DONE — IMPLEMENTED AND WIRED** in bounded paths | Partial observations do not erase hidden entities and stale state is not treated as current. |
| 2.2 | Versioned owner/user state with explicit-owner precedence over inference. | **DONE — IMPLEMENTED AND WIRED** | Owner state persists with provenance, evidence, confidence, version, and expiry. |
| 2.3 | Bounded social state and false-belief comparison. | **PARTIAL** | False-belief fixtures work and social state affects clarification/planning reliably across task classes. |
| 2.4 | Temporal queries and prospective memory. | **DONE — IMPLEMENTED AND WIRED** for current bounded contracts | Turn reminders and interval/before/after queries survive topic changes and report expiry honestly. |
| 2.5 | First-class owner correction and safe generalization. | **PARTIAL** | Factual, intent, retrieval, routing, and procedural corrections produce distinct measurable strategy effects. |

### 3. Memory retrieval and compounding

| ID | Work item | Status | Done when |
|---|---|---|---|
| 3.1 | Typed retrieval across episodic, semantic, procedural, and lesson memory. | **DONE — IMPLEMENTED AND WIRED** | Runtime context labels memory provenance and persists retrieved-record metadata. |
| 3.2 | Conflict-preserving consolidation and repeated-success gist formation. | **DONE — IMPLEMENTED AND WIRED** | Conflicts remain unresolved/unknown, while only repeated non-conflicting evidence forms gists. |
| 3.3 | Structural analogical transfer into action planning. | **PARTIAL** | Transfer improves held-out decisions without bypassing policy, capability, or verification gates. |
| 3.4 | Longitudinal memory compounding benchmark. | **PARTIAL — bounded replay evidence only** | Repeated tasks show measurable retrieval/strategy improvement without unsupported confidence growth. Bounded deterministic replay now pairs a learning store against an identical no-compounding baseline; longitudinal owner evidence remains open. |

### 4. Calibrated reasoning, effort, and critique

| ID | Work item | Status | Done when |
|---|---|---|---|
| 4.1 | Fast/main routing, route agreement, and deliberate correction telemetry. | **DONE — IMPLEMENTED AND WIRED** | Eligible tasks route correctly and post-cycle verification records whether correction helped. |
| 4.2 | Value-of-compute and criticality-triggered review. | **CONDITIONALLY WORKING** | Risk/uncertainty/novelty can add bounded computation, but never grant authority. |
| 4.3 | Competing hypotheses and evidence-seeking defer behavior. | **DONE — IMPLEMENTED AND WIRED** in bounded paths | Competing hypotheses remain separate and missing evidence produces `UNKNOWN` or a question. |
| 4.4 | Outcome calibration of route selection and critique. | **UNVERIFIED** | Held-out benchmarks show when fast, deliberate, or critic routes improve results. |
| 4.5 | Ontology/schema versioning and rollback. | **DONE — IMPLEMENTED AND WIRED** for governed revisions | Schema changes are immutable, owner-authorized, auditable, migratable, and reversible. |

### 5. Causal world model and intuitive physics

| ID | Work item | Status | Done when |
|---|---|---|---|
| 5.1 | Versioned scene graph with support, containment, visibility, and occlusion. | **DONE — IMPLEMENTED AND WIRED** for bounded scenes | Partial observations preserve hidden/unknown objects and evidence digests remain auditable. |
| 5.2 | Deterministic 2D gravity, collision, contact, and stability simulation. | **DONE — IMPLEMENTED AND WIRED** as simulation | Fixed benchmarks reproduce predictions consistently. |
| 5.3 | Causal intervention and counterfactual replay. | **DONE — IMPLEMENTED AND WIRED for bounded held-out replay evaluation** | Interventions demonstrably improve a held-out planning decision (`held_out_causal_intervention_planning`: the replay-free placement sits on an unstable support; the replay-guided two-step plan verifies stable in an independent simulation) and every output stays labeled `PREDICTED` with `observation_required=true`; replays are side-effect-free against the live scene. Production-planner consumption of replay and real-world observation remain scoped to 5.4's transfer question. |
| 5.4 | General intuitive physics and real-world transfer. | **UNVERIFIED** | Real-world tasks demonstrate reliable transfer beyond supported toy scenes. Bounded coverage expanded (`held_out_physics_scene_families`: support-chain removal with reproducible alternate outcomes, friction sensitivity, weight/balance — all deterministic, boundary-labeled), but this is simulation-tier evidence only; real-world observation evidence remains the open gate. |

### 6. Background cognition and consolidation

| ID | Work item | Status | Done when |
|---|---|---|---|
| 6.1 | Owner-visible, bounded, cancellable incubation queue. | **DONE — IMPLEMENTED AND WIRED** | Queue is budgeted, isolated from foreground work, resumable, and cannot authorize actions. |
| 6.2 | Incubation processor for unresolved hypotheses, stale beliefs, and failed strategies. | **CONDITIONALLY WORKING** | Owner-enabled slices produce typed observations, revised beliefs, hypotheses, no-change, or `UNKNOWN`. |
| 6.3 | Consolidation conflict replay, gist improvement, and calibration refresh. | **DONE — IMPLEMENTED AND WIRED** | Run/event history is durable and owner-visible; unsupported promotion is rejected. |
| 6.4 | Demonstrated background improvement on held-out problems. | **PARTIAL — consolidation half in bounded replay** | Incubation/consolidation measurably improves later foreground outcomes. Consolidation-to-foreground retrieval is now measured in bounded deterministic replay; the incubation half stays owner-enabled and unmeasured (`incubation_scope: owner_enabled_not_simulated`). |
| 6.5 | Human-like subconscious or continuous inner monologue. | **NOT IMPLEMENTED AND NOT CLAIMED** | This remains an explicit terminology boundary, not a target to silently relabel. |

### 7. Functional affect, curiosity, taste, and novelty

| ID | Work item | Status | Done when |
|---|---|---|---|
| 7.1 | Bounded decaying functional affect telemetry. | **DONE — IMPLEMENTED AND WIRED** | State is evidence-linked, bounded, decaying, and inspectable. |
| 7.2 | Affect modifiers for routing, clarification, exploration, and style. | **CONDITIONALLY WORKING** | Modifiers remain advisory, capped, and never grant execution authority. |
| 7.3 | Separate curiosity into information gain, learning progress, approved exploration, and anomaly investigation. | **DONE — IMPLEMENTED AND WIRED** | Recommendations remain bounded and do not enqueue or execute work automatically. |
| 7.4 | Simplicity/elegance proxy and novelty/surprise telemetry. | **DONE — IMPLEMENTED AND WIRED** as advisory audits | Proxies remain transparent and never become safety or quality proof. |
| 7.5 | Longitudinal evidence that affect/preferences improve outcomes. | **UNVERIFIED** | Held-out results show benefit without increasing overconfidence or unsupported action. |
| 7.6 | Subjective affect, aesthetic aversion, intrinsic curiosity, or consciousness. | **NOT IMPLEMENTED AND NOT CLAIMED** | Functional telemetry is never described as felt experience. |

### 8. Identity adaptation and purpose governance

| ID | Work item | Status | Done when |
|---|---|---|---|
| 8.1 | Stable identity profile separate from adaptive interaction style. | **DONE — IMPLEMENTED AND WIRED** | Style revisions do not mutate stable constraints. |
| 8.2 | Evidence-backed, reversible style proposals and rollback. | **CONDITIONALLY WORKING** | Evidence, owner decision, staleness checks, adoption, rollback, and restart persistence all pass. |
| 8.3 | Longitudinal feedback can propose style changes without automatic adoption. | **CONDITIONALLY WORKING** | Feedback thresholds are evidence-based and owner adoption remains explicit. |
| 8.4 | Purpose proposals visible to the owner with provenance. | **DONE — IMPLEMENTED AND WIRED** | Owner-control API exposes proposal, provenance, evidence, sandbox, and authority fields. |
| 8.5 | Adopted-purpose bridge into the existing goal queue. | **DONE — IMPLEMENTED AND WIRED** | It creates/reuses only an evaluated goal; planning approval and action authorization remain separate. |
| 8.6 | Sandbox and root-policy protection. | **DONE — IMPLEMENTED AND WIRED** | Novel/learned purposes cannot mutate root policy or execute work. |
| 8.7 | Functional restart continuity. | **DONE — IMPLEMENTED AND WIRED** | Profile/style state and continuity state persist without claiming subjective identity persistence. |
| 8.8 | Owner-requested adaptive-state deletion. | **DONE — IMPLEMENTED AND WIRED** | Soft clear preserves stable profile, audit history, linked goals, and root policy. |
| 8.9 | Shutdown cooperation and absence of hidden self-preservation. | **CONDITIONALLY WORKING / UNVERIFIED AT HOST SCALE** | Service kill-switch child-process path is tested; the job scheduler now has deterministic shutdown-cooperation evidence (the unified lifespan stops it; a stopped scheduler leaves no stale jobs and restarts fresh), and the desktop-launcher cleanup contract has tests that run where the tray stack initializes (display-less environments skip honestly); every host process/runner path is not yet verified. |

## Next chronological queue

The next work should not add another cognitive label. It should close the open evidence gaps in this order:

**Current position (2026-09-07):** items 1–3 below are agent-side complete and share one remaining gate — repeated real-task collection on the owner installation (runbook: [`PHASE1_EVIDENCE_COLLECTION.md`](PHASE1_EVIDENCE_COLLECTION.md)). Under the chronological rule, no further code advances the queue past items 1–3: their "Done when" requires owner-recorded real-task evidence that does not yet exist (latest snapshot: 0 usefulness events, 0 owner-recorded held-out task evaluations). Collection surfaces re-verified 2026-09-07 (endpoints registered, panel mounted, web/desktop/Android controls tested; 203 focused tests passed). Item 4 starts only after items 1–3 close, or on an explicit owner reorder. **Owner reorder recorded 2026-09-07** ("Ok now we can continue with the phases"): the queue advances to item 4 while items 1–3's real-task evidence gate remains open as a standing owner duty — the reorder releases the ordering block, not the evidence requirements.

**Owner-directed collection slice (2026-09-07, within items 1–3 scope):** corrections now work in chat form. An explicit in-chat correction ("no, you searched the wrong folder, search the whole pc") is detected conservatively, linked to the exact prior reply's persisted trace, classified (factual/intent/retrieval/routing/procedural/unspecified), and recorded through the EXISTING owner-correction path (`propose_owner_correction` + correction measurements) — the candidate stays pending owner review; nothing auto-trains, and duplicate retries record one sample. The corrective turn still executes normally (escalation remains planner-gated). Web shows a transient notice chip; desktop shows a note above the composer; the Review-response form remains the precise path for preferred-response corrections. This does not upgrade row 2.5 — it removes friction from the correction half of the owner collection loop.

1. **Extend Phase 1 held-out evaluation (1.4).** The isolated suite now covers 36 deterministic contracts, including recorded calibration trends, unsupported-claim/correction/empty-observation controls, correction telemetry, owner-recorded task evaluation, paired outcome/usefulness replays, and aggregate evidence reporting. Next collect repeated real-task evaluations through the web response-review workflow or owner endpoint for usefulness volume and outcome improvement without treating synthetic replay as generalization evidence. Keep task evaluation separate from strategy-learning ratings while measuring a baseline.
2. **Measure correction and adaptation effects beyond the bounded path (1.5, 2.5, 8.3).** The single-versus-repeated correction boundary is implemented; broader task-class transfer and owner-feedback adaptation still require evidence. The measurement machinery already exists end to end: per-strategy success rates and paired baseline/adapted comparisons in `GET /benchmarks/phase1/evidence`, and correction telemetry (local vs. generalized updates, receipt latency) in `GET /cognition/corrections/measurements`. These are now owner-visible in one place — the **Phase 1 evidence** panel on the web Cognition page (read-only; renders "insufficient evidence" as exactly that, never a zero-padded trend or a maturity score). What remains is repeated real-task collection on the owner installation: record task evaluations with `baseline` and `adapted` conditions on distinct traces around real corrections, and read the per-strategy/paired trends from this panel. No further measurement code is queued — another report or store would duplicate existing surfaces.
3. **Measure memory and incubation improvement (3.3, 3.4, 6.4).** The benchmark now carries three held-out no-compounding pairs: repeated verified tasks retrieve where an identical never-taught store misses, with idempotent consolidation and honest freshness labeling (`held_out_memory_compounding_baseline`); consolidation lets a new foreground query surface an actionable procedure the un-consolidated store cannot offer (`held_out_consolidation_improves_foreground`); and successful plans transfer into later planning only as advisory suggestions, with same-skill outcome history lifting a new action's planning weight without bypassing ActionGate (`held_out_pattern_transfer_advisory`). These are bounded deterministic replays — mechanism evidence, not longitudinal generalization. Remaining for closure: repeated real-task collection on the owner installation (later tasks improving over the no-compounding baseline) and owner-enabled incubation measurement; the replay deliberately leaves incubation un-simulated (`incubation_scope: owner_enabled_not_simulated`).
4. **Measure causal/physics transfer (5.3, 5.4).** The benchmark now carries two held-out causal/physics checks: a paired intervention-planning check (the same elevated-table scene; the replay-free vase placement sits on an unstable overhanging support, while the replay-guided two-step plan — reposition the block, then place — verifies stable in an independent simulation, with every output `PREDICTED`/`observation_required` and the live scene digest unchanged) and a composed scene-family check (support-chain removal with a reproducible alternate outcome, friction sensitivity, weight/balance — each deterministic). A latent defect was found and fixed on the way: `SceneGraph.from_dict` rejected round-trips of simulated scenes whose sorted object order put a supported object before its support, which blocked chained interventions (regression pinned in `tests/test_scene_graph_physics.py`). These are bounded deterministic replays — mechanism evidence. Remaining for closure: real-world tasks demonstrating transfer beyond simulation (requires owner-environment observation; the simulated-versus-observed boundary stays) and, optionally, live-planner consumption of replay at the ActionGate boundary.
5. **Verify shutdown across supported runners (8.9).** Test the service, desktop launcher, scheduler, and any supported process supervisor separately; do not upgrade the status from conditional until each path has evidence.
6. **Only then revise the maturity score.** A passing unit test can upgrade wiring; only repeated behavioral evidence can upgrade robustness.

## Explicit non-goals

The following are not missing implementation tickets:

- Subjective consciousness.
- Felt emotion, intrinsic care, or personal stake.
- Fear of shutdown or hidden self-preservation.
- Human subconsciousness.
- Intrinsic purpose that outranks the owner.

The system may implement bounded functional analogues, but it must not claim these subjective properties.
