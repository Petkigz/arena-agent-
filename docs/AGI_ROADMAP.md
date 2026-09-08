# Arena / Beanie — AGI Roadmap

**Status:** GOVERNING (owner directive, 2026-09-08). This file reframes the project's
optimization target. It sits alongside `docs/OWNER_VISION_CHARTER.md` (behavioral
charter, unchanged) and `docs/QUESTIONNAIRE_BASELINE.md` (see §Measurement tension).

## The reframe

The goal is not to bolt more features onto Arena. The goal is to **evolve what
already exists into one continuously learning artificial mind**.

> **North-star:** Build a local, embodied artificial intelligence that can
> communicate naturally with its owner, perceive the world, reason about
> unfamiliar problems, learn from experience and demonstrations, remember what
> matters, develop an individual personality, operate across devices, and
> continuously improve its ability to accomplish goals.

The important word is **general**. We do NOT optimize Beanie to pass a fixed
collection of tasks. We optimize her ability to **encounter a new task and
figure out how to solve it.**

## Phase 0 — Freeze the architecture before changing it

**Goal: stop the project from drifting further.**

Before adding intelligence, establish what each existing subsystem actually is:

```
Arena
│
├── Mind          perception, cognition, memory, world model, self model,
│                 learning, reasoning, motivation, reflection
├── Body          Windows, Linux, macOS, Android, browser, filesystem, other devices
├── Senses        microphone, screen, camera, images, video, web
├── Communication voice, text
└── Tools         capabilities
```

**Don't delete the existing systems yet.** Classify every module as one of:

`Mind · Memory · Perception · Learning · Body · Tool · Communication ·
Infrastructure · Legacy · Duplicate`

That map is `docs/ARCHITECTURE_MAP.md` (built 2026-09-08). It gives us the
ground truth of the existing codebase before anything is moved, merged, or
removed.

## Measurement tension (open decision for the owner — flagged honestly)

`docs/QUESTIONNAIRE_BASELINE.md` (43/81 → 49/81) is a FIXED battery. The new
north-star says a fixed collection is not the optimization target. Proposed
resolution (needs owner sign-off):

- The questionnaire becomes a **regression diagnostic** (catch capability
  collapses while refactoring), not the objective.
- The primary metric becomes **novel-task outcomes**: every new task the owner
  gives in a live test is one datapoint — attempted honestly / completed /
  verified on the machine. Live tests already generate these (app naming,
  deletion honesty, launches).

## Ground rules carried from the charter (unchanged)

- ask-never-refuse; voice PRIMARY; full OS control incl. Android
- no fabricated success (AGENT_INVARIANTS); every claim machine-verifiable
- don't delete working systems during classification — freeze + map first
- corrections work in chat; charter survives crashes (committed to Git)

## Phase sequencing (owner-directed; Phase 0 in progress)

- **Phase 0 (now):** architecture freeze + classification map. DONE 2026-09-08,
  see `docs/ARCHITECTURE_MAP.md`. Owner review of flagged items pending.
- **Phase 1 (proposed, awaiting owner):** the owner's message defined Phase 0
  fully; Phase 1 content is theirs to set. Candidate directions raised by the
  map: (a) merge/demote the duplicate API surfaces, (b) make the cognition
  spine the only execution path (recorders stop being mistaken for reasoning),
  (c) senses→memory write-path consolidation so experience actually persists
  into retrieval.
