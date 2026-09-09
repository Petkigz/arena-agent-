# Phase 0 — AGI Architecture Map (Beanie Roadmap)

**Date:** 2026-09-08 · **Baseline:** commit `215a5c3` on `arena/01a0813a-arena-agent`
**Governing doc:** [`AGI_ROADMAP.md`](AGI_ROADMAP.md) · **Ledger:** [`AGI_ARCHITECTURE_MAP_FILES.csv`](AGI_ARCHITECTURE_MAP_FILES.csv)
**Generator:** `python scripts/map_agi_architecture.py` (re-runnable, like `audit_dead_code.py`)

This is the Phase-0 freeze deliverable: every production module classified into the
AGI layer model with a disposition, the cognitive-authority question answered, and
the gap between "what the roadmap assumes is missing" and "what actually exists"
measured against the real tree. **Nothing was moved, renamed, or deleted.**

Integrity evidence captured at baseline (this sandbox): full Python suite
**3,353 passed, 19 skipped, 0 failed**; `app.server:app` builds **367 HTTP +
3 WebSocket routes**; all Python parses clean; the manifest carries **184
capabilities** across 85 tool modules. The map covers all production Python
modules with **0 unclassified** (354 at freeze; 376 after the `app/mind/`
package grew through Phases 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 — the target architecture itself, all KEEP).

---

## 1. Disposition legend

| Disposition | Meaning | Count |
|---|---|---|
| **KEEP** | Already fits the target architecture | 252 |
| **INTEGRATE** | Useful; must become part of the unified Mind | 67 |
| **MERGE** | Duplicate/overlapping intelligence (cluster id in CSV) | 23 |
| **DEMOTE** | Useful capability/loop; must not make cognitive decisions | 6 |
| **LEGACY** | Preserve temporarily; stop building on it | 6 |
| **REPLACE** | Architecture fundamentally conflicts | **0** |
| **MISSING** | Required concept has no file (§6) | 11 concepts |

Zero REPLACE is a real finding: the previous sessions did not build anything that
fundamentally conflicts with the AGI target. The drift was **organizational**
(many partial intelligences, no single mind), not **directional**.

Layer distribution (top level): mind 69 · capabilities 62 · communication 58 ·
infrastructure 31 · models 23 · learning 22 · evaluation 22 · embodiment 20 ·
owner-authority 16 · memory 16 · perception 15.

---

## 2. The cognitive authority question — answered

The roadmap asks: *"exactly one place where 'I am Beanie' is represented — not
master_agent, CognitiveRuntime, CoworkerBrain, self_evolving_agent, and three
planners all independently acting like the brain."*

What the tree actually contains (cluster `AUTHORITY` in the CSV):

| Component | What it really is | Phase-0 verdict |
|---|---|---|
| `app/cognition/runtime.py` (5,337 lines) | The singleton composition root — every request path already funnels here. **De-facto brain.** | INTEGRATE — becomes the *interior* of BeanieMind. Not replaced; promoted and given an identity. |
| `app/memory/coworker_brain.py` | A persona **prompt string**, no state. The only place a "person" exists in the backend. | INTEGRATE — the seed of Beanie's identity record; must become real state, not a string. |
| `app/agents/master_agent.py` (1,104 lines) | Action executor — the **hands**. | DEMOTE — named/used strictly as execution, never as authority. |
| `app/agents/self_evolving_agent.py` | Self-improvement loop. | INTEGRATE into learning/self-improvement (Phase 20 material). |
| `app/cognition/cognitive_pipeline.py`, `pipeline.py` | Compat shells delegating to the runtime. | LEGACY — stop building on them. |
| "I am Beanie" | **Does not exist in the backend.** "Beanie" appears only in UI code (frontend BeaniePage/orb, desktop theme states, Android Beanie components). | MISSING #1 — the single most important gap. ✅ **Resolved 2026-09-08 (Phase 1):** `app/mind/identity.py` persists it; `app/mind/beanie_mind.py` is the one door. |

**Verdict:** there is exactly one functional brain today (`CognitiveRuntime`),
which is good news — the Phase-1 job is not a merger of rival brains, it is
**giving the existing brain an identity, a state object, and one named door**
(`BeanieMind.process(...)`).

---

## 3. What already exists vs. what the roadmap assumes missing

Several phases are written as greenfield builds. They are not — partial, wired
versions exist. The map's job is to prevent a second implementation of what is
already there (the failure mode that produced the dead code).

| Roadmap phase | Assumed missing? | Reality in the tree |
|---|---|---|
| P3 World Model | "biggest missing component" | **Partial — 9 modules** (cluster WORLD): `world_model.py` (783 lines, persistent), `world_ingest`, `observation_router` (1,074 lines of host-state grounding), `environment_state/grounding`, `os_grounding`, `scene_graph`, `browser_grounding`. **But:** it is used *after* action (verification probes), not *before* action (world-first reasoning). Missing piece is the role, not the storage. ✅ **2026-09-08:** `app/mind/world_facade.py` adds the pre-action half (ontology + `understand`); cycle consumption remains the Phase-2 step. |
| P4 Self Model | "huge difference…" | **Partial — 8 modules** (cluster SELF): `self_model.py`, `self_knowledge.py`, `identity_continuity.py`, `identity_adaptation.py` (1,066 lines), `self_recovery.py`, `metacognitive_monitor.py` (903 lines), `consciousness_simulation.py`, `api/self_awareness.py`. ✅ **2026-09-08:** `app/mind/self_facade.py` ships the unified "knowledge: unknown / confidence: 0.08 / possible_actions" internal-state surface (the roadmap's acceptance example, verbatim). |
| P5 Unified Memory | "not chat history" | **Partial — 6 modules** (cluster MEMORY): `cognition/memory.py` already implements episodic + semantic + procedural in one store; plus working, prospective, associative, analogical memories and `semantic_rag`. ✅ **2026-09-08:** `app/mind/memory_facade.py` ships the single facade over all eight kinds incl. NEW social memory and meta-memory; autobiographical remains the milestone seed (M4 partial). |
| P16 Owner model | greenfield | **Exists:** `owner_model.py` (counted patterns from owner decisions), `user_state.py`, `human_nature_engine.py`. INTEGRATE, don't rebuild. |
| P9 Curiosity | greenfield | **Exists:** `learning_progress.py`, `information_gain.py`, `experiment_engine.py`, autonomous-goal family. INTEGRATE into one UNKNOWN→investigate loop. |
| P10 Reasoning/Imagination | greenfield | **Exists:** `counterfactual_simulator`, `prediction_engine`, `hypotheses`, `incubation_queue`, `scene_causal`. Prediction-vs-reality comparison is the missing connective tissue. |
| P14 Attention | greenfield | **Seed only:** `attention_manager.py` is 43 lines. Real inputs exist though: `background_observer` + `event_prioritizer` (charter §5④ live) + `anticipation_engine`. This is the largest genuine build inside "existing" territory. |
| P19 Reflection | greenfield | **Duplicated — 3 engines** (cluster REFLECTION): `verified_reflection`, `self_reflection_engine`, `memory/reflection_engine` + `memory_learning`. MERGE to one. |
| P12 OS abstraction | greenfield | **Seed exists:** `os_control_planner.py` ("one planner for every OS action, every platform") + the OS cluster (17 modules incl. ADB). The concept-verb layer (open/copy/navigate/…) is the new part. |
| P24 Generalization eval | greenfield | **Regression-style only:** `intelligence_benchmark.py` (1,862 lines, isolated longitudinal) + `phase0/1_task_evaluations`. Tasks A–G do not exist (§6 M9). |

---

## 4. Merge clusters (duplicate intelligence)

From the CSV `cluster` column — each cluster must become **one** organ of the
Mind. Order below is the suggested Phase-1..5 working order, cheapest first:

| Cluster | Files | What consolidates |
|---|---|---|
| `BELIEF` | `belief_engine.py` + `beliefs.py` (+ `hypotheses.py`) | one belief/hypothesis substrate with evidence + revision |
| `LOOP` | `reasoning_cycle.py` + `reasoning_loop.py` | one observe→reason→investigate loop inside the Mind |
| `REFLECTION` | `verified_reflection` + `self_reflection_engine` + `memory/reflection_engine` (+ `memory_learning`) | one post-experience reflection feeding memory |
| `MEMORY` | `memory.py` (facade nucleus) + associative/analogical/semantic_rag/working/prospective | one unified memory with typed stores (Phase 5) |
| `WORLD` | `environment_state` + `environment_grounding` + `embodied_boundary` (+ world_model core) | one environment/world surface |
| `OWNER` | `user_state.py` + `owner_model.py` (+ `human_nature_engine`) | one owner/relationship model |
| `SELF` | the 5 identity/self modules (+ metacognitive_monitor, consciousness_simulation) | one self model (Phase 4) |
| `PLANNERS` | action_planner, strategic_planning, planning_patterns, goal_decomposer/replanner, project_manager/scheduler | one planning faculty called by the Mind (decision layer) |
| `SENSES` | 7 tools currently under `app/tools/` (screen_capture, camera_capture, ocr_reader, object_detector, vision_analyzer, vlm_analyzer, prosody_analyzer) | relocate conceptually to **perception** — they are senses, not capabilities |
| `STATE` | `cognitive_state.py` + `blackboard.py` | the first two rooms of `BeanieState` |
| `ENTRIES` | `backend/message_router.py` + `backend/voice/service.py` (+ REST `/chat`) | all become thin adapters into `BeanieMind.process` |
| `TOOL-FIRST` | `tool_matcher.py` | **demotion, not merge:** manifest-first routing is exactly the Phase-2 anti-pattern; it survives as capability *resolution*, invoked only after world reasoning |
| `OS` | 17 embodiment modules | already coherent; receives the Phase-12 concept-verb layer on top |

---

## 5. Entry points that must converge (Phase 1 deliverable)

Today the mind is entered through at least five doors with five shapes:

1. **WS text** — `backend/message_router.py` → `CognitiveRuntime.process_cognitive_cycle`
2. **Voice** — `backend/voice/service.py` + `orchestrator.py` → runtime
3. **REST** — `app/main.py` `/chat` → runtime
4. **Observation** — `background_observer`/`event_prioritizer` → *record-only* (never triggers thought)
5. **Autonomous cycle** — `periodic_autonomous_cycle` → runtime on a timer

`BeanieMind.process(input, modality)` must absorb 1–3 directly and decide the
cognitive relevance of 4–5 through the attention system. The server
(`app/server.py`) and the invariant "one brain, always" stay untouched —
BeanieMind *is* the runtime plus identity plus state, not a second runtime.

---

## 6. MISSING ledger — concepts with no file (the actual build list)

> **Status 2026-09-08:** M1 (identity), M2 (BeanieState), M3 (meta-memory),
> M5 (social memory), **M6 (world-first reasoning path)** and **M7
> (demonstration learning)** are LIVE in `app/mind/` (Phases 1, 2, 3, 4, 5,
> 6, 7): the door assembles a world → self → memory brief before capability
> identification, every experience passes through one learning loop, and the
> owner teaches procedures by conversation ("watch this" → steps → proposal →
> confirmed verdict). **Phase 6 is also
> LIVE** though it had no M-row of its own: `app/mind/learning_loop.py` is the
> ONE general learning loop every experience passes through — the door
> auto-submits verified/unverified cycle outcomes and owner corrections; it
> feeds M11's spirit (failures become data) without claiming M11 resolved.
> M4 is partial (milestone seed; no narrative layer). Remaining build list:
> M4-completion, M9. (M8 — attention significance — is LIVE with Phase 14:
> `app/mind/attention.py`; M10 — OS concept-verb abstraction — is LIVE with
> Phase 12: `app/mind/os_concepts.py`; M11 — the prediction↔reality loop —
> is LIVE with Phase 10: `app/mind/imagination.py` connects
> `prediction_engine.py` to the learning loop, so failures become training
> data.)

| # | Concept | Roadmap phase | Nearest existing fragment |
|---|---|---|---|
| M1 | **Beanie identity** — "I am Beanie" as backend state (name, history, values absorbed from owner) | P1, P17 | `coworker_brain.py` persona string |
| M2 | **BeanieState** — unified internal state object (self/owner/world/working_memory/beliefs/hypotheses/plans/predictions/uncertainty/attention) | P1 | `cognitive_state.py`, `blackboard.py` |
| M3 | **Meta-memory** — "I remember doing this" vs "I think I know but never did" | P5 | `self_knowledge.py` (closest) |
| M4 | **Autobiographical memory** — Beanie's own development history | P5, P17 | `identity_continuity.py` (restart checks only) |
| M5 | **Social memory store** — people/relationships as first-class memory type | P5, P16 | `social_cognition.py` engine, no store |
| M6 | **World-first reasoning path** — goal → world understanding → memory → hypotheses → strategy → capabilities | P2 | none — `tool_matcher` is the inverse |
| M7 | ~~**Demonstration learning**~~ ✅ LIVE 2026-09-08 — `app/mind/teaching.py`: "Beanie, watch this" → steps → her proposal → owner's "yes" → generalized procedure (Phase 7; integrates `skill_teaching_engine.py` as the durable store) | P7 | ~~`skill_teaching_engine.py` (form-driven)~~ |
| M8 | ~~**Attention significance system**~~ ✅ LIVE 2026-09-08 — `app/mind/attention.py`: roadmap ladder (current task / owner speaking / important change / anomaly / unfinished goal / learned curiosity / background) arbitrated from evidence on the perception record; repeats demoted; one open unknown surfaced when quiet; popup-over-task advisory (Phase 14; the in-cycle `attention_manager.py` focus tracker stays wired as the runtime fallback) | P13, P14 | ~~`attention_manager.py` (43 lines) + observer/prioritizer feeds~~ |
| M9 | **Generalization evaluation** — tasks A–G (teach-once-adapt, tutorial-transfer, unfamiliar-error, environment-change, incomplete-instruction, learn-from-failure, cross-OS transfer) | P24 | `intelligence_benchmark.py` (regression-style only) |
| M10 | ~~**OS concept-verb abstraction**~~ ✅ LIVE 2026-09-08 — `app/mind/os_concepts.py`: open/copy/navigate/… as platform-free concepts with embodiment mapping derived from the live manifest; procedures transfer across bodies (Phase 12) | P12 | ~~`os_control_planner.py` seed~~ |
| M11 | ~~**Prediction↔reality comparison loop**~~ ✅ LIVE 2026-09-08 — `app/mind/imagination.py`: simulate-before-acting + compare-vs-reality ledger + confirmed/refuted training data through the Phase-6 loop (Phase 10; `prediction_engine.py` wired) | P10 | ~~`prediction_engine.py` + `execution_truth.py` (not connected)~~ |

Every M-item is testable in isolation and none requires deleting existing code —
each attaches to a named fragment above. This is the sequencing input for the
post-Phase-0 plan.

---

## 7. Surfaces not in the Python ledger

- **Frontend (React, 201 src files):** communication/presence layer. 18 route
  pages; voice overlay + wake-word settings mounted (charter §5①). Phase 22 will
  gradually demote dashboard pages to "contextual windows into the mind"; no
  structural change now. Dead-code state: 27 unused exports, acknowledged per
  charter §5⑤ (`scripts/audit_dead_code.py`).
- **Android (Kotlin Compose, 49 files):** communication/presence + voice-first
  embodiment client. Already talks to the one server (`ApiClient`,
  `VoiceWebSocketClient`, wake-word service). Phase 23-ready.
- **Desktop (PySide6, 33 files):** same role as Android; BeaniePage + presence orb
  already exist. Crash-guard in `desktop/main.py` is permanent.
- **`docs/archive/`, root-level plan docs:** historical; `docs/README.md` remains
  the index. This map + roadmap join the authoritative set.

---

## 8. What happens next (proposed, owner decides)

**Status 2026-09-08: steps 1–18 are LIVE (Phases 1–18 complete).**

Per the roadmap's restructuring order, the first build step after this freeze:

1. ✅ **`BeanieMind` facade + identity record** (M1) — `app/mind/beanie_mind.py`
   + `app/mind/identity.py`; wraps the existing runtime singleton; zero behavior
   change; the string persona became a persisted identity with owner-visible
   state. Test-pinned (`tests/test_beanie_mind.py`).
2. ✅ **`BeanieState` skeleton** (M2) — `app/mind/state.py`; read-only views over
   the runtime's real organs, every room honestly marked ok/wired/unavailable.
   Test-pinned.
3. ✅ **Entry convergence** (§5) — WS text + voice (`backend/message_router.py`)
   and REST (`CognitivePipeline.process_request`) call `BeanieMind.process` with
   modality tags; old result shapes unchanged.
4. ✅ **Phases 3–5 LIVE (2026-09-08)** — `world_facade.py` (ontology +
   pre-action understanding), `self_facade.py` (genuine self-assessment),
   `memory_facade.py` (UnifiedMemory + SocialMemoryStore + MetaMemory).
   22 tests in `tests/test_mind_models.py`.
5. ✅ **Phase 2 LIVE (2026-09-08)** — `world_first.py`: the door assembles the
   world → self → memory brief BEFORE capability identification and delivers
   it through working memory (the cycle's existing prompt channel), attention
   gate decisions recorded (M6 resolved). 11 tests in `tests/test_world_first.py`;
   16 `/mind/*` endpoints total.
6. ✅ **Phase 6 LIVE (2026-09-08)** — `learning_loop.py`: one deterministic
   loop for every experience (action, conversation, correction, observation,
   media, demonstration, experiment); the door auto-submits cycle outcomes
   (success = `goal_verified` ONLY — missing verdict stays UNKNOWN) and owner
   chat corrections; writes land in the Phase-5 unified memory and verified
   outcomes feed the Phase-5 calibrator. Fail-open + kill switch
   (`ARENA_LEARNING_LOOP=0`). 16 tests in `tests/test_learning_loop.py`;
   19 `/mind/*` endpoints total.
7. ✅ **Phase 7 LIVE (2026-09-08)** — `teaching.py`: conversation is the
   teaching interface (M7 resolved). "watch this" → steps → her proposal →
   owner's "yes" → procedure stored in cognitive procedural memory + the
   existing taught-skills store + the Phase-6 ledger (verified
   demonstration). Two misreadings → honest stop, nothing saved. Lesson
   turns are consumed before the task cycle; kill switch `ARENA_TEACHING=0`.
   17 tests in `tests/test_teaching.py`; 21 `/mind/*` endpoints total.
8. ✅ **Phase 8 LIVE (2026-09-08)** — `media_learning.py`: images/video/
   audio/web enter the ONE Phase-6 loop as `media` experiences (the
   `universal_media_learner.py` + `youtube_learner.py` nuclei INTEGRATED as
   capabilities). Deterministic observation first; watching is never
   verification (success=None); every failure typed. 10 tests in
   `tests/test_media_learning.py`; 22 `/mind/*` endpoints total.
9. ✅ **Phase 9 LIVE (2026-09-08)** — `curiosity.py`: the internal UNKNOWN
   system. Brief gaps register automatically; topics normalize; encounters
   compound; investigate = memory-first with the same evidence gate as the
   learning loop; resolution paths counted (knowledge / investigation /
   owner); no-evidence unknowns stay open; recurrences reopen. Fail-open +
   kill switch (`ARENA_CURIOSITY=0`). 11 tests in
   `tests/test_curiosity.py`; 25 `/mind/*` endpoints total.
10. ✅ **Phase 10 LIVE (2026-09-08)** — `imagination.py`: the epistemic
    ladder as labeled states; simulate before acting (PredictionEngine +
    own verified history + open unknowns + deterministic counsel); compare
    prediction vs reality (bool evidence only) into a persistent ledger and
    confirmed/refuted training data via the Phase-6 loop (M11 resolved).
    Verified cycles auto-compare at the door; the runtime keeps owning the
    calibrator. Kill switch `ARENA_IMAGINATION=0`. 12 tests in
    `tests/test_imagination.py`; 28 `/mind/*` endpoints total.
11. ✅ **Phase 11 LIVE (2026-09-08)** — `embodiment.py`: the 184
    capabilities became her motor system. Concepts in ("interact with my
    phone"), ranked pathways out with evidence, embodiment labels
    (pc/android/web), authority surfaced as requires_owner_approval, plans
    never execution, motor gaps → open unknowns. 9 tests in
    `tests/test_embodiment.py`; 30 `/mind/*` endpoints total.
12. ✅ **Phase 12 LIVE (2026-09-08)** — `os_concepts.py` (M10 resolved):
    one platform-free concept layer over all bodies; per-body mapping
    derived from the live manifest by evidence; procedures (explicit or
    Phase-7 taught) transfer across bodies with resolved-or-gap honesty.
    10 tests in `tests/test_os_concepts.py`; 35 `/mind/*` routes total.
13. ✅ **Phase 13 LIVE (2026-09-08)** — `perception.py`: the SENSE side.
    Eight typed channels; perceptions enter the Phase-6 loop (novel →
    knowledge, repeated → rehearsed); significance = urgency / novelty /
    curiosity with surfaced reasons; the silent watcher's buffered changes
    ingest at the door + on demand. Kill switch `ARENA_PERCEPTION=0`.
    12 tests in `tests/test_mind_perception.py`; 35 `/mind/*` paths
    (38 routes — three paths carry two verbs) total.
14. ✅ **Phase 14 LIVE (2026-09-08)** — `attention.py` (M8 resolved): the
    arbitrator between perception and thought. Roadmap ladder from evidence
    on the record (owner speech / urgency / novelty / unknown touch /
    background), reasons surfaced, repeats demoted, watermark review, one
    open unknown surfaced only when quiet; the popup-over-task advisory
    ("may interfere with what you're doing") offered to working memory.
    Decides only — `acted: False` on every verdict. Kill switch
    `ARENA_ATTENTION=0`. 16 tests in `tests/test_mind_attention.py`;
    38 `/mind/*` paths (41 routes) total.
15. ✅ **Phase 15 LIVE (2026-09-08)** — `motivation.py`: goals from
    evidence only — six real sources (open unknowns, parked goals, owner
    speech, attention verdicts, verified failures, learned rhythms);
    relevance = named contributions; recurrence compounds; proposals are
    questions built from the goal's own evidence (`acted: False`);
    accepted goals execute through the normal door under owner authority;
    auto-propose only when earned (score ≥5.0) and cooled (10
    interactions). Kill switch `ARENA_MOTIVATION=0`. 15 tests in
    `tests/test_mind_motivation.py`; 41 `/mind/*` paths (44 routes) total.
16. ✅ **Phase 16 LIVE (2026-09-08)** — `social.py`: the persistent owner
    relationship model. Facets (preference / boundary / emotion cue /
    interest / person) extracted ONLY from what the owner said, evidence on
    every facet; repeats compound. Routines / communication style / history
    measured from the real door ledger, claimed only with ≥10 interactions.
    People register in the Phase-5 social store with provenance. Kill
    switch `ARENA_SOCIAL=0`. 15 tests in `tests/test_mind_social.py`;
    43 `/mind/*` paths (46 routes) total.
17. ✅ **Phase 17 LIVE (2026-09-08)** — `personality.py`: the developing
    personality, never a hard-coded mask. Basic identity (Phase-1
    BeanieIdentity) plus traits DERIVED from her real ledgers with evidence
    and observation counts: experience profile (learning ledger), epistemic
    calibration (imagination confirmed/refuted), curiosity stance, her OWN
    communication pattern (reply samples at the door, ≥5 to describe,
    ≥10 for an early-vs-late trend), values learned from the owner
    (explicit value statements only — the owner's values, never system
    morals), adaptation to the owner's measured style (Phase 16). `derive()`
    snapshots and diffs: `changes()` is the verifiable record of "Beanie
    has changed." Kill switch `ARENA_PERSONALITY=0`. 16 tests in
    `tests/test_mind_personality.py`; 45 `/mind/*` paths (48 routes) total.
18. ✅ **Phase 18 LIVE (2026-09-08)** — `authority.py`: the OWNER's
    authority — five lanes of owner-stated rules (always / ask-first /
    never / trusted contexts / temporary); Phase-16 boundaries seed the
    never lane; risk patterns decide only WHEN TO ASK (ask-first opens a
    typed requires_owner_approval ask, never a silent drop); answers
    obeyed; no system morals; authority ≠ intelligence; judges
    authorization, never executes. Kill switch `ARENA_AUTHORITY=0`.
    17 tests in `tests/test_mind_authority.py`; 48 `/mind/*` paths
    (51 routes) total.
19. **Open (roadmap order):** Phase 19 self-reflection (what happened?
    why? what did I believe? was I correct? what surprised me? what did I
    learn? should I change my model? — the bridge between experience and
    development), then self-improvement / model evolution / voice-first
    UI / one-mind desktop+Android, and M9 generalization eval (P24), per
    the owner's sequencing.

---

## 9. Durability

This map exists because sessions reset and agents crash. Any future session must
read `AGI_ROADMAP.md` → this map → the CSV before proposing architecture work.
Regenerate the ledger with `python scripts/map_agi_architecture.py`; a growing
unclassified count means new modules were added without classification — that is
drift, and it stops at review.
