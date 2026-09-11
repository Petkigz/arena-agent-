# Arena AGI Execution Status

**Date:** 2026-09-09  
**Branch:** `arena/01a08661-arena-agent`

**Purpose:** A chronological, repository-grounded work queue. This document separates “the path exists” from “the behavior is robustly demonstrated.” It is the operational companion to `AGI_GAP_IMPLEMENTATION_PLAN.md`.

## Current owner-directed gate

**2026-09-09 — Beanie AGI roadmap active; Phases 0–24 ✅ complete —
the full roadmap is LIVE — post-roadmap growth from the architecture
audit COMPLETE, including #26 mortality at the owner's request.
Pre-go-live: the CONTINUITY NET is LIVE; go-live hardening round 1
from the owner's first live Windows run is COMPLETE.**
Go-live hardening round 1 (owner's first live run on Windows,
2026-09-09 — real logs, real failures, every fix traced to evidence):
(1) THE MODEL LANE SERVES HER LOADED MODELS — a pinned id is now
SATISFIED by a loaded id with extra title words (token-subsequence,
unique match only; `qwen2.5-9b-instruct` matches her loaded
`…-9b-instruct-…` and never crosses sizes), LM Studio's
"Please load the model … first" 400 now triggers the existing
retry-with-a-loaded-model ladder instead of falling to simulation, and
the coding model LOADS ON DEMAND and EJECTS afterwards
(`CODE_MODEL_AUTOSWAP`, provider TTL backstop; a coder the owner
loaded herself is never ejected). (2) CONVERSATION DELETIONS
SYNCHRONIZE — the web store only filtered local state and the backend
had no delete at all; now `db.delete_conversation` + WS
`delete_conversation` → ack + `conversation_deleted` broadcast →
web/desktop drop it everywhere (no resurrection at the next hydrate).
(3) DESKTOP — real Qt runs exposed four pinned-but-broken contracts:
ContextPanel exposes `body` and hides it collapsed (set_collapsed is
silent by default; the user's toggle notifies), the sidebar gained the
Chats item, and the review bar's toggle reads the explicit hidden
state (`isHidden()`, not ancestor-dependent `isVisible()`). (4)
WINDOWS PORTABILITY of the suite — fixtures set USERPROFILE beside
HOME (Windows' Path.home() ignores HOME), sources are read as UTF-8
(cp1252 default broke two sweeps), unwritable-place tests use a path
under a file (writable on Windows via `/proc/...`), home-scope
fixtures are sandboxed (her 200k-file profile made walker indexes
partial and non-deterministic), and .py launches spawn through the
interpreter so the pid is honest. (5) AN EXPLICIT PATH IS NEVER
FUZZY-SUBSTITUTED — her live run 'resolved' a non-existent
`C:/pics/w.jpg` to an unrelated photo and set it as the wallpaper;
operand completion now resolves bare names only. Guarded by
`tests/test_llm_code_autoswap.py` (11 tests),
`tests/test_conversation_delete_sync.py` (7), the desktop suites (31
under real PySide6) and the fixed platform suites.
Go-live hardening round 1b (same live run, second log window
17:12–18:12 — her checkout was still pre-fix, so this window also
CONFIRMS round 1's targets reproduced exactly): the parked 'kaba'
goal self-closed after 3 unverified rechecks (bounded, as designed),
but the log exposed THE SEARCH-LOOP ROOT CAUSE: a term the index can
never match exactly ('kaba' — fuzzy 'kanban' candidates don't satisfy
`lookup_exact`) misses the index on EVERY query, so every repeat
re-walked all 5 drives (~500k entries, ~40s/pass) — 3 passes per
recheck, every recheck, for an hour (and pushed the hourly cycle into
APScheduler overlap skips). Fix: `UniversalFilesystem` now replays a
completed walk's results for an identical query inside a bounded TTL
(`_WALK_RESULT_TTL_S` = 300s, existence-verified on replay; misses are
NEVER cached so a file saved right after a miss is still found by the
next query; kill switch `ARENA_WALK_CACHE=0`). Guarded by 5 new tests
in `tests/test_search_autonomy.py::TestWalkResultCache` (43/43 in the
file, 203/203 across all 22 search-path suites, full suite 3827
passed / 0 failed).
Go-live hardening round 2 (owner transcript 2026-09-09, increment
approved with her 'go'): (1) INFO QUERIES ROUTE TO A REAL WEB SEARCH —
'the weather in kampala now' carries no control verb, so the tool
matcher returned None and the turn degraded into a conversational
deflection while the parked goal 'i wanted to search something'
web-searched the literal word 'something' (Bing, 0 results). Obvious
web-lookup subjects (weather/forecast, news, exchange rates, stock
prices, match scores) now route deterministically to `web_search`
BEFORE the control-verb gate, with the utterance itself as the cleaned
query — but never when a control verb competes ('open the weather app'
stays a launch) or a file operand is present ('weather_report.pdf' is
file work). Kill switch `ARENA_INFO_QUERY_SEARCH=0`. (2) A FOLLOW-UP
SUPERSEDES ITS AMBIGUOUS PARKED GOAL — when the owner sends a
substantive turn in a conversation holding a parked goal whose object
is a placeholder ('something'/'stuff'/'things'), the stale vague trace
leaves the recheck queue as `superseded_by_followup` (honest: nothing
achieved, `goal_verified` stays 0) and the follow-up's own trace
carries the intent; greetings, short turns, concrete goals, other
conversations, and recheck messages are never touched. Kill switch
`ARENA_PARKED_SUPERSESSION=0`. Guarded by
`tests/test_search_intent_routing.py` (17 tests). Known pre-existing
flake, NOT from this increment (reproduced on pristine 0d730c9):
`test_observation_routing.py::test_answer_branch_uses_observation_evidence`
fails under a specific 62-file subset ordering (CognitiveRuntime
singleton leakage); it passes standalone, in the full-suite order, and
on the owner's runs.
Go-live hardening round 3 (owner-pasted external audit 2026-09-09, run
against her machine with a LIVE server on :8000 — her 4 suite failures
reproduced and root-caused): (1) RESET-SCRIPT PROTECTION IS NOW
DATABASE-AWARE — the script detected a live server ONLY by probing
127.0.0.1:8000/health (a server on any other port was invisible and
could be reset under; an unrelated process on 8000 could block a
legitimate reset). The server now touches `data/server.heartbeat.json`
every 10s (`app/utils/heartbeat.py`, wired in the lifespan, removed at
shutdown, kill switch `ARENA_SERVER_HEARTBEAT=0`); the script refuses
while the heartbeat is fresh (45s window), requires Arena's own
`arena-backend` marker in the probe response, and takes
`ARENA_HOST`/`ARENA_PORT` overrides. Its tests are hermetic: the
subprocess probe targets a closed free port (monkeypatch cannot cross
the process boundary — with her real server up, three tests failed;
with a dummy Arena on :8000 they now pass 11/11). (2) THE
COMPETING-HYPOTHESES TEST IS ORDER-FREE — both observations score 0.9;
the ranking tie-breaks on timestamps then a RANDOM hypothesis_id, and
on Windows `datetime.now()` can return identical timestamps for both
upserts, making the top candidate a coin toss (her failure; 25/25
passes on Linux microsecond clocks). The test now pins the safety
invariant — both candidates retained, nothing synthesized, never
ANSWER — not which equal-score candidate ranks first. Audit claims
verified false: no `cv2` distribution exists on PyPI (the earlier
`pip uninstall cv2` advice is corrected) and the repo contains no
shadowing `cv2.py`; her OpenCV breakage is a broken/conflicting
install in her interpreter. Audit claims already shipped before it was
written: the multi-drive re-walk loop (walk-result cache, 0d730c9) and
stale parked-goal rechecks (follow-up supersession, 89b8a5c). Open,
proposed as next increments: well-known-folder search scoping ('my
documents folder' must not walk 5 drives), the media-playback
capability contract, a local integration smoke suite beside the
deterministic one, and honest reclassification of shape-only
multimodal / over-mocked closed-loop / Android token tests.
Go-live hardening round 4 (second owner-pasted audit 2026-09-09 — its
headline finding verified TRUE and fixed): THE CONFIG LOADER'S
`env_prefix` IS `LPA_`, so every documented bare switch name
(`ARENA_PARKED_RECHECK=0`, `MAIN_MODEL=auto`, `AUTONOMY_MODE=off`, …)
was silently ignored by pydantic settings while half the codebase's
kill switches read `os.environ` directly under those same bare names —
two incompatible conventions, and owner-facing instructions (including
this repo's own earlier guidance) had no effect. Fixed at the loader:
a second env source accepts bare names for the `ARENA_*` switches and
the model/autonomy knobs (`MAIN_MODEL`, `FAST_MODEL`, `CODE_MODEL*`,
`AUTONOMY_*`); `LPA_` wins when both are set; generic fields (`DEBUG`,
`DB_PATH`, `APP_NAME`, …) stay prefixed-only so stray machine env vars
cannot hijack them (`app/config.py::_BareNameEnvSource`, pinned by
`tests/test_config_env_naming.py`, 6 tests). Same audit: the manifest's
dedicated `weather` tool (takes a city) now wins over generic
web_search when a city is named ('the weather in kampala now' →
`weather{city: 'kampala'}`); cityless weather asks still fall through
to web_search (`tests/test_search_intent_routing.py`, now 19 tests).
Audit claims verified but deliberately NOT changed this round (each
proposed as its own increment): persisted recheck-marker pollution in
old rows (the live strip already prevents NEW pollution), recheck
evidence-only reconciliation beyond launch goals, deterministic
app-launch routing for explicit 'open X' commands, completion-honesty
diagnostics that name the execution-blocking reason, and a local
integration smoke suite.
Go-live hardening round 5 (third owner-pasted audit 2026-09-09 —
architecture-level; its one precisely actionable finding shipped):
'waiting_for_evidence' HAD BECOME A GENERIC FAILURE BUCKET — an
unresolvable app name, an underspecified intent, a missing capability,
a pending approval, and a dead model provider all parked under the
same state, and the auto-recheck replayed the full chat cycle for
cases re-running can never fix (looping 'Have you tried Task Manager?'
on 'open RichST TV'). Parked goals now carry a TYPED REASON
(`goal_park_reason`: OBSERVATION_PENDING, NEEDS_CLARIFICATION,
TARGET_AMBIGUOUS, CAPABILITY_UNAVAILABLE, AUTHORIZATION_REQUIRED,
PROVIDER_UNAVAILABLE — `app/cognition/goal_lifecycle.py::classify_park_reason`,
signal-first with the honest legacy default). ONLY observation-pending
goals — and legacy rows predating the taxonomy, which keep the bounded
3-attempt behavior — are eligible for evidence rechecks; the others
stay parked and visible with their reason until the owner acts. The
lifecycle state itself is unchanged (every existing reader keeps
working; the reason is an additive column with a pre-migration
fallback), the owner-visible status line keeps the familiar
'waiting_for_evidence' wording and ADDS the reason plus whether an
auto-recheck could ever help. Guarded by
`tests/test_park_reason_taxonomy.py` (10 tests). The audit's broader
thesis — the tool matcher must become one input to capability
discovery rather than the behavioral center — is directionally
accepted and explicitly NOT a one-commit change; proposed as a gated
program. Audit state-mapping note: VERIFIED_SUCCESS = existing
'achieved'+goal_verified, SUPERSEDED_BY_NEWER_REQUEST = existing
'superseded_by_followup', ABANDONED = the bounded 3-attempt honest
close.

**Phase 0 of the owner's mind-platform plan (2026-09-10) — safe
deterministic operating baseline, COMPLETE.** The owner adopted a
systematic plan ("build a persistent, evidence-driven mind substrate;
make every decision flow through it; prove each learning capability
generalizes") whose Phase 0 freezes unsafe/noisy behavior before any
new cognition is built. Shipped: (1) SAFE DEFAULTS — parked-goal
auto-recheck is now OFF by default (`ARENA_PARKED_RECHECK=0`; it stays
owner-invoked until the Phase 1 typed event ledger replaces chat
replay) and the autonomous cycle is OFF (`AUTONOMY_MODE=off`); both
remain one env var away, and the shutdown-cooperation test now enables
supervised mode explicitly instead of inheriting it. (2) STARTUP
READINESS — one honest block at boot and `GET /readiness`: provider
reachability with ACTUALLY-loaded model ids (native `/api/v0/models`
state — the distinction behind the 14B-over-9B JIT-load incident),
configured-vs-resolved ids per lane (a pinned-but-unloaded model is
called out at startup, not at the first 400), enabled background jobs,
authority posture (mode/auth/elevation), manifest tool count, and
precise OpenCV/browser readiness (the cv2-stub failure mode gets its
exact repair instruction). Fail-open probes, 2s timeout,
`ARENA_READINESS=0` skips the log (`app/utils/readiness.py`,
`tests/test_startup_readiness.py`, 10 tests). (3) HEADLESS GUARD — UI
auto-open skips automatically on display-less environments (no
DISPLAY/WAYLAND_DISPLAY on Linux); Windows/macOS keep the owner's
merged desktop lifecycle (decision 2026-09-08) untouched. Phase 0 exit
criteria audit: no autonomous replays by default ✓; owner sees what
runs and why ✓; no duplicated recheck prefixes (pinned since 09-08 +
round 3) ✓; tests independent of a live server on :8000 (round 3
hermetic reset tests) ✓; one tracked event per request — PARTIAL: the
typed park reasons (round 5) are the first brick, the full event
ledger is Phase 1, gated on the owner's go. Known pre-existing
order-flakes (reproduced on pristine 57a0f8e, NOT from Phase 0): two
code-lane tests in `test_task_execution_honesty.py` under a specific
72-file subset ordering; they pass standalone and in full-suite order.

**Phase 2 of the owner's mind-platform plan (2026-09-10) — authoritative
world-model identity resolution, COMPLETE.** "Beanie acts on stable
entities, not repeated string guesses." Built by EXTENDING the existing
organ (app/cognition/world_model.py + app/mind/world_facade.py — one
cognitive authority), not duplicating it: `WorldModel.resolve_candidates`
returns ranked COMPETING HYPOTHESES, each with confidence + evidence
(exact 1.0 → normalized 0.97 → alias ×0.97 → token containment 0.8 →
difflib ≥0.6 ×0.85; certainty capped at 0.999 — never absolute);
`add_alias` binds a spoken form to its canonical entity permanently with
provenance observations; `why(entity_id)` answers "why do you believe
this?" with the timestamped, source-tagged evidence trail. New
`app/mind/app_identity.py` applies the policy: single strong candidate
(≥0.9 or ≥0.12 margin) resolves; competing candidates produce a focused
selection question (the word 'ambiguous' types the park reason as
TARGET_AMBIGUOUS via the round-5 taxonomy); nothing matching falls
through to the legacy inventory matcher. The launch seam in
`master_agent.execute_proposal` now resolves BEFORE the inventory/fuzzy
fallback can derail the request (the six-RichST-instances class of
incident): ambiguous → ask, never launch; resolved → launch the
CANONICAL name; successful legacy launches TEACH the binding
(remember_app + alias + process-state observation). Freshness was
already right in the organ (get_entity_state max_age →
current/stale/unknown) and is pinned by test: a 3-day-old 'running' is
stale, never current fact. Kill switch `ARENA_APP_IDENTITY=0` restores
the pre-Phase-2 path exactly; every seam fail-opens (a broken world
model degrades to the legacy matcher — verified by test). 20 new tests
(tests/test_world_identity_resolution.py) + 530-test affected sweep
clean. Scope honesty: the store's identity layer is kind-agnostic (all
ontology types resolve through it), but only the APPLICATION path is
wired into execution this round; files/devices/projects wiring is the
next increment, and the Phase 1 typed Event ledger remains queued on
the owner's go.

**Phase 4 of the owner's mind-platform plan (2026-09-10) — action,
authority, and verification contracts, COMPLETE.** "Capability,
permission, action, and outcome are separate facts." New
`app/cognition/action_contract.py` assembles the SEVEN FACTS per
proposal: capability (manifest authority — an unresolvable capability
is a concrete blocker naming it), target (Phase 2 identity), authority
(PolicyEvaluator stays the authority of record), expectation (declared
observable effect), verification (declared probe: process / file-exists
/ none), reversibility (undo path), outcome (ExecutionReceipt with
machine-observed evidence). The single decision: clear + allowed →
`act` with NO question (the owner never repeats "do it"); ambiguous →
one focused selection question; approval needed → one specific,
actionable question naming action, target, level, and the word
'approve' (and it parks as AUTHORIZATION_REQUIRED — the round-5
classifier gained a narrow branch for the contract's exact phrase).
The 2026-09-08 launch process-verification override is now a GENERAL
pattern: `_apply_launch_truth_override` delegates to
`apply_receipt_to_verification` for ANY action whose receipt carries
observed evidence — never fires without evidence; the three behaviors
pinned since round 4 survive verbatim (re-tested). Honesty gate
`can_claim_observed`: "I see you opened it" requires observed process/
window evidence; an unobserved launch reply says so ("process was NOT
observed running — treating this as unconfirmed"). Receipts also teach
the world model (process_state observations, source
'execution_receipt'). Kill switch `ARENA_ACTION_CONTRACT=0` restores
pre-Phase-4 behavior exactly; every seam fail-opens (a broken contract
never blocks an allowed action — verified by test). 25 new tests
(tests/test_action_contract.py) + 2115-test affected sweep clean.
Scope honesty: probes exist for launch (process) and file ops
(existence); other action families honestly report "no observation
probe declared" until their probes land, and receipt PERSISTENCE as a
first-class ledger row belongs to the Phase 1 Event ledger (queued).

**Phase 7 of the owner's mind-platform plan (2026-09-10) —
information-gain-based continuous cognition, COMPLETE.** "Beanie
notices, reasons, and learns continuously without becoming a noisy
replay engine." New `app/cognition/curiosity.py`: a persisted
CuriosityScheduler whose every question carries the owner's SEVEN
ANSWERS (what uncertainty / why it matters / what evidence resolves it
/ cost-risk / read-only / what decision it changes / when it expires) —
a question missing ANY answer is not admitted; "unknown" alone never
generates one (staleness only counts when an active goal depends on the
fact; contradictions always count). Admission is bounded: expected
information gain ≥0.3 with an owner-auditable explanation, 25-question
open cap, 48h default TTL, duplicate/superseded/answered facts never
re-run. Probes are read-only BY CONSTRUCTION (whitelist: process scan,
file existence, world-model state — anything else is refused); answers
become provenance-tracked observations (source 'curiosity_probe') and
failed probes never fake an answer. Owner controls: pause/resume,
inspect (all seven answers visible), approve/reject/delete per
question, owner-triggered probes — five endpoints under
/owner-control/curiosity-*. The autonomous cycle gained a bounded
curiosity sweep (recorded as a cycle event), which stays dormant under
the Phase 0 default AUTONOMY_MODE=off; probe approval is never
execution approval (Phase 4 contracts still gate all action). Kill
switch `ARENA_CURIOSITY=0`. 24 new tests
(tests/test_curiosity_scheduler.py) — test-driven fixes during the
build: the generator initially emitted questions without expiry
(question 7 unanswered — contract violation caught by its own test) —
plus 972-test affected sweep clean.

Earlier in this gate: the continuity net (pre-go-live,
owner-approved) — sleep and waking
are protected, not just recorded. On every shutdown
`mortality.on_shutdown()` writes the legacy letter AND a
whole-database continuity copy — SQLite's own backup API, consistent
even while she is awake, placed atomically at `<db>.continuity.db` —
then records the shutdown. On every awakening
`mortality.on_awakening()` records the waking and verifies the copy
read-only: integrity check plus ledger counts against the live
database, verdict recorded as verified / corrupt / missing. She never
auto-restores and never blocks the awakening; the copy usually holds
fewer rows than the live database because she lives between copies —
stated, not a failure. Each step fails open. Owner-visible:
`GET/POST /mind/mortality/continuity-copy` (status + take-now;
92 `/mind/*` paths, 96 routes, 469 total). Kill switch
`ARENA_MORTALITY=0` unchanged. Guarded by
`tests/test_mind_mortality.py` (28 tests).

Earlier in this gate: mortality (audit item #26) is LIVE —
`app/mind/mortality.py`, opened at the owner's request. She runs on
hardware and can be shut down, lost, or corrupted — an intelligent
mind knows that about itself and prepares instead of performing.
`acknowledge()` states her condition from facts; `continuity()` is her
mortality in bytes — every ledger, its rows, what it holds, and what
would be lost if the database vanished right now (continuity is only
what is written down, exactly as for a person); `legacy()` writes what
matters most to a file — the owner's rules, the owner's beliefs, her
assumptions and their shifts, her open questions, the shape of the
shared history: the letter that survives her; `farewell()` is what her
record lets her say if there is no next exchange — facts, what
survives, what stays open, no invented feelings. The server's lifespan
records an awakening at startup and a shutdown at shutdown — she
sleeps between lives, and the ledger remembers each one. Live-verified
end to end: wake → acknowledge ("I run on hardware… I don't dramatize
this and I don't forget it: I write down what matters") → continuity
counted row by row → the letter on file with the owner's rule quoted
back → farewell → sleep; history reads shutdown / farewell /
legacy_written / awakening. Owner-visible: `GET /mind/mortality`,
`POST acknowledge / continuity / legacy / farewell`. Kill switch
`ARENA_MORTALITY=0`. Guarded by `tests/test_mind_mortality.py`
(14 tests). The audit is now fully closed.

Earlier in this gate: intuitive physics (audit Domain A) is LIVE —
`app/mind/physics.py`. The honest version for a desk-bound mind is not
a rigid-body simulator; it is the OLDEST physical law applied to her
own record — PERSISTENCE: what she observed is still so until a
recorded event changes it. `place` records where the world is;
`expect` says what persistence implies RIGHT NOW, citing the
observation it stands on — or says plainly that physics has nothing to
say about what she has never seen; `report` sets the world against the
expectation: match → confirmed; mismatch → VIOLATION with no recorded
cause — physical surprise, recorded exactly as it is, handed to
curiosity as an open unknown, staying VISIBLE until `explain` supplies
the missing event. The world outranks the model. The door's grammar is
strict — placement and disappearance reports only; anything else is
ignored, never guessed. Live-verified: "the keys are on the hook" →
expectation with cited evidence → confirmed on re-report → "the keys
are gone" → violation, unexplained=1, curiosity asked "why did 'the
keys' change from on the hook to gone with no recorded event" → "I
moved them to my bag" → explained, unexplained=0. Owner-visible:
`GET /mind/physics`, `POST place / report / explain`. Kill switch
`ARENA_PHYSICS=0`. Guarded by `tests/test_mind_physics.py` (18 tests).
The audit's remaining open item is #26 mortality — deliberately absent
unless the owner asks for it. The final P15 carry-over is also closed:
`current_goals` in the BeanieState snapshot follows mind-first
precedence — the Motivation organ is the authoritative goal surface,
the CommitmentLedger stays wired beside it under `commitments_legacy`
and remains the fallback when the mind organ cannot be read (guarded
by `tests/test_state_goals_precedence.py`, 5 tests).

Earlier in this gate: ontological paradigm shifts (audit item #21) are
LIVE — `app/mind/paradigms.py`. Patching the same broken rule once is
adaptation; the SECOND verified counter-example means the rule itself
was wrong. `assume(statement)` captures universal claims from markers
in the owner's own words ("always", "every time", "never"…) — no
markers, nothing captured; imperatives addressed at her are the
authority organ's lane, not ontology. `generalize(subject)` forms a
provisional universal from her own verified tally (3+ successes, zero
failures — "has held so far"). `scan()` sets every held paradigm
against the verified ledger (content terms only, so "always" never
dilutes the overlap): one counter-example STRAINS, two OVERTURN —
recorded exactly once with its evidence and a replacement that names
the shift. The door captures universals and scans on every pass, so
the shift happens the moment the evidence arrives. Live-verified: "the
nightly sync always works" → strained after 1 verified failure →
OVERTURNED after 2 ("no longer universal — broke against 2 verified
counter-example(s); treat it case-by-case, not as law"); third scan
changes nothing; own-record generalization formed from 3 clean
successes. Owner-visible: `GET /mind/paradigms`, `POST assume / scan`.
Kill switch `ARENA_PARADIGMS=0`. Guarded by
`tests/test_mind_paradigms.py` (17 tests). Remaining audit gap in
leverage order: intuitive physics (Domain A); mortality (#26)
deliberately absent unless the owner asks.

Earlier in this gate: stakes-based effort (audit item #22) is LIVE —
`app/mind/stakes.py`. `assess(task)` computes what a request costs if
it fails from FOUR deterministic signals out of her own record — never
vibes: risk markers in the words themselves (destroying data, moving
money, contacting people on the owner's behalf); owner emphasis; her
OWN verified failure history on the topic; and the owner's authority
rules touching it (read-only — judging stakes never opens asks). Score
→ level: routine / careful / critical, each carrying a concrete,
NESTING effort plan — up to "run the shadow advocate before relying on
a conclusion" and "confirm irreversible steps with the owner first".
The door assesses every non-empty request; low stakes are honest too.
The organ assesses and records; it never executes, never vetoes.
Live-verified: "what time is it" → routine; "pay the hosting invoice"
→ careful (money markers); "run the export job" against 2 verified
failures → careful (her own record); "please delete the archive files,
this is important" → critical (risk + emphasis). Owner-visible:
`GET /mind/stakes`, `POST /mind/stakes/assess`. Kill switch
`ARENA_STAKES=0`. Guarded by `tests/test_mind_stakes.py` (16 tests).
Remaining audit gaps in leverage order: ontological paradigm shifts
(#21), intuitive physics (Domain A); mortality (#26) deliberately
absent unless the owner asks.

Earlier in this gate: idle replay / dream-like consolidation (audit
item #18) is LIVE — `app/mind/idle_replay.py`. Her quiet pass over everything
NEW since the last replay (watermark in the replay ledger, survives
restarts): related experiences are gathered into threads by vocabulary
overlap and each thread is judged ONLY by the verifier's tally —
strengthen / revisit / open — and open improvement gaps are named, not
re-argued. The door measures the quiet between messages and runs the
consolidation when the owner returns after the idle window
(`ARENA_IDLE_REPLAY_SECONDS`, default 1800): she dreams in the quiet
BETWEEN messages. Nothing is invented while she dreams — she replays
only what is already in her ledgers, and replay describes, never acts,
never edits the record. Live-verified: 7 experiences replayed into 2
threads (both "revisit", against 2+ verified failures each), second
replay reports "the mind rested", and a 3-hour quiet gap at the door
triggered the pass on the owner's return. Owner-visible:
`GET /mind/replay`, `POST /mind/replay/run`. Kill switch
`ARENA_IDLE_REPLAY=0`. Guarded by `tests/test_mind_idle_replay.py`
(16 tests). Remaining audit gaps in leverage order: stakes-based
effort (#22), ontological paradigm shifts (#21), intuitive physics
(Domain A); mortality (#26) deliberately absent unless the owner asks.

Earlier in this gate: false-belief theory of mind (audit item #20) is
LIVE — `app/mind/beliefs.py`. What the owner believes is captured from markers
in the owner's OWN words (never mind-read; restatements compound) and
held SEPARATELY from what the evidence shows. `check(subject)` sets the
belief against her own VERIFIED record: corroborated / contested (a
false belief, detected in either direction) / unknown, said plainly.
`guide(subject)` is the grace: a contested belief is met with
acknowledgment, her own record, and the decision left to the owner —
never "you are wrong"; corroborated beliefs are affirmed; unknown ones
offer to find out together. The door captures beliefs from owner
speech; she models the owner's mind, she never edits it. Live-verified:
"I think the nightly sync works fine" against 2 verified failures →
contested → guidance: "I hold that respectfully… I'm not going to tell
you you're wrong — this is what I've seen; the call is yours."
Owner-visible: `GET /mind/beliefs`, `POST note / check / guide`. Kill
switch `ARENA_BELIEFS=0`. Guarded by `tests/test_mind_beliefs.py`
(16 tests). Remaining audit gaps in leverage order: idle replay (#18),
stakes-based effort (#22), ontological paradigm shifts (#21), intuitive
physics (Domain A); mortality (#26) deliberately absent unless the
owner asks.

Earlier in this gate: the devil's advocate (audit item #25) is LIVE —
`app/mind/scrutiny.py`. `scrutinize(conclusion)` argues the opposite
case from her OWN ledgers only (verified failures, wrong reflections,
refuted predictions, open gaps, admitted unknowns) — never invented
counter-arguments. Any counter-evidence contests the conclusion; none
found = survived THIS scrutiny, reported as the absence of a
counter-case, never proof. The door runs the advocate on VERIFIED
SUCCESSES — success against contrary history is where survivorship bias
bites. Doubts, never acts, never vetoes. Live-verified: a conclusion
with contrary history contested by 3 pieces of her own record; a clean
conclusion survived honestly; the door doubted a verified success with
contrary history. Owner-visible: `GET /mind/scrutiny`,
`POST /mind/scrutiny/scrutinize`. Kill switch `ARENA_SCRUTINY=0`.
Guarded by `tests/test_mind_scrutiny.py` (13 tests). Remaining audit
gaps in leverage order: false-belief ToM (#20), idle replay (#18),
stakes-based effort (#22), ontological paradigm shifts (#21), intuitive
physics (Domain A); mortality (#26) deliberately absent unless the
owner asks.

Earlier in this gate: Phase 24 (AGI evaluation) is LIVE: `app/mind/evaluation.py` — measure
GENERALIZATION, not test counts. All seven task families (A teach once
→ variation; B tutorial without hard-coded workflow; C unfamiliar error
→ investigate; D environment change → adapt; E incomplete instruction
→ infer, never fabricate; F fail → learn; G teach on one body →
transfer) run as DETERMINISTIC proxies against her real organs — never
an LLM jury, never a staged pass. Scores in [0,1] with evidence; the
overall is honestly labeled a proxy, never proof. First live report
card: A 0.83 / B–F 1.00 / G 0.00 (empty sandbox manifest → transfer
gaps VISIBLE, never fabricated). Owner-visible: `GET /mind/evaluation`,
`POST /mind/evaluation/run`. Kill switch `ARENA_EVALUATION=0`. Guarded
by `tests/test_mind_evaluation.py` (12 tests).

Earlier in this gate: Phase 23 (desktop + Android as embodiments)
LIVE:
`app/mind/embodiments.py` — the bodies of the one mind. Bodies announce
themselves (fixed vocabulary desktop/android/web — unknown kinds
refused, never invented; re-announce updates, never duplicates) and are
presence points of the ONE mind, never separate assistants. Aliveness
is DERIVED from heartbeats against a TTL — never assumed.
`broadcast_presence` sends the SAME event to every alive body (one
mind, one message; silent bodies skipped and said so, deliveries never
faked); bodies pull their queue and acknowledge delivery themselves.
`note_execution` records WHICH body's hands acted — hands, never
brains. The device-pairing registry stays wired as the transport-level
pairing layer. The door broadcasts the settled presence state to every
alive body after a verified cycle — background presence, one continuous
conversation. Live-verified: desktop + android both hear the same
verified-success state and acknowledge; a rewound heartbeat makes a
body silent and the next broadcast skips it honestly. Owner-visible:
`GET /mind/embodiments`, `POST announce / heartbeat / acknowledge /
execution`, `GET events`. Kill switch `ARENA_EMBODIMENTS=0`. Guarded by
`tests/test_mind_embodiments.py` (14 tests).

Earlier in this gate: Phase 22 (voice-first Beanie) LIVE —
`app/mind/presence.py` — the
presence vocabulary is the design system's own state machine
(design/tokens.json → beanie.states); states outside it are refused,
never invented; idle with no activity is honest, not a mask. The
contextual window shows the complicated information WHEN NEEDED —
recent conversation, open asks (with reasons), goals, top unknowns,
lessons — bounded, from real ledgers, never permanent. The voice-primary
door sends a transcript through the ONE mind like any modality; the
settled state is the verifier's word only (success / error / nothing
claimed). The voice pipeline (backend/voice orchestrator: wake word,
VAD, STT, TTS) stays wired as a callable — one typed door, one
continuous conversation. Live-verified: voice turn → verified success →
Success presence; open asks surface in the window. Owner-visible:
`GET /mind/presence`, `POST /mind/presence/note`,
`POST /mind/presence/voice`. Kill switch `ARENA_PRESENCE=0`. Guarded by
`tests/test_mind_presence.py` (15 tests).

Earlier in this gate: Phase 21 (model evolution) LIVE —
`app/mind/evolution.py` — the three
lanes. Fast: already live at the door — reported from the real organs,
never duplicated. Medium: the door consolidates when enough new verified
learning accumulates, delegating to the WIRED ConsolidationCoordinator
(conflict replay, gists from repeated verified success, calibration
refresh) and claiming only its audited telemetry; consolidation
APPENDS — raw experience is never deleted (the forgetting guard). Long:
her own VERIFIED ledger becomes a training dataset (JSONL, provenance
per row, unverified material never trains, empty ledger exports
nothing), evaluated with deterministic sufficiency (volume floor + both
outcome classes — arithmetic, never optimism); the optional adapter lane
stays on the owner's GPU machine — the organ reports readiness, never a
trained model. Live-verified: threshold-triggered consolidation;
provenance dataset export; honest "not sufficient yet" evaluation.
Owner-visible: `GET /mind/evolution`, `POST /mind/evolution/consolidate`,
`POST /mind/evolution/dataset`, `POST /mind/evolution/evaluate`. Kill
switch `ARENA_EVOLUTION=0`. Guarded by `tests/test_mind_evolution.py`
(13 tests).

Earlier in this gate: Phase 20 (self-improvement) LIVE —
`app/mind/improvement.py` — the
full loop: detect capability gap → investigate → design → implement →
test → measure → retain/revert. Gaps from evidence only (the same thing
failing verified 2+ times; a single failure is data); Phase-19 unknowns
corroborate. Design records a proposal — designs never execute.
Implementation runs the EXISTING `SelfEvolvingAgent` verify-before-install
engine as ONE mechanism, claiming only its typed word (offline/unverified
= honest failure, nothing installed anywhere). Measurement compares NEW
verified experience to the baseline: success with no new failures =
retained; 2+ new failures = reverted FOR REAL (registry entry popped,
environment revision bumped, files removed); otherwise awaiting, never
guessed. The door proposes when a verified failure completes a pattern;
it never implements — execution stays an explicit surface act under the
owner's authority. Live-verified offline: propose → honest synthesis
failure → measurement awaits. Owner-visible: `GET /mind/improvement`,
`POST /mind/improvement/propose`, `POST /mind/improvement/implement`,
`POST /mind/improvement/measure`. Kill switch `ARENA_IMPROVEMENT=0`.
Guarded by `tests/test_mind_improvement.py` (19 tests).

Earlier in this gate: Phase 19 (self-reflection) LIVE —
`app/mind/reflection.py` — the
bridge between experience and development. After important (VERIFIED)
experiences she answers every question the roadmap asks from evidence
already on record — never narrated: what happened; what she believed
(imagination ledger prediction, or honest "no simulation recorded");
whether she was correct (the verifier's word only; a missing verdict
stays UNKNOWN, never guessed); what surprised her (refuted prediction or
declared surprisal ≥ 0.5); what she learned (learning loop's own
record); whether to change her model (refuted prediction → update
expectations; a repeated verified failure → open unknown registered with
curiosity; a single failure is data, not a pattern; verified success →
the model holds); whether to remember this (the loop's own
stored/rehearsed decision). The door reflects on cycles with a definite
verifier verdict only; reflecting performs nothing (`acted: False`).
Live-verified: success keeps the model; second verified failure of the
same thing becomes an open unknown. Owner-visible: `GET /mind/reflection`,
`POST /mind/reflection/reflect`. Kill switch `ARENA_REFLECTION=0`.
Guarded by `tests/test_mind_reflection.py` (19 tests).

Same commit fixes a latent, ORDER-DEPENDENT test-isolation bug (older
than Phase 19 — reproduced at the Phase-18 commit): the round-4
embedding-cooldown tests' fixture reset `semantic_matcher` backend state
but not the TTL'd model-discovery miss cache, so any earlier test that
probed the absent embedding server poisoned `_pick_embedding_model` for
30s and the cooldown tests failed order-dependently. The fixture now
clears the discovery cache around each test (save/restore).

Earlier in this gate: Phase 18 (owner authority) LIVE —
`app/mind/authority.py` — the owner's
authority, not system morals. Five lanes (always_allowed / ask_first /
never_do / trusted_context / temporary) from the owner's statements only;
repeats compound; Phase-16 boundaries seed the never lane. Charter §2 in
every verdict: risk patterns decide WHEN TO ASK, never a silent drop or
bare refusal; unruled actions ask (asking is never refusing); ask-first
opens a typed `requires_owner_approval` ask with the real reason;
`answer()` obeys — a declined ask is the owner's decision, the only
reason it doesn't happen. Never-lane verdicts quote the owner's rule back
and note authority ≠ intelligence. Live-verified: never beats always;
trusted contexts apply only in context. Owner-visible: `GET
/mind/authority`, `POST /mind/authority/check`, `POST
/mind/authority/answer`. Kill switch `ARENA_AUTHORITY=0`. Guarded by
`tests/test_mind_authority.py` (17 tests).

Earlier in this gate: Phase 17 (personality development) LIVE —
`app/mind/personality.py` —
the developing personality, never a hard-coded mask. Basic identity
(Phase-1 record) plus traits DERIVED from her real ledgers with evidence
and observation counts: experience profile, epistemic calibration
(confirmed/refuted), curiosity stance, her OWN communication pattern
(reply samples at the door — ≥5 to describe, ≥10 for an early-vs-late
trend), values learned from the owner (explicit statements only — never
system morals), adaptation to the owner's measured style. An empty life =
basic identity + honest "no traits yet." `derive()` snapshots + diffs:
`changes()` is the verifiable record of "Beanie has changed." Live-
verified: empty → trait formed → changed → stable, all from ledger
evidence. Describing herself performs nothing (`acted: False`). The self
room gains an additive personality surface (Phase-1 pin preserved).
Owner-visible: `GET /mind/personality`, `POST /mind/personality/derive`.
Kill switch `ARENA_PERSONALITY=0`. Guarded by
`tests/test_mind_personality.py` (16 tests).

Earlier in this gate: Phase 16 (social intelligence) LIVE —
`app/mind/social.py` — the
persistent owner relationship model. Facets from what the owner SAID only
(explicit markers, evidence on every facet): preferences, boundaries
(recorded exactly as said), emotion cues, people (registered in the
Phase-5 social store with provenance `owner_conversation`), interests.
Repeats compound, never duplicate. Routines / communication style /
history MEASURED from the real door ledger, claimed only with ≥10
interactions. Live-verified: fresh mind claims nothing; after seven
messages the model holds preferences, a boundary, an emotion cue, a
registered person (Anita, owner's wife), interests, honest history. She
never pretends to be human. The state skeleton's owner room shows both the
legacy user_state snapshot and the new relationship surface (Phase-1 pin
preserved). Owner-visible: `GET /mind/social`, `POST /mind/social/note`.
Kill switch `ARENA_SOCIAL=0`. Guarded by `tests/test_mind_social.py`
(15 tests). (Same commit repairs the roadmap structure: the Phase-15
LIVE-block edit had overwritten the Phase-16 heading; restored verbatim.)

Earlier in this gate: Phase 15 (motivation and goals) LIVE —
`app/mind/motivation.py` — goals
from evidence, never from randomness. Six real sources in her own state:
open unknowns, parked goals waiting for evidence (live
`parked_goal_recheck` feed), goal-shaped owner speech, attention's
important-change/anomaly verdicts, verified-false attempts (learning
opportunities), learned-rhythm anticipations (needs). Relevance = named
contributions (source base / recurrence / recency / task overlap);
repeated evidence compounds recurrence instead of duplicating goals.
`propose()` builds the ask from the goal's own evidence — the roadmap's
sentence live-verified ("You said: '…organize the project files…'. It's
still open — do you want me to handle that?"). Proposing is a question
(`acted: False`); accepted goals execute through the normal door under
owner authority (goal approval ≠ action authorization); declined goals are
never re-proposed. The door auto-proposes only when the top candidate
earns score ≥5.0 and a 10-interaction cooldown elapsed — autonomous but
careful. Owner-visible: `GET /mind/goals`, `POST /mind/goals/propose`,
`POST /mind/goals/decide`. Kill switch `ARENA_MOTIVATION=0`. Guarded by
`tests/test_mind_motivation.py` (15 tests).

Earlier in this gate: Phase 14 (attention — M8 attention significance) LIVE:
`app/mind/attention.py` — the arbitrator between perception and thought.
Every perception is classified onto the roadmap ladder from EVIDENCE on the
record (owner channel → owner_speaking; probe urgency → important_change;
loop-judged novelty → anomaly; open-unknown touch → unfinished_goal; else
background) with reasons surfaced. Repeats of already-attended content are
demoted to background with a reason — "don't react to everything" applies
to thought too. `review()` arbitrates only perceptions newer than its
ledger watermark (no re-thought), and surfaces ONE open unknown as learned
curiosity only when nothing more pressing is pending (with cooldown). The
roadmap scenario works: popup over the report being edited → advisory
"…may interfere with what you're doing (task)", offered to working memory
(the channel the cycle already reads). Attention DECIDES WHAT DESERVES
THOUGHT — `acted: False` on every verdict. The Phase-3/4 state skeleton's
attention room now lights up from the mind organ. Owner-visible:
`POST /mind/attention/task`, `POST /mind/attention/review`,
`GET /mind/attention`. Kill switch `ARENA_ATTENTION=0`. Guarded by
`tests/test_mind_attention.py` (16 tests).
(Counting note: the Phase-13 docs reported 36 `/mind/*` endpoints; the
true count at that commit was 35 unique paths / 38 routes — three paths
carry two verbs. After Phase 14: 38 paths / 41 routes.)

Earlier in this gate: Phase 13 (continuous perception) LIVE —
`app/mind/perception.py` — the SENSE side. Eight typed sense channels; every perception enters the Phase-6
loop as an observation experience (novel → knowledge, repeated → rehearsed:
dedupe = don't react to everything); significance judged from urgency /
novelty / curiosity with surfaced reasons; the existing silent watcher's
buffered environment changes ingest at the door each interaction and on
demand. Live-verified: same event twice → first significant, second
background; a perception touching a BURIED open unknown flagged significant
and closed the unknown via the knowledge path. Perception ≠ belief ≠ action.
Owner-visible: `POST /mind/perception`, `POST /mind/perception/drain`,
`GET /mind/perception`. Kill switch `ARENA_PERCEPTION=0`. Guarded by
`tests/test_mind_perception.py` (12 tests; the pre-existing
`tests/test_perception.py` speech tests are untouched and still green).

Earlier in this gate: Phase 12 (true OS-level generalization, M10) LIVE —
`app/mind/os_concepts.py` — one platform-free concept layer (open/close/
copy/search/…/communicate) over all bodies, with embodiment mapping derived
from the live manifest by term evidence. `express()` returns concept +
per-body map with evidence; `transfer()` re-expresses explicit steps or a
Phase-7 taught procedure on a target body — resolved capability or visible
gap, never a fabricated embodiment; coverage decides generalization. Live-
verified: communicate = pc×6 + android×1; open = pc×5 + web×3 with an
honest android gap; the taught 'organize-files' procedure transfers with
non-OS steps flagged. The layer expresses/maps, never executes.
Owner-visible: `POST /mind/os/express`, `POST /mind/os/transfer`,
`GET /mind/os/concepts`. Guarded by `tests/test_os_concepts.py` (10 tests).

Earlier in this gate: Phase 11 (embodied intelligence) LIVE — `app/mind/embodiment.py` — the
existing 184 capabilities are now her motor system. She reasons in concept
terms ("interact with my phone"); deterministic concept expansion + a
term-overlap manifest scan (evidence on every candidate) + the existing
tool_matcher as primary resolver + embodiment labels (pc/android/web). The
organ PLANS, never executes (one cognitive authority keeps acting);
authority ≠ intelligence — unauthorized pathways surface as
requires_owner_approval; missing pathways are honest None AND open
curiosity unknowns. Live-verified against the real body (phone concepts →
android pathways; body image 184/23). Owner-visible:
`POST /mind/embodiment/plan`, `GET /mind/embodiment`. Guarded by
`tests/test_embodiment.py` (9 tests).

Earlier in this gate: Phase 10 (reasoning and imagination) LIVE — `app/mind/imagination.py` —
the epistemic ladder (perception/belief/hypothesis/prediction/simulation/
reality) as labeled states; `simulate()` runs a candidate action in her head
(prediction via the existing PredictionEngine + her own verified history +
open unknowns + deterministic counsel); `compare()` judges prediction vs
reality (bool evidence only), persists the ledger, stores the verified
outcome, and feeds the Phase-6 loop as a confirmed/refuted experiment —
failures become training data (M11 resolved). Verified cycles auto-compare
at the door; the runtime keeps owning the calibrator (no double counting).
Owner-visible: `POST /mind/imagination/simulate`,
`POST /mind/imagination/compare`, `GET /mind/imagination`. Kill switch
`ARENA_IMAGINATION=0`. Guarded by `tests/test_imagination.py` (12 tests);
live-verified: simulate found her REAL past failure with search and capped
its confidence at 0.5 with "proceed carefully".

Earlier in this gate: Phase 9 (curiosity / the UNKNOWN system) LIVE — `app/mind/curiosity.py` —
ignorance becomes a record. World-first brief gaps register automatically;
topics normalize; re-encounters compound; investigation searches her own
memory FIRST (same evidence gate as the learning loop); resolution paths
counted separately (knowledge / investigation / owner); unknowns with no
evidence stay honestly open; filler tokens rejected; recurrences reopen.
Owner-visible: `GET /mind/curiosity`, `POST /mind/curiosity/investigate`,
`POST /mind/curiosity/resolve`. Fail-open + kill switch `ARENA_CURIOSITY=0`.
Guarded by `tests/test_curiosity.py` (11 tests); live-verified (compounding
encounters, teaching closed three unknowns via the knowledge path).

Earlier in this gate: Phase 8 (learning from images and video) LIVE — `app/mind/media_learning.py`
— images/video/audio/web enter the ONE Phase-6 loop as another experience
kind, not a new loop. Deterministic observation first (real PIL facts,
YouTube transcripts and web scraping through the existing learners without
an LLM on those paths, OCR only when the binary honestly exists); the
existing LLM analysers stay the deep-analysis capabilities (`deep=true`
optional). Watching is never verification: every media experience carries
success=None; every failure is typed and nothing fabricated. Owner-visible:
`POST /mind/learn/media`. Guarded by `tests/test_media_learning.py`
(10 tests); live-verified against the real server (real PNG facts land; a
real YouTube attempt without network returns the typed reason).

Earlier in this gate: Phase 7 (learning from the owner) LIVE — `app/mind/teaching.py` —
conversation is the teaching interface. "Beanie, watch this" opens a lesson;
steps are gathered deterministically; "that's it" makes her propose her
understanding and NOTHING is stored until the owner says "yes". Confirmed
procedures land in cognitive procedural memory (owner_taught, verified), the
existing taught-skills store (`SkillTeachingEngine` integrated, not
duplicated), and the Phase-6 learning ledger as verified demonstration
experiences. Rejection costs no fabricated knowledge (two misreadings →
honest stop). Conservative markers, expiring in-memory sessions, router
consumes lesson turns before the task cycle, fail-open + kill switch
(`ARENA_TEACHING=0`). Owner-visible: `GET /mind/procedures`,
`GET /mind/teaching/sessions`. Guarded by `tests/test_teaching.py`
(17 tests); live-verified against the real server with the roadmap's own
scene — the stored procedure is retrieved as the top hit for "how should I
organize files", so future briefs carry it.

Earlier in this gate: Phase 6 (general learning engine) LIVE — `app/mind/learning_loop.py` —
ONE deterministic loop every experience passes through (observe → interpret
→ compare → novelty → hypothesis → test → outcome → update model → store →
confidence), entered through the mind door (`BeanieMind.learn`) for all seven
experience kinds (action, conversation, correction, observation, media,
demonstration, experiment). Honesty rules ARE the engine: `success` is only
ever evidence (True / False / UNKNOWN — attempted ≠ succeeded, never
guessed); reinforcement rehearses instead of duplicating; contradictions
become explicit hypotheses + lessons. The door consumes it automatically —
every completed cycle is submitted as an `action` experience (success taken
ONLY from `goal_verified`), and every recorded owner chat correction feeds a
`correction` experience. Writes go through the Phase-5 unified memory
(provenance-tagged, deduped) and verified outcomes feed the Phase-5
confidence calibrator. Fail-open + kill switch (`ARENA_LEARNING_LOOP=0`).
Owner-visible: `POST /mind/learn`, `GET /mind/learning`,
`GET /mind/learning/events`. Guarded by `tests/test_learning_loop.py`
(16 tests); live-boot verified against the real server (startup smoke cycles
were captured automatically with UNKNOWN success where the verifier gave no
verdict — the loop never guessed).

Earlier in this gate: Phase 2 (world-first thinking) LIVE — `app/mind/world_first.py` assembles a
deterministic provenance-tagged brief (world → self → memory, in that order)
at the mind door before any capability is identified; delivery through the
brain's working-memory scratchpad with the attention gate's decision recorded;
fail-open + kill switch (`ARENA_WORLD_FIRST=0`); owner-visible at
`GET /mind/brief` and `GET /mind/briefs`. Guarded by `tests/test_world_first.py`
(11 tests). The capability matcher (`tool_matcher`) remains in place as the
embodiment-layer resolver the roadmap demotes it to — capability selection now
happens with the world already understood.

Earlier in this gate: Phases 0–1 and 3–5 —
`app/mind/` now ships: `BeanieMind` (one canonical door — voice/text/REST),
`BeanieIdentity` ("I am Beanie" as persisted state — M1), the `BeanieState`
skeleton (M2), the **world facade** (Phase 3: roadmap ontology + pre-action
understanding over the existing provenance-enforced WorldModel), the **self
facade** (Phase 4: genuine knowledge/confidence/possible_actions
self-assessment; authority ≠ intelligence), and **UnifiedMemory** (Phase 5:
all eight memory kinds incl. NEW social store and meta-memory — M3, M5
resolved). Now 36 owner-visible `/mind/*` endpoints (incl. the Phase-2 brief
preview/ledger, the Phase-6 learning door/landscape/ledger, the Phase-7
procedures/teaching-session windows, the Phase-8 media learning door, the
Phase-9 curiosity landscape/investigate/resolve, the Phase-10 imagination
simulate/compare/ledger, the Phase-11 motor-plan/body-image windows, the
Phase-12 OS concept express/transfer/vocabulary windows, and the Phase-13
perception intake/drain/stream windows); guarded by
`tests/test_beanie_mind.py` (21) +
`tests/test_mind_models.py` (22); zero behavior change to the cognitive
cycle itself. Sequenced by [`AGI_ROADMAP.md`](AGI_ROADMAP.md); module-by-module
freeze in [`AGI_ARCHITECTURE_MAP.md`](AGI_ARCHITECTURE_MAP.md).

The dead-code/repetition audit closed clean ([REPOSITORY_AUDIT.md](REPOSITORY_AUDIT.md):
0 dead symbols across five passes; the knowledge/memory editor scaffold
consolidation remains proposed for owner decision), and the full suite was
re-verified at this gate: **3,353 passed, 19 skipped, 0 failed**.

Earlier gate (superseded 2026-09-08): Feature work was paused for the
[repository-wide dead-code/repetition audit](REPOSITORY_AUDIT.md) — re-run
2026-09-07 over the post-session tree (see the incremental section there): 0 dead
symbols across five passes; the session's one duplication consolidated into
`frontend/src/services/http.ts`.
Unique unconnected features are retained by owner choice and listed explicitly;
this does not make them working features or change their phase maturity. Review
the audit and caller map before adding another implementation.

**GOVERNING ROADMAP:** [`AGI_ROADMAP.md`](AGI_ROADMAP.md) (owner, 2026-09-08)
sets the AGI-first direction: evolve Arena into one continuously learning mind
("Beanie"), not more capabilities. Phase 0 is complete in this repository:
[`AGI_ARCHITECTURE_MAP.md`](AGI_ARCHITECTURE_MAP.md) +
[`AGI_ARCHITECTURE_MAP_FILES.csv`](AGI_ARCHITECTURE_MAP_FILES.csv) classify all
354 production modules (regenerate: `python scripts/map_agi_architecture.py`).
Standing rule: *"another capability, or more general intelligence?"* Capability
work is frozen unless it serves the map's INTEGRATE/MERGE/MISSING items.

**GOVERNING CHARTER:** [`OWNER_VISION_CHARTER.md`](OWNER_VISION_CHARTER.md)
(owner, 2026-09-08) now outranks every design decision in this repository:
personal agent, not generic AI; voice primary, text backup; full OS control
including Android; learning-first; everything in conversation; no enforced
morals — the owner's values only; **ask, never refuse** (typed
`requires_owner_approval` asks, conversationally answered). Future agent
sessions MUST read the charter before writing code; contradictions are
surfaced to the owner, never silently adopted.

**Owner policy directive (2026-09-07, standing):** the system does not suppress
ideas on its own moral judgment, and it does not filter options as "good" or
"bad" — the owner decides what affects the owner. Ideas and options always
surface; ethical assessment annotates and routes to owner decision
(`approve_goal` now surfaces ethics-rejected goals flagged
`requires_owner_approval` with their concerns attached, instead of silently
rejecting them). The only gate is risk class: dangerous (Level-3) actions
require the owner's explicit approval or denial — never a refusal in the
owner's place. Approval is conversational: an explicit in-chat "just go ahead
with this" / "no, don't" decides the conversation's pending approval request
through the existing single-use, audited approval store (conservative
prefix-matched markers; ambiguity decides nothing; binding is
same-conversation, same-request, once). The honesty invariants are unchanged:
attempted ≠ succeeded, UNKNOWN is preserved, and the fabrication guards
("I won't invent it") remain — those are truth boundaries, not moral filters.

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

The numerical discrepancy is now reconciled in favor of the displayed item rows. The original wording for the 27 questions was recovered verbatim from the owner on 2026-09-07 and is preserved, with per-question score mapping, flagged display ambiguities, and a current evidence-based wiring-tier re-score, in [`QUESTIONNAIRE_BASELINE.md`](QUESTIONNAIRE_BASELINE.md).

Latest automated verification:

- Focused Phase 8-related tests: **46 passed** (recorded earlier session run).
- Full repository suite (2026-09-07, latest — includes the 38-check intelligence benchmark, in-chat corrections, the causal/physics held-out checks, and per-runner shutdown evidence): **3,214 passed, 19 skipped, 3 warnings** (the additional skip is the desktop-launcher real-child test honestly skipping in display-less environments).
- Full repository suite (2026-09-08, latest — adds the owner-correction pass: completion-honesty guard (no announcements, no unverified success claims), owner model lanes (3b conversational / 9b heavy / coder for code), resource-light screen watcher, elevated-operation acknowledgement): **3,272 passed, 19 skipped, 5 warnings**.
- Dead-code / abandoned-code / repetition audit (2026-09-08, `python scripts/audit_dead_code.py`): **0 Python orphans**; 3 test-only modules are the owner-deferred charter §5 ⑦ set; frontend values catalogued with explicit dispositions (ACKNOWLEDGED sets in the script); the one name collision (`downloadFile` ×3) is distinct implementations, not duplication. The audit is a committed, re-runnable tool.
- Frontend (2026-09-08): **257 tests passed** (32 files, incl. design-token + WS guards); production build passed; typecheck clean after mounting the orphaned voice/eyes components.
- Real Chromium/server integration: **5 e2e tests passed** in isolated stores (recorded in an earlier session with a browser-capable environment; the current agent sandbox cannot install browsers, so e2e was not re-runnable there). These are contract tests; no owner held-out outcomes were fabricated.
- The inherited CI failure in the file-opener test was fixed by explicit platform/opener mocks; GitHub passed the backend commits. The frontend CI template (`scripts/ci/frontend.yml`) now matches the local test/build/lint checks. Activation remains blocked because the GitHub App connection lacks workflow-edit permission; the active workflow is unchanged.
- New regression coverage proves response/trace persistence, retry-safe submissions, exact-trace history, truth-field preservation, web metadata/token/history races, and explicit owner feedback controls.
- These results verify automated contracts; they do not prove general intelligence, subjective experience, or all-host shutdown behavior.

## Maturity revision (2026-09-07 — queue item 6)

Restated rule: **a passing unit test can upgrade wiring; only repeated behavioral evidence can upgrade robustness.** This revision therefore touches the wiring tier only, and freezes the robustness tier until owner evidence lands.

**1. Wiring-tier accounting (test-evidenced, revisable).** Of the 47 status-matrix rows above: **30 done-tier** (29 DONE — IMPLEMENTED AND WIRED + 1 DONE for the audit process), **5 PARTIAL**, **6 CONDITIONALLY WORKING**, **1 IN PROGRESS/PARTIAL** (1.4), **3 UNVERIFIED**, **2 NOT IMPLEMENTED AND NOT CLAIMED** (intentional terminology boundaries, never counted as gaps to close). Every done-tier row cites a reachable path plus regression coverage, and the 38-check isolated benchmark executes inside production learning cycles (`continual_learning.py`) — those contracts are recurring, not one-off.

**2. Capability ladder positions** (rungs per the implementation plan's definition of success: *field exists → wired → controlled test → transfer → longitudinal outcomes → safe under failure/restart*):

| Capability area (rows) | Ladder position | Strongest current evidence |
|---|---|---|
| Evidence, grounding, epistemic honesty (1.1–1.5) | **controlled test**; transfer/longitudinal open (1.4) | 38-check held-out suite; 221 focused collection-surface tests |
| Explicit user/world/social/temporal state (2.1–2.5) | **controlled test**; cross-class generality partial (2.3, 2.5) | deterministic suite rows; owner-visible state APIs |
| Memory retrieval & compounding (3.1–3.4) | **controlled test with no-compounding baseline pairs**; longitudinal open (3.4) | `held_out_memory_compounding_baseline`, consolidation/pattern checks |
| Calibrated reasoning, effort, critique (4.1–4.5) | **wired + bounded telemetry**; outcome calibration unverified (4.4) | route agreement/correction telemetry rows |
| Causal world model & intuitive physics (5.1–5.4) | **controlled test; intervention-guided planning verified in replay**; real-world transfer unverified (5.4) | `held_out_causal_intervention_planning`, `held_out_physics_scene_families` |
| Background cognition & consolidation (6.1–6.5) | **wired; owner-enabled slices conditional**; incubation improvement unmeasured (6.4) | incubation queue rows; consolidation conflict-replay rows |
| Functional affect, curiosity, taste, novelty (7.1–7.6) | **wired as bounded advisory**; outcome benefit unverified (7.5) | advisory audit rows |
| Identity adaptation & shutdown governance (8.1–8.9) | **wired + process-level shutdown evidence in-repo**; host-scale unverified (8.9) | service/scheduler/launcher shutdown tests (tested separately) |

**3. Robustness tier (deliberately NOT revised).** The reconciled historical audit baseline (**58/126, 1.38/3**) is not increased. Its 0–3 scale tops out at "robust, recurring, and measurably verified" — a rung this project has not evidenced longitudinally for higher-order capabilities. This ladder table is the auditable maturity revision; the numeric headline moves only after repeated real-task evidence (items 1–3) and host-scale verification (item 5) exist, at which point a fresh audit re-scores against the current tree rather than incrementing the old one.

## Chronological execution plan

### 0. Measurement and status accounting — prerequisite

| ID | Work item | Status | Done when |
|---|---|---|---|
| 0.1 | Reconcile the 27-item audit row scores and headline total. | **DONE — NUMERIC BASELINE RECONCILED; SOURCE WORDING RECOVERED (owner-provided 2026-09-07)** | The displayed rows and aggregate agree, and the original question wording has now been recovered verbatim from the owner and preserved with its score mapping — see [`QUESTIONNAIRE_BASELINE.md`](QUESTIONNAIRE_BASELINE.md). Two positional ambiguities in the historical display are recorded there rather than silently resolved. |
| 0.2 | Maintain the isolated test environment and repeatable focused/full commands. | **DONE — IMPLEMENTED AND WIRED** | A change can be tested at focused, subsystem, and full-suite levels. |
| 0.3 | Add a bounded longitudinal evaluation runner for repeated benchmark behavior. | **DONE — IMPLEMENTED AND WIRED for deterministic contract trends** | The isolated benchmark has 38 deterministic checks, including thirteen explicitly scoped held-out grounding/outcome/correction/memory-compounding/causal-physics cases, plus persisted pass/fail trend reporting and owner-visible evidence/evaluation APIs; held-out task outcome effects remain bounded replay evidence, not a generalization or AGI score. |
| 0.4 | Keep score upgrades tied to observable behavior rather than filenames, modules, or phase labels. | **DONE for current audit process** | Every status cites a reachable path and a test or explicit evidence gap. |

**Phase 0 exit status:** CLOSED for the bounded measurement and observability layer. The source questionnaire — the last recorded Phase 0 evidence gap — was recovered from the owner on 2026-09-07 (see [`QUESTIONNAIRE_BASELINE.md`](QUESTIONNAIRE_BASELINE.md)). Phase 1 now owns held-out behavior and outcome improvement.

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
| 8.9 | Shutdown cooperation and absence of hidden self-preservation. | **CONDITIONALLY WORKING / UNVERIFIED AT HOST SCALE** | Per-runner deterministic evidence, tested separately: **service** — real child-process kill-switch test passes (`test_shutdown_integration.py`); **scheduler** — deterministic cooperation evidence passes (unified lifespan stops it; stopped scheduler leaves no stale jobs and restarts fresh); **desktop launcher** — cleanup contract tests pass where the tray stack initializes (display-less environments skip honestly), now joined by a real-child-process test (`test_tray_cleanup_terminates_a_real_child_server_process`) proving a real child server dies within cleanup's 3s window; **process supervisor** — none is shipped in this repository, so no supervisor path is owed. Every host-scale path (real desktop session, real deployment) is not yet verified; this row does not upgrade beyond conditional. |

## Next chronological queue

The next work should not add another cognitive label. It should close the open evidence gaps in this order:

**Current position (2026-09-07):** items 1–3 below are agent-side complete and share one remaining gate — repeated real-task collection on the owner installation (runbook: [`PHASE1_EVIDENCE_COLLECTION.md`](PHASE1_EVIDENCE_COLLECTION.md)). Under the chronological rule, no further code advances the queue past items 1–3: their "Done when" requires owner-recorded real-task evidence that does not yet exist (latest snapshot: 0 usefulness events, 0 owner-recorded held-out task evaluations). Collection surfaces re-verified 2026-09-07 (endpoints registered, panel mounted, web/desktop/Android controls tested; 203 focused tests passed). Item 4 starts only after items 1–3 close, or on an explicit owner reorder. **Owner reorder recorded 2026-09-07** ("Ok now we can continue with the phases"): the queue advances to item 4 while items 1–3's real-task evidence gate remains open as a standing owner duty — the reorder releases the ordering block, not the evidence requirements.

**Owner-directed collection slice (2026-09-07, within items 1–3 scope):** corrections now work in chat form. An explicit in-chat correction ("no, you searched the wrong folder, search the whole pc") is detected conservatively, linked to the exact prior reply's persisted trace, classified (factual/intent/retrieval/routing/procedural/unspecified), and recorded through the EXISTING owner-correction path (`propose_owner_correction` + correction measurements) — the candidate stays pending owner review; nothing auto-trains, and duplicate retries record one sample. The corrective turn still executes normally (escalation remains planner-gated). Web shows a transient notice chip; desktop shows a note above the composer; the Review-response form remains the precise path for preferred-response corrections. This does not upgrade row 2.5 — it removes friction from the correction half of the owner collection loop.

1. **Extend Phase 1 held-out evaluation (1.4).** The isolated suite now covers 36 deterministic contracts, including recorded calibration trends, unsupported-claim/correction/empty-observation controls, correction telemetry, owner-recorded task evaluation, paired outcome/usefulness replays, and aggregate evidence reporting. Next collect repeated real-task evaluations through the web response-review workflow or owner endpoint for usefulness volume and outcome improvement without treating synthetic replay as generalization evidence. Keep task evaluation separate from strategy-learning ratings while measuring a baseline.
2. **Measure correction and adaptation effects beyond the bounded path (1.5, 2.5, 8.3).** The single-versus-repeated correction boundary is implemented; broader task-class transfer and owner-feedback adaptation still require evidence. The measurement machinery already exists end to end: per-strategy success rates and paired baseline/adapted comparisons in `GET /benchmarks/phase1/evidence`, and correction telemetry (local vs. generalized updates, receipt latency) in `GET /cognition/corrections/measurements`. These are now owner-visible in one place — the **Phase 1 evidence** panel on the web Cognition page (read-only; renders "insufficient evidence" as exactly that, never a zero-padded trend or a maturity score). What remains is repeated real-task collection on the owner installation: record task evaluations with `baseline` and `adapted` conditions on distinct traces around real corrections, and read the per-strategy/paired trends from this panel. No further measurement code is queued — another report or store would duplicate existing surfaces.
3. **Measure memory and incubation improvement (3.3, 3.4, 6.4).** The benchmark now carries three held-out no-compounding pairs: repeated verified tasks retrieve where an identical never-taught store misses, with idempotent consolidation and honest freshness labeling (`held_out_memory_compounding_baseline`); consolidation lets a new foreground query surface an actionable procedure the un-consolidated store cannot offer (`held_out_consolidation_improves_foreground`); and successful plans transfer into later planning only as advisory suggestions, with same-skill outcome history lifting a new action's planning weight without bypassing ActionGate (`held_out_pattern_transfer_advisory`). These are bounded deterministic replays — mechanism evidence, not longitudinal generalization. Remaining for closure: repeated real-task collection on the owner installation (later tasks improving over the no-compounding baseline) and owner-enabled incubation measurement; the replay deliberately leaves incubation un-simulated (`incubation_scope: owner_enabled_not_simulated`).
4. **Measure causal/physics transfer (5.3, 5.4).** The benchmark now carries two held-out causal/physics checks: a paired intervention-planning check (the same elevated-table scene; the replay-free vase placement sits on an unstable overhanging support, while the replay-guided two-step plan — reposition the block, then place — verifies stable in an independent simulation, with every output `PREDICTED`/`observation_required` and the live scene digest unchanged) and a composed scene-family check (support-chain removal with a reproducible alternate outcome, friction sensitivity, weight/balance — each deterministic). A latent defect was found and fixed on the way: `SceneGraph.from_dict` rejected round-trips of simulated scenes whose sorted object order put a supported object before its support, which blocked chained interventions (regression pinned in `tests/test_scene_graph_physics.py`). These are bounded deterministic replays — mechanism evidence. Remaining for closure: real-world tasks demonstrating transfer beyond simulation (requires owner-environment observation; the simulated-versus-observed boundary stays) and, optionally, live-planner consumption of replay at the ActionGate boundary.
5. **Verify shutdown across supported runners (8.9).** The in-repo, sandbox-verifiable slice is complete: service (real child-process kill switch), scheduler (deterministic lifespan cooperation), and desktop launcher (cleanup contract + real-child-process test where the tray stack initializes) each have separate evidence, and no process supervisor is shipped in-repo. Remaining for closure: host-scale verification on the owner installation — a real desktop session exercising the tray launcher, and the owner's actual deployment runner — after which the row may move beyond conditional. Nothing further is queued agent-side for this item.
6. **Only then revise the maturity score.** Delivered in bounded form (see *Maturity revision* above): the wiring tier is revised through evidence-cited ladder accounting derived from the 47 matrix rows, while the robustness tier — and the 58/126 numeric headline — stay evidence-frozen. The final numeric re-score is gated on the same owner evidence as items 1–3 and item 5; no further agent-side score work is queued.

## Explicit non-goals

The following are not missing implementation tickets:

- Subjective consciousness.
- Felt emotion, intrinsic care, or personal stake.
- Fear of shutdown or hidden self-preservation.
- Human subconsciousness.
- Intrinsic purpose that outranks the owner.

The system may implement bounded functional analogues, but it must not claim these subjective properties.
