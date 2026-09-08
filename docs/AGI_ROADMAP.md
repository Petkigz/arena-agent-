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

Don't make memory simply "chat history." Build multiple kinds of memory under one
system: Working, Episodic (experiences), Semantic (facts/concepts), Procedural
(how to do things), Social (people/relationships), Preference (owner's
preferences), Autobiographical (Beanie's history), and **Meta-memory** (what
Beanie knows about what she knows).

The last one is important. Beanie should know: "I remember doing this" versus
"I think I know how to do this, but I've never actually done it."

## Phase 6 — General Learning Engine

The learning loop: experience → observe → interpret → compare with existing
knowledge → detect novelty → form hypothesis → test → observe outcome → update
model → store knowledge → update confidence.

This should work for: conversations, documents, images, videos, websites,
demonstrations, mistakes, successful actions, owner corrections, experiments.

## Phase 7 — Learning From You

This should become one of the easiest things you can do.

You: "Beanie, watch this." Then demonstrate. She observes.
You: "This is how I normally organize these files." She learns.
Then: "So you group them by project first, then type. Is that correct?"
You: "Yes."

Now she has learned a generalized procedure. No forms. No manually creating
skills. No writing JSON. **Conversation is the teaching interface.**

## Phase 8 — Learning From Images and Video

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

Give her an internal UNKNOWN system. She encounters something unfamiliar:
"I don't understand X." Instead of immediately asking you: UNKNOWN → investigate.
She can search, inspect, experiment, compare sources, observe, ask you, try a
harmless experiment, revisit previous memories. Then: uncertainty ↓, knowledge ↑.
This is a critical AGI behavior.

## Phase 10 — Reasoning and Imagination

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

Don't build WindowsTool / MacTool / LinuxTool / AndroidTool as separate
intelligence. Build an **OS abstraction** where Beanie understands concepts such
as: open, close, move, copy, rename, search, install, configure, read, write,
observe, click, type, navigate, communicate. Then the embodiment layer maps them
to the appropriate platform.

That means Beanie can learn "How I accomplish this goal on Windows" and later
generalize the concept to Android or Linux.

## Phase 13 — Continuous Perception

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
