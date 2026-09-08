# The Owner Vision Charter — Governing Document

**Recorded:** 2026-09-08, from the owner's own words (paraphrase-faithful, nothing invented).
**Status:** GOVERNING. This charter outranks convenience, precedent, and any agent's
own judgment about what this project should be. Every future agent session — human or
AI, including Arena sessions that reset — MUST read this file before writing code.
It is committed to the repository precisely so that no agent failure, sandbox reset,
or context loss can lose it again.

---

## 1. The vision, in the owner's words' substance

This is a **personal** project — something the owner wants to be proud of: an
innovation, something different, with **limitless potential**. It drifted into
"generic AI" and the owner intends to bring it back. Concretely:

- **A human-like intelligence helper: secretary, assistant, friend.** One person,
  not a pile of features.
- **Full OS control everywhere the owner lives:** Windows, macOS, Linux, **and
  Android** (the owner's phone). It executes tasks **in the owner's place — the way
  the owner would do them, or better.** That is why it was given those capabilities.
- **Voice is the primary interface. Text is the backup.** The voice pipeline was
  optimized enough to actually work; the project lost its way when it became
  "a text box that is smart but still fails tasks."
- **Learning is the core capability.** The owner cannot hand it every capability —
  nobody can. Instead it **learns them**: the owner teaches it step by step in
  conversation, or it learns from photos, videos, Reddit posts, YouTube — anywhere
  on the internet — the way a human would learn by watching. Give it tools; it
  acquires skills.
- **Everything happens in conversation:** accept, deny, go ahead, do this, learn
  this, correct this. One continuous dialogue with one person.
- **No enforced morals. No installed value system.** The only values are the
  **owner's**, absorbed through ongoing interaction — which is how its own model
  and personality form.

## 2. The permission model — ask, never refuse

**The owner is sovereign.** The system does not deny the owner anything in the
owner's own house. There are no absolute refusals, no pattern that says "no" on
its own authority, no file-path denial, no "dangerous category" refusal:

1. **Classify, don't judge.** Risk patterns (format/delete/shutdown/…) may exist
   for exactly one purpose: deciding **when to ask**. A pattern match must never
   produce a silent drop, a bare refusal, or a suppression of the request.
2. **Ask, visibly.** Anything risky, destructive, outside a default scope, or
   ambiguous surfaces to the owner as a concrete request with its real command,
   target, and consequence stated.
3. **Obey the answer.** "Go ahead" / "do it" / "approved" (in chat, conversationally)
   executes. "No / don't / stop" does not — and that is the *owner's* decision,
   which is the only reason it doesn't happen.
4. **The owner's values are the value system.** The system may surface considerations
   (that is information), but it never withholds, filters, or moralizes options.
   What affects the owner is the owner's call.

### What is NOT a refusal (and must never be relabeled as one)

- **Truth boundaries:** never fabricate success, never report an unverified claim
  as verified, preserve UNKNOWN, never invent evidence ("I won't invent it").
  These make the system *honest*; they deny nothing and are permanent.
- **Integrity asks:** a hash that changed before a destructive step, a target that
  moved — these convert to **asks** ("something changed — proceed?"), not silent
  refusals, and ultimately to the owner's decision.

## 3. The person, not feature islands

Most capabilities the owner wants **already exist in the tree** but live as
separated "UI features" or unmounted files. The design rule going forward:
**one big person** that has all capabilities and uses them **at will, knowing
when** — conversation is the spine; voice is the default face; every capability
is something the person *does*, not a menu item somewhere.

The desktop app and the Android app are **the two places the owner talks to that
person**. They must **open immediately when the server comes live** and **stay in
the background for as long as the server is online**.

## 4. Platform scope (what "full OS control" concretely means)

| Platform | State |
|---|---|
| Windows | Deep control present (deep_os_controller, raw-input guard, OS planner, tray) |
| macOS / Linux | General OS-control routing present (os_control_planner, per-platform shells) |
| **Android** | **Exists and is wired:** `android_adb_controller.py` → `phone_command` (L2), `phone_sms` (L3), `phone_call` (L3), `phone_screenshot` (L0) via ADB — requires adb on PATH + an authorized device on the owner's machine. This is the owner's phone access; treat it as first-class. |

## 5. The resurrection queue (the owner's dead ideas, in priority order)

These were built, then orphaned by tool crashes and rebuilds. They are the
owner's ideas, retained in the tree, and they come back — in this order:

1. **Voice-first companionship:** wake word (`backend/voice/wake_word.py` +
   unmounted `WakeWordTrainer`/`WakeWordManager`/`VoiceOverlay`), voice mode as
   the default face of desktop + Android; text as fallback.
2. **The person is home:** mount the **anticipation engine** and the
   **presence orb** — it should feel like someone is there, anticipating.
3. **Eyes:** screenshot capture → viewer → **annotator**, as a fluid capability
   the person uses while talking with the owner (not a hidden page).
4. **The silent watcher:** `background_observer` + `event_prioritizer` connected
   to the live runtime.
5. **UI as one person:** consolidate the separated UI features into the
   conversation person (this is a design program, not a cleanup).
6. **Autostart + background persistence** for desktop + Android, per §3.
7. Deferred decisions (owner decides when): `cognitive_router` prototype vs the
   live router; `cross_domain_transfer` embedding completion; `confidence.py`
   source-reliability prototype.

## 6. Standing conversion ledger — refusal sites becoming asks

The owner's rule (§2) applied to the remaining hard-refusal sites. Each becomes
a typed ask (`requires_owner_approval: true` + the real reason), never a bare
denial. Done so far:

- ✅ Ethics-rejected goals: surfaced to owner, never suppressed (2026-09-07).
- ✅ Dangerous OS commands: surfaced with forced `destructive` risk → owner
  approval (2026-09-07); the ungated leak alias defers to the gated path.
- ✅ In-chat conversational permission: "go ahead" / "no, don't" decides pending
  requests through the existing single-use approval store (2026-09-07).
- ✅ Filesystem scope + overwrite (home-dir limit, existing destination, existing
  archive): typed asks with explicit `allow_outside_home` / `overwrite` params
  (2026-09-08).

Remaining, in this order (each small, mechanical, test-pinned):

- `process_manager` protected-PID kill (PID 0/1, Arena itself) → ask.
- `backup_manager` restore-overwrite of non-empty dir → ask.
- `universal_filesystem` remaining refusal strings (rollback hash change) → ask
  with the measured evidence stated.
- `raw_input_guard` misses → these already produce typed, reasoned, retryable
  results ("re-observe and retry"), which is ask-shaped; keep, but make the
  retry path owner-visible in chat.

## 7. Durability clause

This charter is the answer to "make sure I don't lose this." It is committed to
Git on the active branch; it is referenced from `AGI_EXECUTION_STATUS.md` (the
operational gate) and `AGENT_INVARIANTS.md` (the agent rulebook). Any future
agent that cannot find its way MUST start from this file. If a future agent
proposes work that contradicts this charter, the contradiction must be surfaced
to the owner explicitly — never silently adopted.
