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
> `GET /mind/perception` (35 `/mind/*` paths; 38 routes — the Phase-13
> count of 36 was wrong). Kill switch
> `ARENA_PERCEPTION=0` gates the door drain; the owner surface keeps
> working. Guarded by `tests/test_mind_perception.py` (12 tests; the
> pre-existing `tests/test_perception.py` speech tests stay untouched).

screen, camera, microphone, phone state, desktop state, network/environment →
perception → attention → significance. Beanie shouldn't react to everything. She
should determine: "Is this relevant to what we're doing?" That gives you an
attention system.

## Phase 14 — Attention

> ✅ **LIVE 2026-09-08:** `app/mind/attention.py` — M8 attention
> significance. The arbitrator between perception and thought: what
> deserves thought, in what order, with what advisory. Each perception is
> placed on the roadmap ladder from evidence on the record — owner channel
> → owner_speaking; probe-declared urgency → important_change; loop-judged
> novelty → anomaly; open-unknown touch → unfinished_goal; else
> background_observation — always with reasons. Repeats of already-attended
> content are demoted with a reason ("don't react to everything" applies to
> thought too). `review()` arbitrates only perceptions newer than its
> ledger watermark (nothing is re-thought), and surfaces ONE open unknown
> as learned_curiosity only when nothing more pressing is pending (with a
> cooldown so she doesn't repeat herself). The roadmap's own scenario is
> live: while she is editing the quarterly report, a popup appears →
> advisory "'popup…' — this may interfere with what you're doing (editing
> the quarterly report)", offered to working memory through the same
> channel the Phase-2 brief uses. Attention DECIDES WHAT DESERVES THOUGHT
> — `acted: False` on every verdict; background is an explicit verdict,
> never a silent drop. The Phase-3/4 state skeleton's attention room now
> lights up from the mind organ. Owner-visible: `POST /mind/attention/task`,
> `POST /mind/attention/review`, `GET /mind/attention` (38 `/mind/*`
> endpoints; 41 routes counting dual-verb paths). Kill switch
> `ARENA_ATTENTION=0` gates the door arbitration; the
> owner surface keeps working. Guarded by `tests/test_mind_attention.py`
> (16 tests).

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

> ✅ **LIVE 2026-09-08:** `app/mind/motivation.py` — goals from evidence,
> never from randomness. `gather()` collects candidate goals from SIX real
> evidence sources in her own state: open unknowns (curiosity), parked
> goals waiting for evidence (unfinished — fed by the live
> `parked_goal_recheck` store), goal-shaped owner speech in the door
> ledger (owner goals), attention's important-change/anomaly verdicts
> (environment), VERIFIED-false attempts in the learning ledger (learning
> opportunities — unverified ≠ opportunity), and the anticipation engine's
> learned-rhythm predictions (needs; honest silence until ≥3 occurrences).
> Relevance is a sum of NAMED contributions (source base / recurrence /
> recency / current-task overlap) — inspectable, not vibes; repeated
> evidence compounds recurrence instead of duplicating goals. `propose()`
> builds the owner-facing ask from the goal's own evidence — the roadmap's
> own sentence was live-verified: owner said "organize the project files"
> → "You said: '…organize the project files…'. It's still open — do you
> want me to handle that?" Proposing is a question (`acted: False`);
> accepted goals stay on the books and execute through the normal door,
> where owner authority applies (goal approval ≠ action authorization);
> declined goals are never re-proposed. The door pass auto-proposes only
> when the top candidate earns score ≥5.0 AND a 10-interaction cooldown
> elapsed — autonomous, but careful. Owner-visible: `GET /mind/goals`,
> `POST /mind/goals/propose`, `POST /mind/goals/decide` (41 `/mind/*`
> paths; 44 routes). Kill switch `ARENA_MOTIVATION=0` gates the door
> refresh; the owner surface keeps working. Guarded by
> `tests/test_mind_motivation.py` (15 tests).

Introduce autonomous goals carefully — not randomly generated tasks. Instead:
needs, curiosity, unfinished goals, owner goals, environment opportunities,
learning opportunities → candidate goals → evaluate relevance → prioritize → act.

Beanie can eventually say: "You mentioned yesterday that you wanted to organize
the project. I noticed the files are still scattered. Do you want me to handle
that?" That's useful autonomous behavior.

## Phase 16 — Social Intelligence

> ✅ **LIVE 2026-09-08:** `app/mind/social.py` — the persistent owner
> relationship model. Facets come ONLY from what the owner said (explicit
> markers, evidence carried on every facet): preferences ("I love/prefer/
> hate…"), boundaries ("Never …" — recorded exactly as said), emotion
> cues ("I'm … frustrated/stressed/…"), people ("my wife Anita" →
> registered in the Phase-5 social store with provenance
> `owner_conversation`), and interests from statements about something.
> Repeated observations COMPOUND (times_observed), never duplicate.
> Routines, communication style, and history are MEASURED from the real
> door ledger — most-active hour and style are claimed only with ≥10
> interactions; the observation lane never pollutes the owner's style.
> Live-verified: fresh mind claims NOTHING; seven owner messages later the
> model has 2 preferences, 1 boundary, 1 emotion cue, 1 person (Anita,
> owner's wife), interests, and honest 7-interaction history. She never
> pretends to be human — the model is observed evidence with counts. The
> state skeleton's owner room shows BOTH the legacy user_state snapshot
> and the new relationship surface. Owner-visible: `GET /mind/social`,
> `POST /mind/social/note` (43 `/mind/*` paths; 46 routes). Kill switch
> `ARENA_SOCIAL=0` gates the door pass; the owner surface keeps working.
> Guarded by `tests/test_mind_social.py` (15 tests).
>
> *(Doc repair, same commit: the Phase-15 LIVE-block edit had accidentally
> duplicated the Phase-15 heading over the Phase-16 heading; the roadmap
> structure was restored verbatim.)*

Because the goal is helper + secretary + friend, build an owner model:
preferences, habits, communication style, goals, routines, interests,
relationships, boundaries, emotional/contextual cues, history with Beanie.

This shouldn't mean pretending to be human. It means developing a persistent
relationship model.

## Phase 17 — Personality Development

> ✅ **LIVE 2026-09-08:** `app/mind/personality.py` — the developing
> personality; never a hard-coded mask. The profile is DERIVED on demand
> from her real ledgers: basic identity (the Phase-1 BeanieIdentity record
> — what she starts from) plus traits that only exist with evidence:
> experience profile (learning ledger), epistemic calibration (imagination
> confirmed-vs-refuted), curiosity stance (open/resolved unknowns), her OWN
> communication pattern (replies sampled at the door — ≥5 samples to
> describe it, ≥10 to claim an early-vs-late trend: measurable change),
> values learned from the owner (explicit statements only — the owner's
> values only, never system morals), and adaptation to the owner's measured
> style (Phase 16). An empty life yields the basic identity and the honest
> statement that no traits formed yet. `derive()` snapshots the profile and
> diffs it against the previous snapshot — `changes()` is the verifiable
> record of "Beanie has changed" (live-verified: trait formed → changed →
> stable). The state skeleton's self room gains an additive personality
> surface (Phase-1 identity pin preserved). Owner-visible:
> `GET /mind/personality`, `POST /mind/personality/derive` (45 `/mind/*`
> paths; 48 routes). Kill switch `ARENA_PERSONALITY=0` gates the door
> pass; the owner surface keeps working. Guarded by
> `tests/test_mind_personality.py` (16 tests).

Don't hard-code the personality forever. Start with a basic identity. Then:
interactions → experiences → preferences → communication patterns → values
learned from owner → personality development. You should eventually be able to
notice "Beanie has changed" because her behavior actually changed through
experience.

## Phase 18 — Owner Authority

> ✅ **LIVE 2026-09-08:** `app/mind/authority.py` — the owner's authority,
> not system morals. Five lanes exactly as the roadmap draws them:
> always_allowed / ask_first / never_do / trusted_context / temporary —
> rules come ONLY from the owner's statements ("never delete…", "you can
> always…", "ask before…", "just for today…", "when working on X you
> can…"), restated rules compound with provenance, and Phase-16 boundaries
> seed the never lane automatically. Charter §2 governs every verdict:
> risk patterns (delete/format/send/…) decide WHEN TO ASK and nothing
> else — no silent drop, no bare refusal; an unruled action asks (asking
> is never refusing); ask-first opens a TYPED `requires_owner_approval`
> ask with the real reason; `answer()` obeys the owner — "go ahead"
> executes-forward, and a declined ask is the owner's decision, the only
> reason it doesn't happen. Never-lane verdicts quote the owner's rule
> back and note authority ≠ intelligence (she understands HOW even where
> the lane withholds authorization). Live-verified: never beats always;
> trusted contexts apply only inside their context; honesty boundaries
> are permanent truth rules, not refusals, and are not owner-policy here.
> Owner-visible: `GET /mind/authority`, `POST /mind/authority/check`,
> `POST /mind/authority/answer` (48 `/mind/*` paths; 51 routes). Kill
> switch `ARENA_AUTHORITY=0` gates the door pass; the owner surface keeps
> working. Guarded by `tests/test_mind_authority.py` (17 tests).

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

> ✅ **LIVE 2026-09-09:** `app/mind/reflection.py` — the bridge between
> experience and development. After important (VERIFIED) experiences she
> answers every question the roadmap asks, and every answer is drawn from
> evidence already on record — never narrated: what happened; what she
> believed (the imagination ledger's prediction for that action, or an
> honest "no simulation recorded" — nothing invented); whether she was
> correct (the verifier's word only — True/False, and a missing verdict
> stays UNKNOWN, never guessed); what surprised her (a refuted prediction
> or declared surprisal ≥ 0.5); what she learned (the learning loop's own
> record); whether to change her model (refuted prediction → update
> expectations; a REPEATED verified failure → registered as an open
> unknown with curiosity, "why does this keep failing"; a single failure
> is data, not a pattern; verified success → the model holds); and
> whether to remember this (the learning loop's own stored/rehearsed
> decision). The door reflects on cycles whose verifier returned a
> definite verdict — unverified cycles are not important yet, so no
> reflection. Reflecting performs nothing (`acted: False`). Live-verified:
> verified success keeps the model; one failure is data; the second
> verified failure of the same thing becomes an open unknown the mind
> keeps working on. Owner-visible: `GET /mind/reflection`,
> `POST /mind/reflection/reflect` (50 `/mind/*` paths; 53 routes). Kill
> switch `ARENA_REFLECTION=0` gates the door pass; the owner surface
> keeps working. Guarded by `tests/test_mind_reflection.py` (19 tests).

After important experiences: What happened? Why? What did I believe? Was I
correct? What surprised me? What did I learn? Should I change my model? Should I
remember this? This becomes the bridge between experience and development.

## Phase 20 — Self-Improvement

> ✅ **LIVE 2026-09-09:** `app/mind/improvement.py` — the full loop the
> roadmap draws: detect capability gap → investigate → design → implement
> → test → measure → retain/revert. Detection is evidence only — the SAME
> thing failing verified 2+ times in the learning ledger (a single
> failure is data, not a gap); Phase-19's registered unknowns
> corroborate. Investigation reports the record, nothing more. Design
> records a proposal (mechanism `capability_synthesis`, hypothesis,
> baseline failure count, measurement criterion) — designs never
> execute. Implementation runs the EXISTING self-evolving engine
> (`SelfEvolvingAgent`, the wired verify-before-install loop) as ONE
> mechanism, and claims only its typed word: sandbox-tested before
> install, hotloaded only if green; an offline model or a rejected
> attempt is recorded as the honest failure it is. Measurement compares
> NEW verified experience to the baseline — success with no new failures
> = retained; 2+ new failures = reverted FOR REAL (live registry entry
> popped, environment revision bumped, files removed); anything less =
> awaiting evidence, never guessed. The door detects and PROPOSES when a
> verified failure completes a pattern — it never implements; execution
> stays an explicit surface act under the owner's authority.
> Live-verified offline: second failure proposes; synthesis fails
> honestly ("no usable model completion"); measurement awaits.
> Owner-visible: `GET /mind/improvement`, `POST /mind/improvement/propose`,
> `POST /mind/improvement/implement`, `POST /mind/improvement/measure`
> (54 `/mind/*` paths; 57 routes). Kill switch `ARENA_IMPROVEMENT=0`
> gates the door pass; the owner surface keeps working. Guarded by
> `tests/test_mind_improvement.py` (19 tests).

Only after the previous pieces work: detect capability gap → investigate → design
improvement → implement → test → measure → retain/revert. The existing
self-evolving/code-generation infrastructure can become part of this — one
mechanism of self-improvement, not the definition of intelligence.

## Phase 21 — Model Evolution

> ✅ **LIVE 2026-09-09:** `app/mind/evolution.py` — model evolution in
> the roadmap's three lanes, each honest about what it is. **Fast:**
> already live at the door (learning ledger, durable memory, world
> model, self model) — the organ REPORTS the real wiring, never
> duplicates it. **Medium:** the door consolidates automatically once
> enough new verified learning accumulates, delegating to the WIRED
> `ConsolidationCoordinator` engine (conflict replay, gists from
> repeated VERIFIED success, calibration refresh) and claiming only its
> audited telemetry — consolidation APPENDS, raw experience is never
> deleted (the forgetting guard). **Long:** her OWN verified ledger
> becomes a training dataset (JSONL, provenance per row — unverified
> material never trains the model, an empty ledger exports nothing,
> never padded), evaluated with deterministic sufficiency rules (volume
> floor + both outcome classes; arithmetic, never optimism); the
> optional adapter lane (`LoraManagerTool` / `scripts/train_lora.py`)
> stays where the roadmap puts it — training runs on the owner's GPU
> machine, and the organ reports readiness, never a trained model.
> Live-verified: threshold-triggered consolidation at the door; dataset
> export with provenance; honest "not sufficient yet" evaluation.
> Owner-visible: `GET /mind/evolution`, `POST /mind/evolution/consolidate`,
> `POST /mind/evolution/dataset`, `POST /mind/evolution/evaluate`
> (58 `/mind/*` paths; 61 routes). Kill switch `ARENA_EVOLUTION=0`
> gates the door pass; the owner surface keeps working. Guarded by
> `tests/test_mind_evolution.py` (13 tests).

Only now work on: base model + memory + world model + self model + learned
examples + personality + optional LoRA. The model itself doesn't need to be
retrained after every interaction:

- **Fast learning:** memory/world-model updates.
- **Medium-term learning:** skill/concept consolidation.
- **Long-term learning:** dataset creation + evaluation + optional adapter training.

That prevents catastrophic forgetting and unnecessary retraining.

## Phase 22 — Voice-first Beanie

> ✅ **LIVE 2026-09-09:** `app/mind/presence.py` — voice-first presence.
> The presence vocabulary IS the design system's own state machine
> (`design/tokens.json` → `beanie.states`: idle / listening / thinking /
> speaking / working / acting / observing / success / error / offline) —
> one shared vocabulary, rendered per platform; states outside it are
> refused, never invented, and with no activity on record she reports
> idle HONESTLY (never pretends to be busy). The CONTEXTUAL WINDOW is
> the complicated information existing WHEN NEEDED, not permanently:
> the recent conversation (the door's entry ledger), open asks awaiting
> the owner's answer, active goals, top open unknowns, model-changing
> lessons — each bounded, each from a real ledger, each honest when
> unavailable. The VOICE-PRIMARY DOOR sends a transcript through the ONE
> mind exactly like any modality; the settled state is the verifier's
> word (verified success → success; verified failure → error; no verdict
> → nothing claimed). The voice pipeline (`backend/voice` orchestrator:
> wake word, VAD, STT, TTS) stays wired as a callable — it calls this
> organ; one typed door, one continuous conversation. Live-verified:
> voice turn → verified success → green Success presence; open asks
> surface in the window with their reasons. Owner-visible:
> `GET /mind/presence`, `POST /mind/presence/note`,
> `POST /mind/presence/voice` (61 `/mind/*` paths; 64 routes). Kill
> switch `ARENA_PRESENCE=0` gates the door pass; the owner surface keeps
> working. Guarded by `tests/test_mind_presence.py` (15 tests).

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

> ✅ **LIVE 2026-09-09:** `app/mind/embodiments.py` — the bodies of the
> one mind. A body ANNOUNCES itself (kind from the fixed vocabulary
> desktop / android / web — unknown kinds are refused, never invented;
> re-announce updates, never duplicates) and is a presence point of the
> ONE mind, never a separate assistant. Aliveness is DERIVED from
> heartbeats against a TTL — active while it beats, silent when it
> stops, never assumed. `broadcast_presence` sends the SAME presence
> event to every alive body — one mind, one message; silent bodies are
> skipped and said so, deliveries never faked. Bodies PULL their queue
> (`events`) and `acknowledge` delivery themselves; the transport stays
> whatever each client speaks. `note_execution` records WHICH body's
> hands performed an action — provenance, because bodies are hands,
> never brains. The device-pairing registry
> (`backend/api/device_routes.py`) stays wired as the transport-level
> pairing layer. The door broadcasts the settled presence state to
> every alive body after a verified cycle — background presence, one
> continuous conversation. Live-verified: desktop + android both hear
> the same verified-success state and acknowledge; a rewound heartbeat
> makes a body silent and the next broadcast skips it honestly.
> Owner-visible: `GET /mind/embodiments`, `POST
> /mind/embodiments/announce`, `POST /mind/embodiments/heartbeat`,
> `GET /mind/embodiments/events`, `POST /mind/embodiments/acknowledge`,
> `POST /mind/embodiments/execution` (67 `/mind/*` paths; 70 routes).
> Kill switch `ARENA_EMBODIMENTS=0` gates the door pass; the owner
> surface keeps working. Guarded by `tests/test_mind_embodiments.py`
> (14 tests).

```
Arena Server
      ├──────────→ Desktop Beanie ── background presence
      └──────────→ Android Beanie ── background presence
```

Both are clients of the same Mind. Not two separate assistants.

## Phase 24 — AGI Evaluation

> ✅ **LIVE 2026-09-09:** `app/mind/evaluation.py` — measure
> GENERALIZATION, not test counts. All seven task families run as
> DETERMINISTIC proxies against her real organs — never an LLM jury,
> never a staged pass: **A** teach once → variation (adaptation scored
> on real term evidence); **B** tutorial → the steps she performs are
> recovered from what was actually LEARNED (ledger recovery, never
> hidden knowledge); **C** unfamiliar error → becomes a registered
> UNKNOWN (investigation starts with honest ignorance); **D**
> environment change → the registry revision advances and stale
> availability is dropped (re-probe, never dead facts); **E**
> incomplete instruction → correctness stays UNKNOWN (never fabricated
> completion); **F** verified failure → called WRONG with counsel
> (failure becomes material); **G** teach on one body → the OS concept
> layer transfers it, resolved on the target body or flagged as a
> VISIBLE gap, never a fabricated capability. Each task yields a score
> in [0,1] with evidence; the overall number is a proxy measurement of
> generalization — meaningful, and honestly labeled a proxy, never
> proof. First live report card: A 0.83 / B–F 1.00 / G 0.00 (the
> sandbox's empty capability manifest leaves transfer gaps VISIBLE).
> Owner-visible: `GET /mind/evaluation`, `POST /mind/evaluation/run`
> (69 `/mind/*` paths; 72 routes). Kill switch `ARENA_EVALUATION=0`
> gates the run surface. Guarded by `tests/test_mind_evaluation.py`
> (12 tests).

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

## Beyond the roadmap — growth from the 2026-09-09 architecture audit

After Phases 0–24 went LIVE, the owner asked for an honest audit against
a 27-question + 5-domain general-intelligence checklist. The audit
scored her from the actual code and surfaced the gaps. The first gap is
now closed:

> ✅ **LIVE 2026-09-09:** `app/mind/scrutiny.py` — the devil's advocate
> (audit item #25: "a dedicated subroutine that actively tries to
> disprove its own favorite conclusions… true intelligence doubts
> itself"). ``scrutinize(conclusion)`` argues the OPPOSITE case using
> only evidence from her own ledgers — verified failures, reflections
> where the verifier called her wrong, refuted predictions, open
> improvement gaps, admitted unknowns — never invented
> counter-arguments. Any counter-evidence CONTESTS the conclusion; none
> found means it survived THIS scrutiny, reported exactly as the
> absence of a counter-case, never proof. The door runs the advocate on
> VERIFIED SUCCESSES — success in the face of contrary history is where
> survivorship bias bites. Doubts, never acts, never vetoes (the
> decision belongs to the owner's authority and the verifier's word).
> Owner-visible: `GET /mind/scrutiny`, `POST /mind/scrutiny/scrutinize`
> (71 `/mind/*` paths; 74 routes). Kill switch `ARENA_SCRUTINY=0`.
> Guarded by `tests/test_mind_scrutiny.py` (13 tests).

> ✅ **LIVE 2026-09-09:** `app/mind/beliefs.py` — false-belief theory of
> mind (audit item #20: "hold that you hold a false belief, and choose
> to guide you WITHOUT correcting you"). What the owner believes is
> captured from markers in the owner's OWN words ("I think…", "I
> believe…") — never mind-read — and held SEPARATELY from what the
> evidence shows. ``check(subject)`` sets the belief against her own
> VERIFIED record: corroborated, CONTESTED (a false belief, detected in
> either direction), or unknown — said plainly. ``guide(subject)`` is
> the behavior the audit asked for: a contested belief is met with
> acknowledgment ("you told me you believe…"), her own record, and the
> decision left to the owner — never "you are wrong"; a corroborated
> belief is affirmed; an unknown one offers to find out together. The
> door captures beliefs from owner speech; she models the owner's mind,
> she never edits it. Owner-visible: `GET /mind/beliefs`,
> `POST /mind/beliefs/note`, `POST /mind/beliefs/check`,
> `POST /mind/beliefs/guide` (75 `/mind/*` paths; 78 routes). Kill
> switch `ARENA_BELIEFS=0`. Guarded by `tests/test_mind_beliefs.py`
> (16 tests).

> ✅ **LIVE 2026-09-09:** `app/mind/idle_replay.py` — dream-like
> consolidation (audit item #18: "when nothing is asked of her, does
> she replay recent experience offline and consolidate it?").
> ``replay()`` is her quiet pass over everything NEW since the last
> replay (a watermark kept in the replay ledger, so it survives
> restarts): related experiences are gathered into THREADS by
> vocabulary overlap, and each thread is judged ONLY by the verifier's
> own tally — mostly verified successes → strengthen, mostly verified
> failures → revisit, mixed or no verdict → open; improvement gaps
> still open are named, not re-argued. The door measures the quiet
> between messages (``ARENA_IDLE_REPLAY_SECONDS``, default 1800): when
> the owner returns after the window, the consolidation runs — she
> dreams in the quiet BETWEEN messages. Nothing is invented while she
> dreams: she replays only what is already in her ledgers, and replay
> describes — never acts, never edits the record. Owner-visible:
> `GET /mind/replay`, `POST /mind/replay/run` (77 `/mind/*` paths;
> 80 routes). Kill switch `ARENA_IDLE_REPLAY=0`. Guarded by
> `tests/test_mind_idle_replay.py` (16 tests).

> ✅ **LIVE 2026-09-09:** `app/mind/stakes.py` — stakes-based effort
> (audit item #22: "does she try equally hard at everything, or does
> effort follow stakes?"). ``assess(task)`` computes what a request
> costs if it fails from FOUR deterministic signals out of her own
> record — never vibes: risk markers in the words themselves
> (destroying data, moving money, contacting people on the owner's
> behalf); owner emphasis ("important", "carefully", …); her OWN
> verified failure history on the topic — where she has failed
> verified 2+ times, casual effort is least affordable; and the
> owner's authority rules touching the topic (read-only — judging
> stakes never opens asks). Score → level: ROUTINE (0–1), CAREFUL
> (2–3), CRITICAL (4+), and each level carries a concrete, NESTING
> EFFORT PLAN — what extra care the level buys, up to "run the shadow
> advocate before relying on a conclusion" and "confirm irreversible
> steps with the owner first". The door assesses every non-empty
> request; low stakes are honest too — not everything needs ceremony.
> The organ assesses and records; it never executes, never vetoes —
> the decision belongs to the owner's authority. Owner-visible:
> `GET /mind/stakes`, `POST /mind/stakes/assess` (79 `/mind/*` paths;
> 82 routes). Kill switch `ARENA_STAKES=0`. Guarded by
> `tests/test_mind_stakes.py` (16 tests).

> ✅ **LIVE 2026-09-09:** `app/mind/paradigms.py` — ontological
> paradigm shifts (audit item #21: "can she overturn a deep assumption
> when verified evidence breaks it, or does she only patch exceptions
> forever?"). Patching the same broken rule once is adaptation; the
> SECOND verified counter-example means the rule itself was wrong.
> ``assume(statement)`` captures universal claims from markers in the
> owner's own words ("always", "every time", "whenever", "never") —
> no markers, nothing captured; imperatives addressed at HER are the
> authority organ's lane, not ontology. ``generalize(subject)`` lets
> her form a PROVISIONAL universal from her own verified tally (3+
> verified successes, zero failures — "has held so far"). ``scan()``
> sets every held paradigm against the verified ledger — matching on
> content terms only, so "always" never dilutes the overlap: positive
> universals are broken by verified failures, negative universals by
> verified successes. One counter-example → STRAINED; two or more →
> OVERTURNED, recorded exactly once with the counter-evidence and a
> replacement that names the shift ("no longer universal — broke
> against 2 verified counter-example(s); treat it case-by-case, not as
> law"). The door captures universals and scans on every pass, so the
> shift happens the moment the evidence arrives. The organ describes;
> it never executes. Owner-visible: `GET /mind/paradigms`,
> `POST /mind/paradigms/assume`, `POST /mind/paradigms/scan`
> (82 `/mind/*` paths; 85 routes). Kill switch `ARENA_PARADIGMS=0`.
> Guarded by `tests/test_mind_paradigms.py` (17 tests).

> ✅ **LIVE 2026-09-09:** `app/mind/physics.py` — intuitive physics
> (audit Domain A: "does she hold expectations about how the physical
> world behaves — and notice when the world violates them?"). The
> honest version for a desk-bound mind is not a rigid-body simulator;
> it is the OLDEST physical law applied to her own record —
> PERSISTENCE: what she observed is still so, until a recorded event
> changes it. ``place(subject, state)`` records where the world is;
> ``expect(subject)`` says what persistence implies RIGHT NOW, citing
> the observation it stands on — or says plainly that physics has
> nothing to say about what she has never seen. ``report(subject,
> observed)`` sets the world against the expectation: match →
> CONFIRMED; mismatch → VIOLATION with no recorded cause — physical
> surprise, recorded exactly as it is, handed to curiosity as an open
> unknown, and staying VISIBLE until ``explain(subject, cause)``
> supplies the missing event. The world outranks the model: after a
> violation the state is the observation. The door's grammar is
> strict — placement reports ("the keys are on the hook") and
> disappearance reports ("the keys are gone") only; anything else is
> ignored, never guessed. Owner-visible: `GET /mind/physics`,
> `POST /mind/physics/place`, `POST /mind/physics/report`,
> `POST /mind/physics/explain` (86 `/mind/*` paths; 89 routes). Kill
> switch `ARENA_PHYSICS=0`. Guarded by `tests/test_mind_physics.py`
> (18 tests).
>
> With this organ every audit gap she was meant to close IS closed:
> scrutiny (#25), false-belief theory of mind (#20), idle replay
> (#18), stakes-based effort (#22), ontological paradigm shifts (#21),
> and intuitive physics (Domain A) are all LIVE. Mortality (#26)
> remains deliberately absent unless the owner asks for it.

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
