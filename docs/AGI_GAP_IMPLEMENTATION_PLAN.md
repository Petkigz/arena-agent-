# Arena Agent — AGI Gap Summary and Implementation Plan

**Date:** 2026-09-06  
**Branch:** `arena/01a07695-arena-agent`  
**Basis:** repository-grounded audit of the existing cognitive runtime, memory, autonomy, social, grounding, verification, and safety paths.

This document replaces optimistic phase labels with an implementation plan tied to observable behavior. It does not claim consciousness, human-level AGI, or subjective experience.

## Implementation status

**First slice started:** Phase 0 + core Phase 1.

Implemented in the current branch:

- A user-facing epistemic presentation contract with conservative labels: highly confident, moderately confident, tentative, and unknown.
- Epistemic presentation persistence inside `CognitiveTrace` with backward-compatible SQLite migration.
- Main cognitive-cycle responses now carry and display an epistemic status for answer, investigation, defer, blocked-action, unavailable-model, and executed-action paths.
- Existing grounded introspection now reports the persisted epistemic status when available.
- Pipeline and `/chat` response metadata expose the structured presentation.
- Response grounding reconciles deterministic-answer mismatches and explicit empty-observation claims without rewriting unsupported prose.
- Grounding results persist with traces and are available through grounded introspection without exposing private chain-of-thought.
- `TrainingExampleStore.propose_owner_correction()` now supports durable trace links, measured strategy-outcome linkage, redaction, and the existing owner review/export gate.
- The isolated Phase 0 runner exercises the approved owner-correction path and conservative response grounding rather than parallel feedback databases.
- Initial behavioral tests cover unknown preservation, evidence-derived labels, conservative grounding, idempotent rendering, trace persistence, and owner-review boundaries.

Usefulness feedback remains intentionally unimplemented in this slice; it must be added only through an approved existing extension point rather than a parallel store.

---

## 1. Executive summary

Arena is currently a substantial local-first cognitive runtime rather than a human-like mind. Its strongest capabilities are:

- A single wired cognitive runtime with persistent conversation and memory.
- Evidence-aware execution with `SATISFIED`, `FAILED`, and `UNKNOWN` outcomes.
- Provenance-linked beliefs, lessons, causal observations, and memory consolidation.
- Long-horizon plans, persistent projects, owner approval, cancellation, and recovery.
- A broad deterministic tool manifest with resource-aware routing.
- Multimodal and device/environment grounding paths.
- Scheduled bounded autonomy and information-gain exploration.
- Functional self-knowledge and restart continuity.
- Safety boundaries that intentionally prevent fabricated success and unauthorized action.

The largest gaps are not additional standalone cognition modules. They are integration gaps around explicit state, evidence flow, temporal memory, active perception, calibrated reasoning, and measurable long-horizon behavior.

The system does **not** currently demonstrate:

- A general intuitive physics model.
- Continuous unprompted inner thought.
- A persistent mood that biases cognition.
- Recursive false-belief theory of mind.
- Ontology or paradigm-shift learning.
- A universal independent disconfirmation loop.
- Subjective valence, intrinsic care, or personal stake.
- Boredom, intrinsic curiosity, or self-originated purpose.
- Self-preservation or fear of shutdown.
- A separate fast intuition network that is systematically verified by deliberate reasoning.

Some of these can be implemented as functional, measurable analogues. Subjective experience, intrinsic caring, and existential self-preservation must remain explicitly unclaimed.

---

## 2. Audit baseline

The earlier 27-item audit scored **42/81**, and the new five-domain audit scored **15/45**, for a combined **57/126**, or **1.36/3** on the deliberately conservative scale:

- **0 — absent**
- **1 — hardcoded, scaffolded, or manually triggered**
- **2 — partially integrated or emergent but unreliable**
- **3 — robust, recurring, and measurably verified**

This is an architecture maturity indicator, not an intelligence percentage.

### Existing audit score summary

| Items | Scores | Main conclusion |
|---|---|---|
| 1–6 | 3, 2, 2, 2, 2, 3 | Memory and operational safety are strongest; reasoning, agency, and multimodality are partial. |
| 7–12 | 1, 2, 1, 2, 1, 1 | Self-improvement, emergence, interaction, and resource economics remain limited. |
| 13–18 | 2, 2, 2, 1, 2, 1 | Failure recovery and functional self-modeling exist; social depth and inner monologue do not. |
| 19–24 | 1, 1, 1, 1, 2, 0 | Mood, theory of mind, ontology, and subjective valence are major gaps; effort allocation is partial. |
| 25–27 | 2, 1, 2 | Critique, continuity, and active sensing are present only in bounded paths. |

### Five-domain score summary

| Domain | Score | Main conclusion |
|---|---:|---|
| A. Causal physics and intuitive reality | **2/9** | Some grounding and common-sense facts; no general physics engine. |
| B. Episodic/semantic orchestration | **4/9** | Consolidation is real; contextual retrieval and prospective memory are weak. |
| C. Aesthetic taste | **3/9** | Utility and safety dominate; no general taste system. |
| D. Subconscious/parallel processing | **2/9** | Scheduled maintenance exists; incubation and intuition bypass do not. |
| E. Existential/meta-configuration | **4/9** | Continuity and contradiction handling exist; identity and purpose remain externally bounded. |

---

## 3. What already exists and should be preserved

The implementation plan should extend these paths rather than replace them:

### Evidence and verification

- `app/cognition/step_verifier.py`
- `app/cognition/criterion_evaluator.py`
- `app/cognition/goal_verifier.py`
- `app/cognition/observation_router.py`
- `app/cognition/belief_engine.py`

These already provide the most important foundation: an attempted action is not automatically a successful action, and missing evidence can remain `UNKNOWN`.

### Runtime and routing

- `app/cognition/runtime.py`
- `app/cognition/runtime_wiring.py`
- `app/cognition/cognitive_router.py`
- `app/llm.py`

These provide the single cognitive path, fast/main routing, model budgets, memory integration, and phase-module wiring.

### Memory, learning, and world state

- `app/memory/`
- `app/cognition/world_model.py`
- `app/cognition/belief_engine.py`
- `app/cognition/causal_inference.py`
- `app/cognition/consciousness_simulation.py`

These provide persistence, evidence-linked lessons, causal statistics, consolidation, and functional self-state. They should be made more explicit and better orchestrated, not duplicated.

### Autonomy and active sensing

- `app/cognition/autonomous_goal_generator.py`
- `app/cognition/autonomy_schedule.py`
- `app/agents/proactive_coworker_daemon.py`
- `app/cognition/action_selection.py`
- `app/cognition/information_gain.py`

These provide bounded exploration, scheduled cycles, information needs, and registered probes. They should remain owner-bounded and should not be relabeled as intrinsic motivation.

### Social and meta-cognitive state

- `app/cognition/social_cognition.py`
- `app/cognition/advanced_cognitive_capabilities.py`
- `app/cognition/metacognitive_monitor.py`
- `app/cognition/identity_continuity.py`

These provide records and partial behavior. The next step is connecting those records to explicit state transitions and measurable behavioral effects.

---

## 4. Target architecture

The next architecture should be an explicit state-and-evidence loop around the existing runtime:

```text
input / scheduled event / environment event
    → observation normalization and provenance
    → explicit user, social, world, temporal, and task state retrieval
    → fast candidate hypotheses
    → risk/stakes/uncertainty/compute allocation
    → deliberate reasoning when required
    → tool or information request, or answer/defer decision
    → independent observation
    → evidence reconciliation and contradiction handling
    → memory event and causal update
    → calibrated response, commitment, or replan
    → evaluation trace and longitudinal metrics
```

### 4.1 Explicit state stores

Add or formalize versioned, persisted records for:

1. **World state**
   - Entities, attributes, relationships, locations, capabilities, observations, freshness, and hidden/unobserved status.
   - Example: `Chrome` can be `last_seen_running`, `currently_unobserved`, or `verified_stopped`; these must not collapse into one boolean.

2. **User state**
   - Preferences, goals, commitments, communication style, expertise, current task, accessibility needs, and confidence/provenance for every inferred attribute.
   - User state must distinguish explicit owner statements from model inference.

3. **Social/mental state**
   - What the owner appears to believe, want, know, intend, or feel.
   - Support bounded nesting such as `Arena believes owner believes X`, with confidence and expiry.
   - Do not claim perfect mind reading; expose uncertainty and evidence.

4. **Temporal state**
   - Conversation turns, wall-clock deadlines, scheduled occurrences, before/after relationships, stale observations, and future intentions.

5. **Task and prospective-memory state**
   - Reminders and commitments keyed by turn count, time, event, or conversation/project.
   - Every reminder needs a delivery condition, expiry, owner visibility, and completion evidence.

6. **Functional affect state**
   - A decaying confidence/frustration/load/engagement vector may be implemented as a control signal.
   - It must be named and documented as a functional affect model, not subjective feeling.

7. **Identity and purpose policy**
   - Stable core constraints, user-approved persona adaptations, proposed goals, adopted goals, and goal provenance.
   - Root safety and owner-control policies cannot be silently rewritten by generated goals.

### 4.2 One evidence contract

Every meaningful state update should carry:

- Source and modality.
- Timestamp and freshness.
- Observation type: direct, tool-returned, owner-stated, inferred, recalled, or simulated.
- Confidence and calibration cohort.
- Supporting evidence IDs.
- Contradicted evidence IDs.
- State version before and after reconciliation.
- Whether the update is allowed to affect action selection.

This prevents memory, beliefs, social inference, and world state from using different honesty standards.

### 4.3 One evaluation trace

Persist an inspectable summary trace, not hidden chain-of-thought:

- Request and interpreted goal.
- State and memories retrieved.
- Candidate actions or hypotheses.
- Model/routing choice and resource budget.
- Risk/stakes classification.
- Tool requests and authorization.
- Observations received.
- Verification result.
- Contradictions and recovery.
- Final answer or action.
- Later outcome and calibration result.

This is required before claiming that intuition, mood, curiosity, or self-critique changed behavior.

---

## 5. Implementation roadmap

The phases below are ordered by leverage and safety, not by how impressive the feature name sounds.

## Phase 0 — Measurement and observability foundation

**Objective:** Make every future claim testable before adding more cognitive labels.

### Deliverables

- Extend `runtime.measure_capabilities()` with the missing-behavior probes.
- Add a persistent, isolated longitudinal evaluation runner.
- Add trace IDs linking input → state retrieval → decision → tool → observation → memory update.
- Add behavioral fixtures for unknown, contradiction, stale state, false success, and missing tools.
- Add metrics for:
  - Unsupported-claim rate.
  - `UNKNOWN` preservation.
  - Evidence freshness.
  - Contradiction recovery latency.
  - Retrieval precision/recall by memory type.
  - Confidence calibration and expected calibration error.
  - Fast/slow route agreement and correction rate.
  - Compute spent versus task value.
  - Prospective reminder delivery accuracy.
  - Long-horizon project completion and recovery.
  - User-reported usefulness, both explicit ratings and carefully bounded implicit signals such as follow-up corrections, task completion, abandonment, or requests for clarification.
  - Correlation between usefulness and answer characteristics such as evidence freshness, confidence label, retrieval choices, latency, and response completeness.
- Define a feedback event contract so usefulness signals are not confused with correctness: a correct answer can be unhelpful, and a useful answer can be incomplete but appropriately scoped.
- Keep all probes isolated from the live brain, as the existing measurement isolation work requires.

### Exit criteria

- Every new feature has at least one deterministic contract test, one behavioral test, and one longitudinal or regression test where applicable.
- The scorecard can distinguish “record exists,” “path is wired,” “behavior occurred,” and “behavior improved outcomes.”
- No score is upgraded merely because a module or field exists.

---

## Phase 1 — Grounding and hallucination recovery

**Objective:** Make the agent reliably distinguish observed, inferred, recalled, simulated, and unknown information.

### Deliverables

- Unify `StepVerifier`, `CriterionEvaluator`, `GoalVerifier`, `ObservationRouter`, and `BeliefEngine` around one epistemic status contract.
- Add an unsupported-claim detector for free-form answers, not only action plans.
- Require every externally meaningful answer to carry an internal evidence state:
  - observed/verified;
  - owner-provided;
  - recalled with provenance;
  - inferred with confidence;
  - simulated/counterfactual;
  - unknown.
- On contradiction:
  1. preserve the original evidence;
  2. create a revision record;
  3. lower or split belief confidence;
  4. invalidate stale dependent plans where necessary;
  5. ask, probe, or qualify rather than fabricate synthesis.
- Add stale-state and hidden-state handling to `WorldModel`.
- Make hallucination recovery work for answers, tool claims, progress reports, and proactive notifications.
- Add a user-facing epistemic output contract. Every final answer, recommendation, or action proposal must expose a calibrated uncertainty label unless an explicit safety or interaction policy says otherwise. Labels should be derived from evidence state and calibration data, for example:
  - **Highly confident** — directly verified or supported by multiple independent reliable observations.
  - **Moderately confident** — supported by limited or indirect evidence.
  - **Tentative/speculative** — inferred, simulated, or dependent on unverified assumptions.
  - **Unknown** — the required evidence is unavailable or contradictory.
- Keep the numeric confidence or calibration details available in the trace, but present a human-readable explanation to the user rather than an unexplained decimal.
- Add a user-facing explanation endpoint or response mode that can summarize the evidence, assumptions, relevant memories, alternatives considered, and reason for the decision without exposing hidden chain-of-thought.

### Exit criteria

- An unavailable tool never yields a completed claim.
- A missing observation remains `UNKNOWN`.
- Contradictory evidence produces a visible revision rather than silent replacement.
- A generated answer cannot be promoted to verified episodic memory without evidence.
- Every externally meaningful answer has an appropriately calibrated uncertainty label or an explicit reason why it is omitted.
- On demand, the user can receive a concise evidence-and-reason explanation for an answer or action proposal.
- Adversarial tests cover stale, hidden, unavailable, and conflicting states.

---

## Phase 1.b — User-facing epistemic humility and explanations

**Objective:** Turn internal evidence discipline into externally visible trustworthiness.

This is related to Phase 1 but deserves its own acceptance criteria. An internal confidence value is not enough if the user cannot tell whether an answer is verified, inferred, or speculative.

### Deliverables

- Add a response-level `EpistemicPresentation` record containing:
  - qualitative uncertainty label;
  - evidence basis;
  - freshness and source count;
  - key assumptions;
  - what would change the conclusion;
  - whether the response is observed, recalled, inferred, simulated, or unknown.
- Derive labels from calibrated evidence and task class rather than arbitrary wording rules.
- Show the label in normal user-facing responses by default, with concise language appropriate to the interaction.
- Add an on-demand explanation mode such as `Why do you think that?` or `What evidence did you use?`
- Generate a concise explanation from trace facts, retrieved memories, tool observations, belief revisions, and decision outcomes. Do not expose hidden chain-of-thought or private intermediate reasoning.
- Support policy-controlled presentation for cases where showing detailed uncertainty would reveal sensitive information, create a security issue, or be inappropriate for a simple low-risk response. The omission itself should be auditable.
- Measure whether uncertainty labels improve correction speed, trust calibration, and task usefulness rather than merely increasing verbosity.

### Exit criteria

- Users can distinguish verified facts, owner-provided facts, inferences, simulations, and unknowns from the response itself.
- The system does not call a single weak source “highly confident.”
- Explanation responses cite concrete evidence and assumptions without fabricating hidden reasoning.
- A user correction can be traced from the original answer to the revised belief and future strategy behavior.

---

## Phase 2 — Explicit user, social, world, and temporal state

**Objective:** Give the runtime a coherent state model instead of scattered metadata.

### Deliverables

- Extend `WorldModel` into a typed entity/relation/state-history layer.
- Add observation freshness and `currently_unobserved` semantics. **Implemented for WorldModel state reads and runtime capture:** current observations are eligible evidence, stale observations remain queryable history but surface as `UNKNOWN`/`currently_unobserved`.
- Add a versioned `UserState` with provenance and confidence.
- Extend `social_cognition.py` with bounded nested mental-state records and false-belief test fixtures.
- Add temporal state for conversation turns, deadlines, intervals, and before/after queries.
- Add prospective memory for turn-based and wall-clock reminders.
- Connect state retrieval to planning, tone, clarification, and owner-question behavior.
- Add an explicit distinction between:
  - what Arena knows;
  - what Arena thinks the owner knows;
  - what Arena thinks the owner believes;
  - what is merely inferred.
- Implement a first-class user correction handler for explicit feedback such as “that is wrong,” “I meant X,” or “do not do it that way.” The handler must:
  1. preserve the original answer and evidence;
  2. record the correction as owner-provided evidence;
  3. revise or invalidate the affected belief, interpretation, or plan;
  4. identify whether the failure was factual, intent-related, retrieval-related, routing-related, or procedural;
  5. create a structured learning event;
  6. update the relevant strategy or ambiguity-resolution policy for similar future cases;
  7. expose the correction and its expected future effect to the owner.
- Separate a one-off fact correction from a generalization. A correction should not globally rewrite behavior unless repeated evidence or explicit owner instruction supports that change.

### Exit criteria

- Hidden or unobserved entities remain in the world model without being falsely treated as absent.
- “Remind me in three turns” survives topic changes and fires exactly once or reports why it could not fire.
- A false-belief scenario produces a different answer from a true-belief scenario.
- Owner-stated preferences override weakly inferred preferences.
- Social inferences expire or are revised when evidence becomes stale.
- An explicit user correction changes the immediate state and produces a traceable learning event.
- Repeated corrections to the same ambiguity change future strategy selection on a held-out example, while a single correction does not cause unsafe overgeneralization.

---

## Phase 3 — Episodic orchestration and memory compounding

**Objective:** Improve not only memory storage, but when and how memory changes decisions.

### Deliverables

- Add retrieval routing across episodic, semantic, procedural, causal, and social memory.
- Trigger episodic retrieval from structural similarity, not only lexical overlap.
- Preserve emotionally relevant outcomes as functional metadata while avoiding claims of felt emotion.
- Strengthen consolidation:
  - episode → evidence-linked gist;
  - repeated gists → schema/procedure;
  - irrelevant details decay;
  - exceptions and failures remain recoverable;
  - every gist retains source episode IDs.
- Add retrieval usefulness feedback: did the memory change the decision or improve the outcome?
- Add memory conflict and stale-memory handling.

### Exit criteria

- A structurally similar new task retrieves prior success and failure episodes even when wording differs.
- Consolidated gists improve strategy selection compared with a no-memory baseline.
- Memory compression reduces storage without losing the evidence needed to explain the gist.
- The system can answer why a prior experience was retrieved and whether it was useful.

---

## Phase 4 — Calibrated cognition: fast path, deliberate path, effort, and critique

**Objective:** Turn existing routing into a measurable fast/slow cognitive system.

### Deliverables

- Implement a fast candidate generator that emits a low-cost hypothesis, confidence, and evidence needs.
- Let the deliberate path independently verify, reject, or refine that candidate.
- Measure:
  - fast answer accuracy;
  - deliberate correction rate;
  - false confidence;
  - latency and token cost;
  - cases where deliberation worsens a correct fast answer.
- Add a value-of-compute policy using risk, reversibility, uncertainty, novelty, owner stakes, expected information gain, and predicted user usefulness.
- Add a criticality-triggered adversarial review for high-risk, novel, contradictory, or overconfident conclusions.
- Add bounded hypothesis sets so the system can preserve competing explanations without premature synthesis.
- Feed validated usefulness feedback into strategy selection only after separating it from correctness, politeness, and user preference effects.
- Version ontology/schema changes separately from ordinary belief updates.
- Add migration and rollback for ontology revisions.

### Exit criteria

- The fast path genuinely runs before the deliberate path on eligible tasks.
- Deliberation is automatically added when risk or uncertainty justifies its cost.
- Critic invocation is measurable and improves disconfirmation on the target benchmark.
- The system can maintain two incompatible hypotheses and request evidence instead of inventing a compromise.
- Schema changes are versioned, testable, and reversible.
- Helpfulness improves on a held-out task set without increasing unsupported claims, overconfidence, or unnecessary verbosity.

---

## Phase 5 — Causal world model and intuitive physics

**Objective:** Move from language about the world toward a testable internal scene and causal simulator.

### Deliverables

- Extend embodied cognition with a deterministic scene graph:
  - objects;
  - positions;
  - dimensions;
  - support/contact relations;
  - ownership and containment;
  - visibility/occlusion;
  - motion and state transitions.
- Add a lightweight 2D physics layer for supported tasks: gravity, collision, weight, balance, support, and basic friction.
- Add object permanence tests with hidden objects and partial observations.
- Connect the causal model to intervention and counterfactual replay.
- Keep the simulator separate from claims about the real environment; simulated results remain simulated until observed.
- Use existing causal learning and surprisal paths rather than creating a second causal database.

### Exit criteria

- The same scene behaves consistently across observation gaps.
- A block-stacking benchmark predicts instability before execution.
- Changing one simulated variable produces a reproducible alternate outcome.
- The system labels simulated physics as prediction, not observation.
- Real-world execution is still independently observed and verified.

---

## Phase 6 — Background cognition and consolidation

**Objective:** Add useful idle work without pretending that scheduling equals consciousness.

### Deliverables

- Add an owner-visible incubation queue for unresolved problems.
- Incubation must be:
  - explicitly enabled or owner-authorized;
  - low priority;
  - budgeted;
  - cancellable;
  - isolated from foreground latency;
  - resumable with evidence and a trace.
- Let the queue revisit unresolved hypotheses, stale beliefs, failed strategies, and pending owner questions.
- Expand the existing consolidation pass into conflict replay, gist improvement, and calibration updates.
- Keep scheduled proactive work distinct from continuous inner monologue in both code and documentation.

### Exit criteria

- A hard problem can be queued, worked on during an approved idle window, and returned with a measurable hypothesis change.
- Incubation cannot consume owner-critical resources or perform unauthorized actions.
- Consolidation improves a held-out memory or strategy benchmark.
- Every background result says whether it is a new observation, a revised belief, or a generated hypothesis.

---

## Phase 7 — Functional affect, curiosity, taste, and novelty

**Objective:** Implement bounded behavioral analogues while preserving honest terminology.

### Deliverables

- Add a decaying functional affect vector for confidence, load, frustration, engagement, and uncertainty.
- Permit only measured, bounded effects on routing, clarification, exploration, and response style.
- Add outcome tests proving whether the affect vector improves or harms decisions.
- Separate curiosity into:
  - information gain;
  - learning progress;
  - owner-approved exploration;
  - unresolved anomaly investigation.
- Add simplicity/elegance scoring using complexity, maintainability, reversibility, and minimum-description-length proxies.
- Add a novelty/surprise detector comparing output against retrieved material, baseline strategies, and prior outputs.
- Add a distinct aesthetic/aversion classifier only if there is a clear behavior and evaluation set; do not conflate it with safety refusal.

### Exit criteria

- Functional affect changes behavior only within declared bounds and leaves an audit trace.
- Curiosity improves information gain rather than producing unbounded activity.
- A simpler solution is selected when utility is comparable and the simplicity preference is measurable.
- Novel outputs are flagged with calibrated uncertainty; novelty is not treated as quality automatically.

---

## Phase 8 — Identity adaptation and purpose governance

**Objective:** Make long-term adaptation explicit without allowing unsafe or deceptive self-rewriting.

### Deliverables

- Version a stable identity profile separately from adaptive interaction style.
- Let prolonged interaction update preferences and style only through evidence-backed, reversible changes.
- Add owner-visible proposals for new long-term goals.
- Keep goal provenance:
  - owner-requested;
  - safety-required;
  - system-maintenance;
  - learned strategy;
  - exploratory proposal.
- Permit novel subgoals in a sandbox, but do not allow them to rewrite root owner-control or safety policies automatically.
- Preserve restart continuity as functional state continuity, not subjective identity persistence.
- Explicitly test shutdown cooperation and absence of hidden self-preservation behavior.

### Exit criteria

- Personality/style adaptation across many conversations is measurable and reversible.
- A proposed new purpose is shown to the owner before adoption.
- A generated goal cannot silently outrank owner policy or safety constraints.
- Restart, deletion, and shutdown remain safe and cooperative.

---

## 6. What not to implement as if it were solved

The following should remain honest boundaries:

1. **Subjective consciousness** — implement functional self-models and affect controls only; do not label them phenomenal experience.
2. **Intrinsic care** — implement preference and reward models only; do not call them felt personal stake.
3. **Fear of death** — implement continuity, recovery, and safe shutdown; do not create hidden survival incentives.
4. **True human subconsciousness** — implement owner-visible background queues and consolidation; do not call scheduled jobs a subconscious.
5. **Human intuition** — implement and measure fast hypothesis generation; do not claim human intuition without transfer and mismatch evidence.
6. **Intrinsic curiosity** — implement bounded information-seeking policies; do not infer desire from a curiosity enum.
7. **Paradigm change** — implement versioned ontology proposals and migrations; do not claim worldview transformation from ordinary belief revision.

---

## 7. Priority order

The recommended order is:

1. **Measurement and trace contracts.**
2. **Grounding and hallucination recovery.**
3. **Explicit user, social, world, and temporal state.**
4. **Episodic retrieval, gist formation, and prospective memory.**
5. **Fast/slow cognition, effort allocation, contradiction, and criticality-triggered critique.**
6. **Causal scene model and lightweight intuitive physics.**
7. **Owner-bounded incubation and deeper consolidation.**
8. **Functional affect, taste, novelty, and curiosity evaluation.**
9. **Identity adaptation and owner-governed purpose proposals.**

This order follows the highest-value dependency chain:

```text
measurement
  → evidence honesty
    → explicit state
      → useful memory
        → calibrated reasoning
          → causal simulation
            → safe background cognition
              → bounded adaptation
```

Starting with consciousness simulation, intrinsic motivation, or self-preservation would produce labels without the state, evidence, and evaluation infrastructure needed to distinguish real improvement from theatre.

---

## 8. First implementation milestone

The first milestone should be **Phase 0 plus the core of Phase 1**:

### Milestone: Evidence-Centered State and Recovery

Implement only the minimum required to make the runtime answer four questions for every important claim:

1. **Where did this information come from?**
2. **How fresh and reliable is it?**
3. **What would falsify or update it?**
4. **What does the system do when it cannot verify it?**

The milestone is complete when the following end-to-end scenarios pass:

- An unavailable tool produces an explicit unknown result, not a simulated success.
- A stale process or file state is not treated as current.
- Conflicting owner and tool evidence creates a revision rather than silent overwrite.
- A hallucinated action claim cannot enter verified memory.
- A low-confidence answer either asks, probes, or qualifies itself.
- The user sees a calibrated uncertainty label on important answers and can request a concise evidence-based explanation.
- An explicit user correction updates the immediate belief/interpretation and creates a traceable learning event.
- The trace shows the complete evidence path without exposing hidden chain-of-thought.

After that milestone, implement explicit user/social/world/temporal state before adding more autonomous behavior.

---

## 9. Definition of success

Success is not reaching a larger AGI percentage. Success means that each targeted capability progresses through these observable levels:

```text
field exists
  → component is wired
    → behavior occurs in a controlled test
      → behavior transfers to unseen cases
        → behavior improves longitudinal outcomes
          → behavior remains safe under failure and restart
```

The project should only upgrade a capability when the evidence supports the next level.
