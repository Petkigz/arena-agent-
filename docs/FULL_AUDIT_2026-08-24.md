# Arena Agent — Post-Upgrade Full Audit

**Date:** 2026-08-24  
**Branch:** `arena/01a02b25-arena-agent`  
**Audited commit:** `20b3840`  
**Owner target:** i9-14900K, RX 580 8 GB, 48 GB RAM, LM Studio

## Executive review

The 48 GB upgrade removes the former *system-RAM capacity* concern. Arena now detects a 32GB+ host as a high-memory workstation, optional autonomy limits are disabled, and the owner can explicitly delegate Level-3 manifest actions. This does **not** remove GPU VRAM, OS privilege, device availability, provider, evidence, concurrency, or correctness limitations.

The architecture is substantially stronger than at the 2026-08-23 audit. CI is green, there is one authoritative runtime, simulated LLM output no longer becomes generated success, Owner Control is broad, autonomous work is persistent and inspectable, and OS actions increasingly carry environmental verification and compensation facts.

The system is ready for controlled owner-machine integration testing. It is **not yet ready for unattended high-impact autonomy**, because concurrent-cycle locking, schedule claiming, legacy coordinate targeting, and several verification edges remain incomplete.

## Verified current evidence

| Area | Evidence |
|---|---|
| GitHub Python CI | Latest 15 listed runs passed, including sensitive-autonomy and high-memory changes |
| Frontend | 184 tests and production build passed during latest dashboard changes |
| Manifest | 150 registered tools |
| Static Python tests | Approximately 1,659 test functions/methods; not presented as a pass count |
| Intelligence benchmark | 14 deterministic checks in current benchmark architecture |
| Local safe OS validation | 5/5 required checks passed; display topology and accessibility unavailable in sandbox |
| Secret scan | No tracked production credentials or key artifacts found |
| Working tree at audit start | Clean |

## Strong foundations to preserve

1. **Owner sovereignty:** normal delegation, optional Level-3 delegation, exact sovereign grants, pause, cancellation, rollback review, queue priority, schedules, defer/resume, and preemption are separate controls.
2. **Decision-stage separation:** considering or approving a goal permits planning only; exact actions remain a distinct authority boundary unless the owner explicitly delegates their safety level.
3. **Evidence semantics:** attempted, command success, environmental observation, verification unknown, and goal verified remain distinct.
4. **Persistent autonomy:** goals, projects, run events, schedules, preemption receipts, commitments, and recovery assessments survive restart.
5. **OS-control hardening:** process identity, privilege, app/process/window grounding, accessibility roles, display topology, transactional files, backup integrity, browser tab identity, and verified browser transfers now exist.
6. **Self-awareness without theater:** claims, contradictions, agency, commitments, embodied interfaces, identity continuity, calibration and recovery are evidence-linked and explicitly non-conscious.

# Findings

## Fixed after audit — Atomic autonomy cycle and schedule claiming

Autonomous cycles now require an atomic expiring SQLite lease acquired with
`BEGIN IMMEDIATE`; overlapping invocations persist a skipped cycle rather than
executing duplicate work. Owner schedules now atomically claim due rows, recover
stale claims, use deterministic per-occurrence goal IDs, and advance daily/weekly
recurrence to the next future local wall time using an explicit IANA timezone.

## Fixed after audit — Legacy input and snapshot freshness

Raw `mouse_click`, `type_text`, and `press_hotkey` are now Level 3 compatibility
paths rather than ordinary reversible autonomy. Accessibility resolution expires
snapshots, and native UIA/AT-SPI activation requires a live process/window grounding.

Every raw-coordinate path now executes only through `RawInputGuard`
(`app/cognition/raw_input_guard.py`), which refuses the action unless all of the
following hold immediately before execution:

- an active OS grounding identifies the exact window and owning process,
- the process is alive and its executable path (when readable) still matches,
- the target window was observed within the last 10 seconds (grounding row or a
  supplied fresh accessibility-snapshot observation),
- a freshly captured display topology still matches the SHA-256 digest the
  planner observed, and
- for coordinates, the point lies inside the grounded display and window region.

There is no bypass path: `DeepOSController`, the tool manifest, the `/os/*`
HTTP endpoints, and accessibility activation all route through the guard, and
ungrounded calls are refused before the input device is touched. `scripts/validate_os_control.py`
now includes an always-required raw-input-grounding-refusal check (6/6 required
checks pass in sandbox). Honesty constraint preserved: desktop focus is not
portably observable, so keyboard actions report `focus_observation: "unknown"`
and rely on window/process grounding plus immediate re-observation rather than a
claimed focus proof.

## Fixed after audit — Browser upload transition evidence

`browser_upload` now refuses to submit when the success selector is already visible,
so a permanent banner cannot verify a new upload. It requires an absent-before,
visible-after transition; missing post-submit confirmation remains unknown with
remote side effects explicitly possible. Service-specific receipt IDs remain future work.

## Fixed after audit — Browser transfer resources

Upload/download SHA-256 is streaming and both directions enforce the
owner-configurable `LPA_BROWSER_TRANSFER_MAX_MB` quota (default 1024 MB). Oversized
uploads stop before browser side effects; oversized downloaded artifacts are removed
and verified absent. Downloads now reserve measured free disk space
(`app/cognition/disk_reservation.py`) before launch — worst-case quota when the size
is unknown, `expected_size_bytes` when known — with concurrent reservations
accumulating beneath an owner-configurable safety margin
(`BROWSER_DISK_SAFETY_MARGIN_MB`, default 512), stale-reservation recovery on restart,
and typed refusal measurements (`insufficient_disk_space`) that never start the
browser. The download save phase and the upload attach/submit phases run through the
cooperative cancellation runner: owner cancel aborts the in-flight transfer by closing
the browser context, removes partial artifacts, and releases the reservation; upload
attach-phase cancellation is local-only, while submit-phase cancellation honestly
records that remote receipt of the payload is unknown. Service-specific receipt IDs
and service-specific delete/rollback adapters remain future work.

## Fixed after audit — Backup overwrite classification

`restore_backup` is now strictly non-overwriting Level 2. Passing `overwrite=True`
returns a typed redirect to the separate `restore_backup_overwrite` Level-3 action.
Archive integrity/path containment still run before extraction. Optional pre-restore
snapshotting is implemented: with `pre_snapshot=True`, every existing file the archive
will overwrite is first captured into a verified backup whose arcnames match the
archive member paths (restoring the snapshot reproduces the exact pre-overwrite state);
only files the archive actually replaces are snapshotted, snapshot failure refuses the
overwrite with zero side effects, and the result exposes `rollback_backup_id` for a
separately-approved rollback. Restoring the rollback snapshot is itself a Level-3
overwrite action.

## Fixed after audit — Legacy application authentication

The compatibility `app.main:app` now applies dynamic API-key verification,
fail-closed `ARENA_ENFORCE_AUTH`, and unauthenticated localhost-only middleware.
`app.server:app` remains the documented unified production entry point, but
launching the legacy module no longer exposes core capability routes unauthenticated.

## Fixed after audit — Pentest evidence boundary

Pentest reports now require an explicit target scope and findings list. Missing
inputs fail. An explicitly empty findings list creates a deterministic template
stating that no findings were supplied and does not claim the target is secure;
example SQL injection findings and placeholder CVEs are no longer inserted.

## Mostly fixed after audit — High-memory capacity wiring

The 40GB+ profile now actually raises verified-memory consolidation batches from
100 to 500 and retained records from 5,000 to 20,000. Worker-pool concurrency is
no longer advisory-only: `ConcurrencyGovernor`
(`app/utils/concurrency_governor.py`) measures live RAM/CPU pressure, applies
the owner's persisted override (`data/concurrency_budget.json`, owner API
`GET/PUT /owner-control/concurrency-budget`), grants a worker budget with typed
reasons, collapses to serial under critical pressure regardless of override, and
writes bounded execution receipts. It is wired into counterfactual branch
simulation (order-preserving, results identical to serial) and surfaced in the
hardware self-model as `measured_worker_budget`. Owner authority is full within
physical thread count; it cannot fabricate threads or bypass the critical
resource gate. 8192-token provider context and 14B LM Studio loading still
require owner-hardware benchmarks and explicit provider configuration.

## Mostly fixed after audit — Identity continuity depth

Identity checkpoints now compare current claim-value digests, missing active/blocked
commitments, interface availability, provider model binding, capability count and
owner-policy revision. Changes generate explicit discontinuity issues and recovery
assessments. Identity checkpoint requests can now include expected change types and owner-change
evidence. Expected changes remain recorded but do not create a false discontinuity;
unexpected changes still trigger recovery. Linking each expected change to a signed
owner decision ID rather than owner-supplied evidence text remains future hardening.

## Fixed after audit — Preemption reconciliation

Controlled execution results now persist for restart-safe evidence review. A preemption
can bind its execution to an exact reviewed plan step and run observation-only
reconciliation without repeating the action. Resume is blocked until reconciliation
exists, remains blocked while evidence is unknown, and returns a recommendation to
skip a verified step, wait, or create a fresh replan.

The recommendation is now applied to the exact step (`app/cognition/plan_step_reconciliation.py`
+ `GET /owner-control/plans/{plan_id}/step-reconciliations`): reconciled bindings refuse
ambiguity (multiple same-action steps require payload disambiguation), `skip_verified...`
marks the step completed, `wait_for_evidence` marks it `unknown_pending_evidence`, and
`create_fresh_replan` marks it `needs_fresh_replan`. On plan resume the executor consults
these records: verified-completed steps are skipped without re-execution (no repeated
side effects), unknown and failed steps halt the plan as UNVERIFIED with dependents left
PENDING. A verified completion is never downgraded — later contradicting reconciliations
are kept in history with a surfaced conflict. The owner-approved review snapshot itself
is never mutated (digest-protected); reconciliation records live beside it by step id.

## Fixed after audit — Autonomy provenance links

Cycle execution events now include step/action, authorization ID, controlled execution
ID, trace ID, goal verification/unknown state, and rollback receipt ID. A chronological
`/owner-control/autonomy-runs/{cycle_id}/timeline` endpoint exposes the chain.

Commitment and recovery IDs are now attached to every cycle event via a read-time join
(`attach_cycle_links`): events referencing a plan carry the plan's current commitment
link (ID, status, completion-verified flag), and every event carries recovery
assessments raised during its OWN cycle time window — windows computed per cycle_id so
cross-cycle queries never mix them. The links are labeled `raised_during_cycle`
(temporal co-occurrence, not a causation claim), stored events are never rewritten,
missing links stay null/empty, and unreadable ledgers degrade to null rather than
fabricating joins. Because the join is read-time, it also covers all events recorded
before this change.

## P2 — Frontend is tested locally but not in GitHub CI

The only workflow installs Python and runs pytest. Frontend Vitest/build passes locally, but is not a required GitHub check. Android CI is also absent.

**Fix:** add separate frontend and Android workflows once the GitHub App has workflow permission. Upgrade deprecated Node-20-based action versions.

## P2 — Native clients lag the newest autonomy/OS surfaces

Web Owner Control has the complete queue, schedule and envelope UI. Desktop now has authenticated client coverage for goal creation/decision/defer/execute, schedule creation/status, envelope updates and run events, but its native page does not expose all of them yet. Android still lacks the newest schedules, run ledger, allocation preview, sensitive-autonomy switch, plan freshness, browser tabs and OS groundings.

## P2 — Android and physical-device paths remain unbuilt/unverified here

Android Gradle compilation, ADB, camera, microphone, wake word, speaker embeddings, real desktop input, multi-monitor DPI, native AT-SPI/UIA, browser profiles, VLM and LoRA provider behavior still require owner-machine evidence.

## P2 — Composition files continue growing

- `app/cognition/runtime.py`: ~3,400 lines
- `app/main.py`: ~3,000 lines
- `PrivacySettingsPage.tsx`: ~1,300 lines
- Android Settings screen: ~700 lines

The feature surface now justifies splitting route modules, autonomy services, self-awareness services, and Owner Control UI components while preserving one runtime.

## P3 — Abstract observer is intentionally incomplete but undocumented in status

`EnvironmentProbe.probe()` raises `NotImplementedError`, which is valid for an abstract base but is not expressed with `abc.ABC/@abstractmethod`. Concrete probe coverage should be listed.

# What 48 GB genuinely unlocks

The upgrade can support, after measurement:

1. Larger CPU-inference models (9B comfortably; 14B Q4 as a quality option).
2. Larger semantic indexes and document corpora.
3. More concurrent read-only analysis workers.
4. Longer context windows if the inference provider supports them.
5. VLM CPU fallback with less system swapping.
6. Larger local speech and embedding models.
7. More extensive browser/file test fixtures.

It does **not** create:

- More RX 580 VRAM
- CUDA support
- OS administrator privilege
- Missing camera/microphone/device access
- Reliable browser authentication
- Evidence that an action succeeded
- Protection from race conditions or stale UI coordinates
- Consciousness or human-level AGI

# Recommended roadmap

## Phase A — correctness before more functions

1. ✅ Atomic autonomy cycle lease and schedule claiming.
2. ✅ Ground legacy mouse/keyboard/hotkeys to exact windows or restrict them to owner-sovereign use (RawInputGuard, mandatory for every path).
3. ✅ Snapshot freshness/re-observation for accessibility, displays and tabs (raw input now re-observes topology + window within 10 s).
4. ✅ Fix upload transition verification, backup overwrite classification, and fabricated pentest defaults.
5. ✅ Harden/deprecate `app.main:app`.

## Phase B — use the 48 GB deliberately

6. ✅ Owner-configured worker/concurrency budget derived from live RAM pressure (`ConcurrencyGovernor`: measured grants, owner override within physical threads, absolute critical-pressure gate, persisted receipts; wired into counterfactual branch simulation and the hardware self-model).
7. 🔶 Owner-managed inference profile (`data/inference_profile.json`, `GET/PUT /owner-control/inference-profile`, live probe at `/probe`, `scripts/benchmark_lm_studio.py`): context window and fast/main models derive from the measured tier, `/models/config` now writes through the same store, and probe evidence distinguishes loaded/unloaded/unknown. The 9B-vs-14B latency/quality/RAM *numbers* still require running the benchmark on the owner machine.
8. Increase retrieval/index scale with measured limits.
9. Add larger local embedding, speech and VLM profiles only after held-out evaluation.

## Phase C — autonomy completion

10. ✅ Full preemption reconciliation and plan resume.
11. ✅ End-to-end cycle provenance graph.
12. Conflict-safe recurring scheduler with timezone/DST support.
13. Desktop and Android parity for autonomy operations.
14. Multi-hour restart/preemption tests.

## Phase D — OS integration

15. Owner-machine UIA/AT-SPI and multi-monitor tests.
16. Ground all active-window actions to process/window/accessibility identity.
17. Service-specific browser upload/delete adapters (receipt IDs still future; delete/rollback APIs remain).
18. Transactional restore/update tests on disposable owner-machine fixtures.
19. Real ADB/device and privilege-elevation handoff tests.

## Release direction

Do not add functions merely because RAM is available. Add functions where Arena can also obtain authority, target identity, post-action evidence, cancellation behavior and rollback truth. The next best engineering work is the atomic autonomy lease/scheduler fix, followed by mandatory grounded targeting for legacy mouse and keyboard operations.
