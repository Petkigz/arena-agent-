# Beanie AGI Roadmap — Owner-Governing Direction

**Recorded:** 2026-09-08, verbatim from the owner's roadmap (session noise about a
previous agent's GitHub access failure removed; nothing else altered).
**Status:** GOVERNING for *direction and sequencing*. [`OWNER_VISION_CHARTER.md`](OWNER_VISION_CHARTER.md)
remains governing for vision and permission; [`../AGENT_INVARIANTS.md`](../AGENT_INVARIANTS.md)
remains governing for honesty invariants. This roadmap governs how Arena becomes
one continuously learning artificial mind. The file-by-file consequence of Phase 0
is [`AGI_ARCHITECTURE_MAP.md`](AGI_ARCHITECTURE_MAP.md) + its
[CSV ledger](AGI_ARCHITECTURE_MAP_FILES.csv).

> **The most important rule for the entire roadmap:** whenever we're considering a
> new subsystem, ask: *"Is this another capability, or is this increasing Beanie's
> general intelligence?"* If it's only another capability — don't rush to build it.
> There are already 184 manifest capabilities. If it increases understanding,
> abstraction, generalization, memory, reasoning, learning, curiosity, self-awareness,
> world modeling, adaptation, transfer, or social intelligence — it moves us toward
> the actual objective.

---

The goal is not to bolt more features onto Arena. The goal is to evolve what already
exists into one continuously learning artificial mind.

## North-star

Build a local, embodied artificial intelligence that can communicate naturally with
its owner, perceive the world, reason about unfamiliar problems, learn from
experience and demonstrations, remember what matters, develop an individual
personality, operate across devices, and continuously improve its ability to
accomplish goals.

The important word is **general**.

We should not optimize Beanie to pass a fixed collection of tasks. We should optimize
her ability to encounter a new task and figure out how to solve it.

## Phase 0 — Freeze the architecture before changing it

Goal: stop the project from drifting further.

Before adding intelligence, establish what each existing subsystem actually is.

```
Arena
│
├── Mind
│   ├── perception
│   ├── cognition
│   ├── memory
│   ├── world model
│   ├── self model
│   ├── learning
│   ├── reasoning
│   ├── motivation
│   └── reflection
│
├── Body
│   ├── Windows
│   ├── Linux
│   ├── macOS
│   ├── Android
│   ├── browser
│   ├── filesystem
│   └── other devices
│
├── Senses
│   ├── microphone
│   ├── screen
│   ├── camera
│   ├── images
│   ├── video
│   └── web
│
├── Communication
│   ├── voice
│   └── text
│
└── Tools
    └── capabilities
```

Important: **Don't delete the existing systems yet.** Instead classify every module
as Mind / Memory / Perception / Learning / Body / Tool / Communication /
Infrastructure / Legacy / Duplicate. This gives us a map of the existing codebase.

## Phase 1 — Create the actual "Mind"

> ✅ **LIVE 2026-09-08:** `app/mind/` — `BeanieMind.process(...)` is the one
> canonical door: WS text, voice (`source="voice"` → modality `voice`), and
> REST `/chat` all enter through it into the existing CognitiveRuntime
> singleton (one brain, always — the mind wraps it, never replaces it).
> "I am Beanie" now exists as persisted backend state (`BeanieIdentity`,
> tables `beanie_identity`/`beanie_milestones`; M1) and the BeanieState
> skeleton reports all 15 internal-state rooms honestly (M2). Owner-visible:
> `GET /mind/identity`, `GET /mind/state`, `GET /mind/entries`. Guarded by
> `tests/test_beanie_mind.py` (21 tests). Full suite green at this step.

This is the most important architectural phase. Right now there is a
CognitiveRuntime, orchestrators, planners, agents, matchers, etc. Make one of them
the actual mind coordinator:

```
                    BEANIE MIND
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
   PERCEIVE          REMEMBER           THINK
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                     UNDERSTAND
                         │
                     DECIDE
                         │
                 ┌───────┴───────┐
                 │               │
               ACT             LEARN
                 │               │
                 └───────┬───────┘
                         │
                     REFLECT
                         │
                     REMEMBER
```

Everything else becomes something the Mind can call.

**Deliverable:** one canonical entry point: `BeanieMind.process(...)`. Whether input
comes from voice, text, Android, desktop, screen observation, camera, or another
process — it enters the same mind.

## Phase 2 — Replace tool-first thinking with world-first thinking

> ✅ **LIVE 2026-09-08:** `app/mind/world_first.py` — at the mind door, every
> conversational request now gets a deterministic, provenance-tagged **brief**
> assembled in the roadmap's order (world context → self state → relevant
> memory) from the Phase 3–5 organs, BEFORE the cycle identifies any
> capability. Delivery goes through the brain's working-memory scratchpad —
> the channel the cognitive cycle already reads when building its prompt —
> and the attention gate's acceptance/rejection is recorded honestly. Pure
> retrieval, no LLM, budget-bounded; pure-ignorance briefs are skipped
> (noise is not intelligence). Fail-open: a broken brief path never breaks
> the door. Kill switch: `ARENA_WORLD_FIRST=0`. Owner-visible:
> `GET /mind/brief?text=...` (preview) and `GET /mind/briefs` (ledger).
> Guarded by `tests/test_world_first.py` (11 tests), incl. the roadmap's
> "find the document I was editing yesterday" example against live data.

Instead of `request → find tool → execute tool`, build:

```
request → understand goal → understand current world → retrieve relevant memories
→ form hypotheses → choose strategy → identify capabilities required → act
```

Tools become capabilities, not the intelligence itself. For example, "Find the
document I was editing yesterday": Beanie shouldn't immediately search for a
filesystem tool. She should reason: "document" + "editing" + "yesterday" +
"owner's computer" — construct a model of what she's looking for — *then* choose
filesystem/search/application/screen capabilities.

## Phase 3 — Build the World Model

> ✅ **LIVE 2026-09-08:** the existing provenance-enforced `WorldModel` is kept
> as the authoritative store; `app/mind/world_facade.py` adds the roadmap's
> ontology (People, Places, Devices, Applications, Files, Websites, Accounts,
> Objects, Concepts, Events, Processes), typed teaching (`remember_entity` /
> `relate` — missing endpoints are honest failures, never fabricated),
> provenance-required state observations, and PRE-action understanding
> (`understand(text)` → matched entities + latest states + visible gaps).
> Owner-visible: `GET /mind/world`, `/mind/world/about`, `/mind/world/understand`;
> teaching via `POST /mind/world/{entities,relations,observations}`. Guarded by
> `tests/test_mind_models.py`. (The Phase-2 consumption of this context inside
> the reasoning cycle is the next integration step.)

The biggest missing AGI component (see the map for what already exists as
verification-side fragments). Create a persistent representation of: People,
Places, Devices, Applications, Files, Websites, Accounts, Objects, Concepts,
Events, Relationships, States, Processes.

```
Computer                    Project X
├── Windows 11              ├── created: ...
├── Arena                   ├── modified: ...
├── Photoshop               ├── application: Blender
├── Blender                 ├── state: unfinished
├── projects/               └── related task: ...
└── downloads/
```

Now Beanie can reason about the environment rather than merely execute commands
against it.

## Phase 4 — Build the Self Model

> ✅ **LIVE 2026-09-08:** `app/mind/self_facade.py` makes "I don't know" a
> genuine internal state. `assess(task)` returns exactly the roadmap's shape —
> `knowledge` ∈ {known, partial, unknown}, rule-based `confidence` from REAL
> evidence (capability-catalog match + memory hits, never vibes; unknown =
> 0.08, the roadmap's number), and typed `possible_actions`
> (investigate / ask_owner / observe_demonstration / search). Capability
> awareness reports the full catalog INCLUDING Level-3 actions, because
> authority ≠ intelligence (charter §18): understanding a capability is not
> authorization to run it. Limitations read the hardware self-model honestly.
> Owner-visible: `GET /mind/self`, `GET /mind/self/assess?task=...`. Guarded
> by `tests/test_mind_models.py`.

Beanie needs a persistent model of herself: identity, capabilities, limitations,
knowledge, beliefs, uncertainty, experiences, preferences, personality, goals,
current state, development history.

"I don't know how to configure this application" should become a genuine internal
state:

```
knowledge: unknown
confidence: 0.08
possible_actions: investigate / ask owner / observe demonstration / search
```

That is much closer to general intelligence than simply returning "I don't know."

## Phase 5 — Unified Memory

> ✅ **LIVE 2026-09-08:** `app/mind/memory_facade.py` — `UnifiedMemory` is the
> ONE view over all eight kinds: working (runtime scratchpad), episodic /
> semantic / procedural / lesson (existing MemoryStore), **social** (NEW
> `SocialMemoryStore` — people/relationships with provenance, interaction
> counts, owner-confirmed forget), preference (Phase-7 engine + owner model),
> autobiographical (identity milestones), and **meta-memory** (NEW
> `MetaMemory`: `remembered_done` / `knows_how` / `heard_about` / `unknown`,
> each citing its evidence — "I remember doing this" vs "I think I know how
> but never did"). Single typed write surface (`remember(kind, ...)`).
> Owner-visible: `GET /mind/memory`, `/mind/memory/meta?q=...`,
> `/mind/memory/social`; writes via `POST /mind/memory`, `/mind/memory/social`.
> Guarded by `tests/test_mind_models.py`.

Don't make memory simply "chat history." Build multiple kinds of memory under one
system: Working, Episodic (experiences), Semantic (facts/concepts), Procedural
(how to do things), Social (people/relationships), Preference (owner's
preferences), Autobiographical (Beanie's history), and **Meta-memory** (what
Beanie knows about what she knows).

The last one is important. Beanie should know: "I remember doing this" versus
"I think I know how to do this, but I've never actually done it."

## Phase 6 — General Learning Engine

> ✅ **LIVE 2026-09-08:** `app/mind/learning_loop.py` — ONE deterministic
> loop (`GeneralLearningEngine`) that every experience passes through:
> observe → interpret → compare with existing knowledge → detect novelty →
> form hypothesis → test → observe outcome → update model → store knowledge
> → update confidence. Every KIND of experience enters through the same mind
> door (`BeanieMind.learn`): actions, conversations, corrections,
> observations, media, demonstrations, experiments — and Phase-8 media
> learners will submit through this same door, not build their own loops.
>
> Honesty rules ARE the engine: `success` must be evidence the caller has —
> verified True, verified False, or UNKNOWN (attempted ≠ succeeded, never
> guessed); reinforcement rehearses knowledge instead of duplicating it;
> contradictions become explicit hypotheses + lessons, never silent
> overwrites. The door consumes it two ways automatically: every completed
> cognitive cycle is submitted as an `action` experience (success taken ONLY
> from `goal_verified` — a missing verdict stays UNKNOWN), and every recorded
> owner chat correction is fed as a `correction` experience (lessons). The
> engine writes through the Phase-5 unified memory (provenance-tagged,
> deduped) and feeds verified outcomes to the Phase-5 confidence calibrator.
> Fail-open: learning never fails the task that produced it. Kill switch:
> `ARENA_LEARNING_LOOP=0`. Owner-visible: `POST /mind/learn`,
> `GET /mind/learning` (the learning landscape), `GET /mind/learning/events`
> (the ledger). Guarded by `tests/test_learning_loop.py` (16 tests), incl.
> the typed-intake, novelty, contradiction→hypothesis, experiment verdict,
> dedupe-rehearsal, calibration, and auto-door contracts.

The learning loop: experience → observe → interpret → compare with existing
knowledge → detect novelty → form hypothesis → test → observe outcome → update
model → store knowledge → update confidence.

This should work for: conversations, documents, images, videos, websites,
demonstrations, mistakes, successful actions, owner corrections, experiments.

## Phase 7 — Learning From You

> ✅ **LIVE 2026-09-08:** `app/mind/teaching.py` — `DemonstrationTeaching`:
> conversation IS the teaching interface, exactly as the scene below —
> "Beanie, watch this" opens a lesson; steps are gathered (numbering and
> lead-ins stripped deterministically); "that's it" makes her PROPOSE her
> understanding ("So to organize files, you: 1) … 2) … Is that correct?");
> nothing is stored until the owner says "yes". A confirmed procedure lands
> in three places honestly: cognitive **procedural** memory (owner_taught,
> success=True — so world-first briefs and memory search surface it), the
> EXISTING taught-skills store (`SkillTeachingEngine`, the form-driven engine
> this phase integrates), and the Phase-6 learning ledger as a VERIFIED
> demonstration experience. Rejection never fabricates: she asks again, and
> after two misreadings stops and says nothing was saved. Markers are
> conservative (bare "watch this" only opens a lesson in a short message, so
> "watch this video for me" can't hijack a turn); sessions are in-memory and
> expire when abandoned (stated limit, not hidden). No LLM, no forms, no
> JSON. Router consumes lesson turns before the task cycle (the steps belong
> to the lesson, not a tool run); fail-open + kill switch `ARENA_TEACHING=0`.
> Owner-visible: `GET /mind/procedures`, `GET /mind/teaching/sessions`;
> live-demo verified against the real server (the roadmap's own scene, and
> the stored procedure retrieved as the top hit for "how should I organize
> files"). Guarded by `tests/test_teaching.py` (17 tests).

This should become one of the easiest things you can do.

You: "Beanie, watch this." Then demonstrate. She observes.
You: "This is how I normally organize these files." She learns.
Then: "So you group them by project first, then type. Is that correct?"
You: "Yes."

Now she has learned a generalized procedure. No forms. No manually creating
skills. No writing JSON. **Conversation is the teaching interface.**

## Phase 8 — Learning From Images and Video

> ✅ **LIVE 2026-09-08:** `app/mind/media_learning.py` — `MediaLearning`:
> images, video, audio, and web media enter the ONE Phase-6 loop as another
> experience kind (`media`) — not a new loop. Deterministic observation
> first: real file facts via PIL, YouTube transcripts via the existing
> `YouTubeLearner` (no LLM on that path), web scraping via the existing
> `UniversalMediaLearner` (no LLM), OCR only when a tesseract binary
> actually exists (its absence is reported, not faked). The existing LLM
> analysers stay the deep-analysis capabilities; `deep=true` optionally
> appends their summary and fails honestly when no model is loaded. The
> Phase-6 loop then compares / classifies novelty / stores (deduped) /
> records the ledger entry, with provenance naming the target. Honesty
> rule: **watching is never verification — every media experience carries
> success=None**, and every failure is typed (no transcript, unreadable
> image, fetch error, unsupported target) with nothing fabricated.
> Live-verified against the real server: a real PNG lands with true
> dimensions/format; a real YouTube attempt without network returns the
> typed reason and stores nothing. Owner-visible: `POST /mind/learn/media`
> (22 `/mind/*` endpoints total). Deferred with evidence, not abandoned:
> auto-learning the OUTPUTS of media tools run inside cognitive cycles
> needs the runtime's tool-result shape (Phase 11 embodiment work).
> Guarded by `tests/test_media_learning.py` (10 tests).

```
MEDIA LEARNING
├── audio
├── speech
├── frames
├── OCR
├── objects
├── UI elements
├── actions
├── temporal relationships
└── context
       ↓
   understanding → procedure inference → concept extraction
       → causal relationships → skill/knowledge candidate
```

The key question isn't "What did the video say?" It's: "What happened, why did it
happen, and what can I generalize from it?"

## Phase 9 — Curiosity / Exploration

> ✅ **LIVE 2026-09-08:** `app/mind/curiosity.py` — `CuriosityEngine`, the
> internal UNKNOWN system. Ignorance becomes a RECORD: every gap a
> world-first brief surfaces ("not yet in world model") is registered
> automatically at the door; topics normalize ("The Document" ≡ "the
> document"), and re-encounters COMPOUND (repeated ignorance outranks
> one-off ignorance). Before asking the owner, she investigates her own
> memory first (same evidence gate as the learning loop — recall-broad
> search, term-overlap verdicts). Resolution paths are counted separately:
> `knowledge` (incoming experience through the Phase-6 door matched the
> unknown), `investigation` (real memory evidence found), `owner` (you
> answered). Uncertainty ↓ and knowledge ↑ are ledger facts, not vibes.
> Honesty rules: an unknown with no evidence stays OPEN and the engine
> names the next honest step ("ask the owner"); filler tokens from gap
> extraction ("really", "where") are rejected — noise is not curiosity;
> resolved unknowns that recur REOPEN. Owner-visible: `GET /mind/curiosity`
> (landscape + priorities), `POST /mind/curiosity/investigate`,
> `POST /mind/curiosity/resolve` (25 `/mind/*` endpoints total). Fail-open
> + kill switch `ARENA_CURIOSITY=0` (gates the automatic feeds; the owner
> surface keeps working). Live-verified: unfamiliar request → open unknowns,
> re-ask → compounding, one teaching sentence → three unknowns resolved via
> the knowledge path. Guarded by `tests/test_curiosity.py` (11 tests).
> Deferred to embodiment (Phases 11–13): autonomous experiments/screen
> inspection as investigation actions — the roadmap's "try a harmless
> experiment" needs the motor system.

Give her an internal UNKNOWN system. She encounters something unfamiliar:
"I don't understand X." Instead of immediately asking you: UNKNOWN → investigate.
She can search, inspect, experiment, compare sources, observe, ask you, try a
harmless experiment, revisit previous memories. Then: uncertainty ↓, knowledge ↑.
This is a critical AGI behavior.

## Phase 10 — Reasoning and Imagination

> ✅ **LIVE 2026-09-08:** `app/mind/imagination.py` — `Imagination`: the
> roadmap's epistemic ladder (perception / belief / hypothesis / prediction
> / simulation / reality) is now represented as labeled states, and the
> SIMULATE + COMPARE stages are wired around the existing brain.
> `simulate(action_type)` runs a candidate action in her head BEFORE acting:
> the existing `PredictionEngine` produces the prediction (expected changes +
> confidence, learned or default), then she consults her OWN verified
> history (episodic evidence) and her open unknowns (curiosity) and returns
> deterministic counsel. `compare(action_type, success)` judges the
> prediction against reality — reality must be bool EVIDENCE, never a guess
> — persists a prediction-vs-reality ledger (sqlite), stores the verified
> outcome as an episode, and submits the comparison to the Phase-6 loop as
> an `experiment` experience with a declared prediction → verdict
> confirmed/refuted → **failures become training data** (M11 resolved: the
> prediction↔reality loop is connected). The door auto-compares every cycle
> with a definite verdict and an action (waiting-for-evidence never
> compares); kill switch `ARENA_IMAGINATION=0`. Division of labor, stated:
> the runtime already predicts/evaluates surprisal/feeds the calibrator —
> the organ owns the ledger, verdicts, and training-data feed, and never
> double-counts calibration. Live-verified against the real server:
> `simulate("search_files")` found her REAL verified failure from a past
> cycle and counseled "failed 1 time before, never verifiably succeeded —
> proceed carefully" with confidence capped at 0.5. Owner-visible:
> `POST /mind/imagination/simulate`, `POST /mind/imagination/compare`,
> `GET /mind/imagination` (28 `/mind/*` endpoints total). Guarded by
> `tests/test_imagination.py` (12 tests).

Add a distinction between: Perception ("The screen contains this"), Belief
("I think this is happening"), Hypothesis ("Perhaps X caused it"), Prediction
("If I do X, Y should happen"), Simulation ("If I take this path, the likely
result is..."), Reality ("I actually tried it and Y happened").

```
PERCEIVE → MODEL → HYPOTHESIZE → SIMULATE → ACT → OBSERVE
→ COMPARE PREDICTION vs REALITY → LEARN
```

Now failures become training data for intelligence, rather than just bugs.

## Phase 11 — Embodied Intelligence

> ✅ **LIVE 2026-09-08:** `app/mind/embodiment.py` — `Embodiment`: the
> existing 184 capabilities became her motor system. The roadmap's key
> change is real: she reasons in CONCEPT terms ("I need to interact with my
> phone") and the capability layer figures out how — deterministic concept
> expansion (phone → android/adb/sms/…), a term-overlap scan of the tool
> manifest with evidence on every candidate (matched terms, score), the
> existing `tool_matcher` promoted as primary resolver where it fires, and
> embodiment labels (pc / android / web) per pathway. Live-verified against
> the REAL body: "interact with my phone" → phone_call / phone_sms /
> phone_command (all android); "read the document I was editing" →
> read_document; body image = 184 capabilities across 23 categories.
> Honesty rules: the organ PLANS, it never EXECUTES — acting stays with the
> cycle's proposal/authorization/verification path (one cognitive
> authority); authority ≠ intelligence — pathways she understands but isn't
> authorized for surface as `requires_owner_approval` (never hidden, never
> refused); a missing motor pathway is an honest None AND becomes an open
> unknown in the curiosity system (motor gaps are ignorance too).
> Owner-visible: `POST /mind/embodiment/plan`, `GET /mind/embodiment`
> (30 `/mind/*` endpoints total). Guarded by `tests/test_embodiment.py`
> (9 tests, incl. a manifest whose handlers explode if the motor system
> ever executes one).

```
                  BEANIE MIND
                       │
             ┌─────────┴─────────┐
             │                   │
           SENSE               ACT
             │                   │
     ┌───────┼───────┐     ┌─────┼───────┐
     │       │       │     │     │       │
   screen  audio   camera  PC  Android  Web
```

The existing capabilities become the motor system. The important change: Beanie
doesn't know "tool #73." She knows: "I need to interact with my phone." The
capability layer figures out how.

## Phase 12 — True OS-Level Generalization

> ✅ **LIVE 2026-09-08:** `app/mind/os_concepts.py` — `OSConceptLayer`
> (M10 resolved). No WindowsTool / MacTool / LinuxTool / AndroidTool as
> separate intelligence: ONE platform-free concept layer — open, close,
> move, copy, rename, search, install, configure, read, write, observe,
> click, type, navigate, communicate — with embodiment mapping derived from
> the LIVE tool manifest by term evidence (no hand-catalogued platform
> tables to rot). `express(intent)` returns the concept, its meaning, the
> target, and the per-body capability map (pc / android / web) with matched
> terms on every mapping; `generalizes` is decided by coverage (≥2 bodies),
> never claimed. `transfer(to_platform, steps|procedure)` is the roadmap's
> crown jewel: explicit steps OR a Phase-7 taught procedure, re-expressed
> for the target body — every step resolves to a capability or is flagged
> as a VISIBLE gap (generalization you can inspect, not a claim). Live
> against the real body: communicate covers pc×6 + android×1 (phone_sms via
> sms evidence); open covers pc×5 + web×3 with an honest android gap; the
> Phase-7-taught 'organize-files' procedure transfers to android with its
> non-OS steps honestly flagged. The layer expresses and maps — it never
> executes (Phase-11 doctrine). Owner-visible: `POST /mind/os/express`,
> `POST /mind/os/transfer`, `GET /mind/os/concepts` (33 `/mind/*`
> endpoints). Guarded by `tests/test_os_concepts.py` (10 tests, incl.
> taught-procedure transfer and a manifest whose handlers explode if
> executed).

Don't build WindowsTool / MacTool / LinuxTool / AndroidTool as separate
intelligence. Build an **OS abstraction** where Beanie understands concepts such
as: open, close, move, copy, rename, search, install, configure, read, write,
observe, click, type, navigate, communicate. Then the embodiment layer maps them
to the appropriate platform.

That means Beanie can learn "How I accomplish this goal on Windows" and later
generalize the concept to Android or Linux.

## Phase 13 — Continuous Perception

> ✅ **LIVE 2026-09-08:** `app/mind/perception.py` — `Perception`: the SENSE
> side of the embodiment diagram. screen / camera / audio / phone / desktop /
> network / environment / owner channels become TYPED perceptions (the
> epistemic label 'perception' rides every record — a perception is not a
> belief and never an action). Each perception enters the Phase-6 loop as an
> `observation` experience: novelty decides storage (novel → knowledge,
> repeated → rehearsed — the loop's dedupe IS the roadmap's "don't react to
> everything"). Significance is computed from three evidence sources with
> surfaced REASONS: urgency (the probe declared it), novelty (the loop
> called it novel), and curiosity (it touches an open unknown — scanned
> broadly, because buried unknowns are exactly what perceptions should
> surface). The existing silent watcher (`BackgroundObserver`, already
> probing every 30s) is wired in: `drain_background_observer()` ingests its
> buffered `EnvironmentChange`s as perceptions — automatically at the door
> on every interaction, and on demand. Live-verified: novel screen event →
> significant; the SAME event again → background (no re-reaction); a
> perception touching a buried open unknown flagged significant AND closed
> the unknown through the knowledge path. Owner-visible:
> `POST /mind/perception`, `POST /mind/perception/drain`,
> `GET /mind/perception` (36 `/mind/*` endpoints). Kill switch
> `ARENA_PERCEPTION=0` gates the door drain; the owner surface keeps
> working. Guarded by `tests/test_mind_perception.py` (12 tests; the
> pre-existing `tests/test_perception.py` speech tests stay untouched).

screen, camera, microphone, phone state, desktop state, network/environment →
perception → attention → significance. Beanie shouldn't react to everything. She
should determine: "Is this relevant to what we're doing?" That gives you an
attention system.

## Phase 14 — Attention

```
ATTENTION
├── current task
├── owner speaking
├── important change
├── anomaly
├── unfinished goal
├── learned curiosity
└── background observation
```

You're editing something. A popup appears. Beanie sees it. Instead of doing
nothing because nobody explicitly called the screen tool: "Something changed that
may interfere with what you're doing." That's much closer to an assistant that
actually exists alongside you.

## Phase 15 — Motivation and Goals

Introduce autonomous goals carefully — not randomly generated tasks. Instead:
needs, curiosity, unfinished goals, owner goals, environment opportunities,
learning opportunities → candidate goals → evaluate relevance → prioritize → act.

Beanie can eventually say: "You mentioned yesterday that you wanted to organize
the project. I noticed the files are still scattered. Do you want me to handle
that?" That's useful autonomous behavior.

## Phase 16 — Social Intelligence

Because the goal is helper + secretary + friend, build an owner model:
preferences, habits, communication style, goals, routines, interests,
relationships, boundaries, emotional/contextual cues, history with Beanie.

This shouldn't mean pretending to be human. It means developing a persistent
relationship model.

## Phase 17 — Personality Development

Don't hard-code the personality forever. Start with a basic identity. Then:
interactions → experiences → preferences → communication patterns → values
learned from owner → personality development. You should eventually be able to
notice "Beanie has changed" because her behavior actually changed through
experience.

## Phase 18 — Owner Authority

Not arbitrary system morals. Not random hard-coded restrictions. Instead:

```
OWNER
├── always allowed
├── ask first
├── never do
├── trusted contexts
└── temporary permissions
```

And importantly: **Authority ≠ intelligence.** Beanie can understand how to do
something even when she's not currently authorized to do it. That's a crucial
distinction.

## Phase 19 — Self-Reflection

After important experiences: What happened? Why? What did I believe? Was I
correct? What surprised me? What did I learn? Should I change my model? Should I
remember this? This becomes the bridge between experience and development.

## Phase 20 — Self-Improvement

Only after the previous pieces work: detect capability gap → investigate → design
improvement → implement → test → measure → retain/revert. The existing
self-evolving/code-generation infrastructure can become part of this — one
mechanism of self-improvement, not the definition of intelligence.

## Phase 21 — Model Evolution

Only now work on: base model + memory + world model + self model + learned
examples + personality + optional LoRA. The model itself doesn't need to be
retrained after every interaction:

- **Fast learning:** memory/world-model updates.
- **Medium-term learning:** skill/concept consolidation.
- **Long-term learning:** dataset creation + evaluation + optional adapter training.

That prevents catastrophic forgetting and unnecessary retraining.

## Phase 22 — Voice-first Beanie

The desktop shouldn't look like a traditional dashboard. It should feel like:

```
┌───────────────────────────────────────────┐
│                                           │
│                 Beanie                    │
│                                           │
│              "Yeah?"                      │
│                                           │
│       ───────────────────────             │
│                                           │
│   [small visual state / avatar]           │
│                                           │
│          Listening...                     │
│                                           │
└───────────────────────────────────────────┘
```

The complicated information exists when needed, not permanently.
Voice: primary. Text: backup. Visual UI: contextual window into the mind.

## Phase 23 — Desktop + Android as embodiments

```
Arena Server
      ├──────────→ Desktop Beanie ── background presence
      └──────────→ Android Beanie ── background presence
```

Both are clients of the same Mind. Not two separate assistants.

## Phase 24 — AGI Evaluation

Stop measuring primarily "How many tests pass?" Measure **generalization**.
Create tasks Beanie has never explicitly been programmed for:

- **Task A:** Teach her a new procedure once. Then give her a variation. Can she adapt?
- **Task B:** Show her a tutorial. Can she perform it without a hard-coded workflow?
- **Task C:** Give her an unfamiliar error. Can she investigate it?
- **Task D:** Change the environment. Can she adapt?
- **Task E:** Give her an incomplete instruction. Can she infer the missing context?
- **Task F:** Let her fail. Can she learn from the failure?
- **Task G:** Teach her something on Windows. Can she transfer the underlying concept to Android/Linux?

Those are much more meaningful AGI measurements.

## The development order actually used

Not all 24 phases sequentially — several develop together:

```
CURRENT ARENA → 0. ARCHITECTURE FREEZE → 1. UNIFIED MIND
→ { MEMORY MODEL, WORLD MODEL, SELF MODEL } (together)
→ GENERAL LEARNING → { images, video, teaching } (together)
→ REASONING / HYPOTHESIS / SIMULATION
→ EMBODIMENT + OS CONTROL
→ CURIOSITY + AUTONOMY
→ SOCIAL + PERSONALITY
→ SELF-REFLECTION + IMPROVEMENT
→ AGI EVALUATION
```

## Target conceptual repository architecture (eventual — NOT restructured yet)

```
arena/
├── mind/            (identity, cognition, reasoning, imagination, attention,
│                     motivation, decision, reflection)
├── memory/          (working, episodic, semantic, procedural, social,
│                     autobiographical, meta)
├── models/          (world, self, owner)
├── learning/        (conversation, demonstration, image, video, web, experience,
│                     causal, transfer, consolidation)
├── perception/      (vision, audio, screen, environment)
├── embodiment/      (windows, linux, macos, android, browser, devices)
├── capabilities/    (existing tools...)
├── communication/   (voice, text, presence)
└── evaluation/      (generalization, learning, transfer, autonomy, regression)
```

**Don't restructure the repository yet.** First map the existing code into this
conceptual architecture. Then decide what can be reused, merged, demoted, or
replaced.

## The restructuring order

1. **Map the entire repository.** Every existing module gets one of: KEEP — already
   fits the AGI architecture. INTEGRATE — useful, but needs to become part of the
   unified Mind. MERGE — duplicate/overlapping intelligence. DEMOTE — useful
   capability but shouldn't make cognitive decisions. REPLACE — architecture
   fundamentally conflicts with the target. MISSING — required concept doesn't
   exist yet. LEGACY — preserve temporarily but stop building on it.
2. **Identify the actual cognitive authority.** Exactly one place where "I am
   Beanie" is represented. Not master_agent, CognitiveRuntime, CoworkerBrain,
   self_evolving_agent, and three planners all independently acting like the brain.
3. **Define the internal state:**

```
BeanieState
├── self
├── owner
├── world
├── working_memory
├── active_perception
├── current_goals
├── beliefs
├── hypotheses
├── plans
├── actions
├── predictions
├── uncertainty
├── emotions/social context
├── learned knowledge
└── attention
```

4. **Build the learning loop around that state.**
5. **Only then reconnect the existing tools and interfaces.**

That way we're not throwing away what's already built — we're changing who is
using it.

## The architectural spine the loop must become

```
                    ┌───────────────────┐
                    │      BEANIE       │
                    │   ARTIFICIAL MIND  │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │     ATTENTION      │
                    └─────────┬─────────┘
                              │
              ┌───────────────▼───────────────┐
              │       INTERNAL STATE          │
              │                               │
              │ World Model + Self Model      │
              │ Memory + Current Context      │
              └───────────────┬───────────────┘
                              │
                       ┌──────▼──────┐
                       │   REASON    │
                       └──────┬──────┘
                              │
                  ┌───────────▼───────────┐
                  │ hypotheses / planning │
                  │ simulation / prediction│
                  └───────────┬───────────┘
                              │
                       ┌──────▼──────┐
                       │    ACT      │
                       └──────┬──────┘
                              │
                       ┌──────▼──────┐
                       │  PERCEIVE   │
                       └──────┬──────┘
                              │
                    reality vs prediction
                              │
                       ┌──────▼──────┐
                       │   LEARN     │
                       └──────┬──────┘
                              │
                       ┌──────▼──────┐
                       │   REFLECT   │
                       └──────┬──────┘
                              │
                         update mind
                              │
                              └──────→ repeat
```

That loop is what should eventually become authoritative. The tools, planners,
voice, vision, Android control, etc. plug into it rather than creating competing
mini-agents.
