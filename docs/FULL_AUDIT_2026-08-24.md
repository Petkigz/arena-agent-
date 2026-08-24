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

## P1 — Legacy mouse/keyboard/hotkey actions bypass semantic target grounding

`mouse_click`, `type_text`, and `press_hotkey` still act on coordinates or the active window without requiring an OS/window/accessibility grounding ID. The new semantic path is safer, but autonomous plans can still select legacy actions.

**Fix:** add `target_grounding_id`, expected window/process identity, topology digest, and freshness requirement. Keep raw-coordinate actions only as explicit owner sovereign commands or a compatibility mode.

## P1 — Accessibility and display snapshots can become stale

Accessibility nodes and display topology have no enforced expiry. UI layout, active window, monitor arrangement, DPI, or process identity can change after capture. `accessibility_activate` can therefore click old bounds.

**Fix:** timestamp and expire snapshots, bind each tree to process/window grounding plus display-topology digest, and re-observe immediately before activation.

## P1 — Browser upload confirmation can be a false positive

`browser_upload` verifies that `success_selector` is visible after submission, but does not prove it was absent before the click or changed because of this upload. A permanently visible success banner can incorrectly verify the goal.

**Fix:** capture pre-state, require a transition or service-specific receipt/response identifier, and preserve response/download evidence. Keep unknown if no transition occurs.

## P1 — Browser transfer hashing is not streaming or size-bounded

Browser upload/download hashing uses `Path.read_bytes()`. A large file can consume substantial RAM despite the 48 GB upgrade, and downloads have no owner-configured size quota.

**Fix:** stream SHA-256, enforce optional owner size/quota limits, check free disk before save, and cancel oversized transfers.

## P1 — Backup overwrite restore is under-classified

`restore_backup` is manifest Level 2 even when `overwrite=True`. Overwriting existing files can destroy owner data, and the code correctly admits automatic rollback is unsafe.

**Fix:** split non-overwriting restore (Level 2) from overwrite restore (Level 3), inventory conflicts before extraction, and optionally create a pre-restore snapshot under separate owner authorization.

## P1 — Legacy `app.main:app` remains an unauthenticated entry point

`app.server:app` applies API-key and localhost/LAN hardening. The backward-compatible `app.main:app` exposes core routes without that server wrapper. Launching the wrong module can bypass the intended deployment boundary.

**Fix:** make `app.main:app` delegate to the hardened app factory, or refuse non-test startup and clearly deprecate it.

## P1 — Pentest report generation fabricates findings when none are supplied

`PentestCompanyAssistant.generate_pentest_report()` substitutes example SQL injection/header findings and `CVE-2024-XXXX` when `vulnerabilities_found` is empty. A generated client report can therefore contain invented vulnerabilities.

**Fix:** require explicit findings or generate an explicitly labeled template with zero findings. Never place example findings in a report returned as successful evidence.

## P1 — High-memory concurrency is described but not wired

The hardware self-model reports `max_parallel_cpu_tasks: 6` and an 8192-token budget for high-memory hosts, but the autonomous scheduler, model client, and worker pools do not consume those values. The 14B recommendation is metadata; it does not load/configure LM Studio.

**Fix:** pass a verified resource budget into scheduling and inference routing, add owner-configured concurrency, benchmark latency/RAM on the actual 48 GB machine, and gate increases on measured pressure.

## P2 — Identity continuity misses some meaningful changes

The checkpoint stores active commitment sources and a state digest but does not report lost/added commitments. It compares claim predicates, not claim values/evidence, so a changed hardware fact under the same predicate may not be flagged.

**Fix:** compare commitment sets, current claim digests, interface availability and model/provider binding, with expected-change exemptions linked to owner decisions.

## P2 — Preemption records resume intent but does not orchestrate full resume

Receipts correctly block blind replay, but `request-resume` does not yet run observation-only reconciliation, reconstruct the exact pending step, or produce a fresh revised plan automatically.

**Fix:** implement `resume_review` that observes existing side effects, marks completed steps, invalidates stale assumptions, and returns a new recommendation for owner review.

## P2 — Autonomy run events need stronger cross-links

The ledger records cycle, goal, plan and allocation details, but not every final authorization ID, execution trace ID, verification record, rollback receipt, or commitment ID in one queryable chain.

**Fix:** persist canonical foreign keys for end-to-end provenance and expose a cycle timeline endpoint.

## P2 — Frontend is tested locally but not in GitHub CI

The only workflow installs Python and runs pytest. Frontend Vitest/build passes locally, but is not a required GitHub check. Android CI is also absent.

**Fix:** add separate frontend and Android workflows once the GitHub App has workflow permission. Upgrade deprecated Node-20-based action versions.

## P2 — Native clients lag the newest autonomy/OS surfaces

Web Owner Control has the complete queue, schedule and envelope UI. Desktop/Android do not yet expose all newer controls: schedules, run ledger, allocation preview, sensitive-autonomy switch, plan freshness, browser tabs, and OS groundings.

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

1. Atomic autonomy cycle lease and schedule claiming.
2. Ground legacy mouse/keyboard/hotkeys to exact windows or restrict them to owner-sovereign use.
3. Snapshot freshness/re-observation for accessibility, displays and tabs.
4. Fix upload transition verification, backup overwrite classification, and fabricated pentest defaults.
5. Harden/deprecate `app.main:app`.

## Phase B — use the 48 GB deliberately

6. Owner-configured worker/concurrency budget derived from live RAM pressure.
7. Benchmark 9B versus 14B inference latency, quality and RAM.
8. Increase retrieval/index scale with measured limits.
9. Add larger local embedding, speech and VLM profiles only after held-out evaluation.

## Phase C — autonomy completion

10. Full preemption reconciliation and plan resume.
11. End-to-end cycle provenance graph.
12. Conflict-safe recurring scheduler with timezone/DST support.
13. Desktop and Android parity for autonomy operations.
14. Multi-hour restart/preemption tests.

## Phase D — OS integration

15. Owner-machine UIA/AT-SPI and multi-monitor tests.
16. Ground all active-window actions to process/window/accessibility identity.
17. Service-specific browser upload/delete adapters.
18. Transactional restore/update tests on disposable owner-machine fixtures.
19. Real ADB/device and privilege-elevation handoff tests.

## Release direction

Do not add functions merely because RAM is available. Add functions where Arena can also obtain authority, target identity, post-action evidence, cancellation behavior and rollback truth. The next best engineering work is the atomic autonomy lease/scheduler fix, followed by mandatory grounded targeting for legacy mouse and keyboard operations.
