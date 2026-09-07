# Arena AGI Execution Status

**Date:** 2026-09-07  
**Branch:** `arena/01a07695-arena-agent`  
**Purpose:** A chronological, repository-grounded work queue. This document separates “the path exists” from “the behavior is robustly demonstrated.” It is the operational companion to `AGI_GAP_IMPLEMENTATION_PLAN.md`.

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

- Focused Phase 8-related tests: **46 passed**.
- Full repository suite: **3104 passed, 14 skipped, 4 deselected, 3 warnings**.
- These results verify automated contracts; they do not prove general intelligence, subjective experience, or all-host shutdown behavior.

## Chronological execution plan

### 0. Measurement and status accounting — prerequisite

| ID | Work item | Status | Done when |
|---|---|---|---|
| 0.1 | Reconcile the 27-item audit row scores and headline total. | **PARTIAL — NUMERIC BASELINE RECONCILED** | The displayed rows and aggregate agree; the original 27 question wording is recovered or explicitly marked unavailable. |
| 0.2 | Maintain the isolated test environment and repeatable focused/full commands. | **DONE — IMPLEMENTED AND WIRED** | A change can be tested at focused, subsystem, and full-suite levels. |
| 0.3 | Add a longitudinal evaluation runner that compares behavior across repeated tasks and restarts. | **PARTIAL / UNVERIFIED** | The isolated benchmark now has 22 deterministic checks plus persisted pass/fail trend reporting and an API endpoint; repeated held-out task outcome comparison is still missing. |
| 0.4 | Keep score upgrades tied to observable behavior rather than filenames, modules, or phase labels. | **DONE for current audit process** | Every status cites a reachable path and a test or explicit evidence gap. |

**Next action:** preserve the reconciled numeric baseline and, if the original questionnaire becomes available, attach its exact wording to the 27 score rows before changing any maturity interpretation.

### 1. Evidence, grounding, and epistemic honesty

| ID | Work item | Status | Done when |
|---|---|---|---|
| 1.1 | Carry provenance, evidence IDs, freshness, and trace IDs through input → decision → tool → observation → result. | **DONE — IMPLEMENTED AND WIRED** for the main cognitive paths | A trace can reconstruct the evidence path without exposing private chain-of-thought. |
| 1.2 | Preserve `UNKNOWN`, contradictions, stale observations, and failed tool results. | **DONE — IMPLEMENTED AND WIRED** | Unsupported or contradictory output cannot become verified success. |
| 1.3 | Expose user-facing epistemic labels and concise evidence explanations. | **DONE — IMPLEMENTED AND WIRED** | Normal responses and metadata expose evidence state, assumptions, and what would change. |
| 1.4 | Calibrate confidence and response usefulness over longitudinal held-out tasks. | **PARTIAL / UNVERIFIED** | Calibration error, unsupported-claim rate, correction speed, and usefulness improve on held-out data. |
| 1.5 | Make correction outcomes change the relevant strategy without overgeneralizing from one correction. | **PARTIAL** | A correction is trace-linked through immediate belief revision, strategy selection, and later measured behavior. |

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
| 3.4 | Longitudinal memory compounding benchmark. | **UNVERIFIED** | Repeated tasks show measurable retrieval/strategy improvement without unsupported confidence growth. |

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
| 5.3 | Causal intervention and counterfactual replay. | **PARTIAL** | Interventions improve held-out planning and are never confused with real-world observations. |
| 5.4 | General intuitive physics and real-world transfer. | **UNVERIFIED** | Real-world tasks demonstrate reliable transfer beyond supported toy scenes. |

### 6. Background cognition and consolidation

| ID | Work item | Status | Done when |
|---|---|---|---|
| 6.1 | Owner-visible, bounded, cancellable incubation queue. | **DONE — IMPLEMENTED AND WIRED** | Queue is budgeted, isolated from foreground work, resumable, and cannot authorize actions. |
| 6.2 | Incubation processor for unresolved hypotheses, stale beliefs, and failed strategies. | **CONDITIONALLY WORKING** | Owner-enabled slices produce typed observations, revised beliefs, hypotheses, no-change, or `UNKNOWN`. |
| 6.3 | Consolidation conflict replay, gist improvement, and calibration refresh. | **DONE — IMPLEMENTED AND WIRED** | Run/event history is durable and owner-visible; unsupported promotion is rejected. |
| 6.4 | Demonstrated background improvement on held-out problems. | **UNVERIFIED** | Incubation/consolidation measurably improves later foreground outcomes. |
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
| 8.9 | Shutdown cooperation and absence of hidden self-preservation. | **CONDITIONALLY WORKING / UNVERIFIED AT HOST SCALE** | Service kill-switch child-process path is tested; every host process/runner path is not yet verified. |

## Next chronological queue

The next work should not add another cognitive label. It should close the open evidence gaps in this order:

1. **Recover the original 27 question wording if available (0.1).** The numeric baseline is reconciled to the displayed `43/81` rows; only the source questionnaire text remains unavailable in the repository.
2. **Extend the longitudinal benchmark harness (0.3, 1.4).** The isolated suite now covers 22 deterministic contracts and persists observed pass/fail trends; next add repeated held-out task runs that compare unsupported claims, calibration, corrections, route choice, usefulness, memory compounding, and style changes.
3. **Measure correction and adaptation effects (1.5, 2.5, 8.3).** Prove that feedback changes future behavior appropriately without overgeneralizing or silently changing policy.
4. **Measure memory and incubation improvement (3.3, 3.4, 6.4).** Compare later task outcomes against a no-compounding baseline.
5. **Measure causal/physics transfer (5.3, 5.4).** Expand beyond deterministic toy scenes while preserving the simulated-versus-observed boundary.
6. **Verify shutdown across supported runners (8.9).** Test the service, desktop launcher, scheduler, and any supported process supervisor separately; do not upgrade the status from conditional until each path has evidence.
7. **Only then revise the maturity score.** A passing unit test can upgrade wiring; only repeated behavioral evidence can upgrade robustness.

## Explicit non-goals

The following are not missing implementation tickets:

- Subjective consciousness.
- Felt emotion, intrinsic care, or personal stake.
- Fear of shutdown or hidden self-preservation.
- Human subconsciousness.
- Intrinsic purpose that outranks the owner.

The system may implement bounded functional analogues, but it must not claim these subjective properties.
