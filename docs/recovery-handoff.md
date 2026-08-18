# Recovery Handoff — 2026-08-18

This document reconstructs the repository state after the previous Arena agent session became inaccessible. It is intended to make the next continuation recoverable from Git alone.

## Snapshot

| Item | Value |
|---|---|
| Active Arena branch | `arena/01a014f8-arena-agent` |
| Recovered source commit | `a173110ea85c761fc57227c572284ea40f22932a` |
| Previous remote branch | `arena/019febb5-arena-agent` |
| Base/main commit visible during recovery | `10fcb29400b9a4f79557fd2a9abf1ccea79dc9ac` |
| Recovered history | 258 commits |
| Tracked files at recovery | 243 |
| Python lines (`app` + `tests`) | approximately 18,530 |
| Automated tests at recovery | 255 passing |
| OpenAPI surface | 122 paths / 128 operations |
| Existing pull request | PR #2, open, clean, but stale title/body |

The working tree was clean when recovered. GitHub Actions showed successful runs for the latest commit and the preceding hardening commits.

## What this project is

The codebase is an experimental local-first assistant platform with:

- A FastAPI API and single-page/PWA dashboard.
- Local LM Studio model routing.
- SQLite task, memory, audit, world-state, and trace persistence.
- A cognitive runtime with state, attention, blackboard, events, world modeling, beliefs, goals, planning, execution, perception, verification, replanning, reflection, and learning.
- Voice, vision, browser, desktop, filesystem, Android, document, data, media, security, and workflow adapters.
- Experimental self-healing, capability synthesis, skill teaching, and self-evolution.

It is a meaningful agent architecture, but the repository does not establish human-level intelligence or general intelligence. Those claims require external evaluation, long-horizon task performance, calibration measurements, safety validation, and comparison against human baselines.

## Canonical request path

The intended request path is:

```text
POST /chat
  -> app.cognition.pipeline.PipelineBridge
  -> app.cognition.cognitive_pipeline.CognitivePipeline
  -> app.cognition.runtime.CognitiveRuntime.process_cognitive_cycle
  -> SemanticGoalInterpreter
  -> WorldModel + BeliefEngine
  -> CognitiveReasoningLoop
  -> candidate ActionProposal
  -> ActionGate
  -> MasterAgentOrchestrator.execute_proposal
  -> ExecutionResult
  -> PerceptionLayer direct observation
  -> GoalVerifier
  -> GoalReplanner when required
  -> Reflection + MemoryLearner + CognitiveTrace
```

`MasterAgentOrchestrator.process_user_task` is now a compatibility adapter back into the same canonical path. The old intent helpers in `app/main.py` also delegate to the canonical pipeline.

## Recovered cognitive architecture

### State and coordination

- `CognitiveState` holds session, task, attention, execution, world, and memory-facing state.
- `Blackboard` provides bounded working-memory exchange.
- `EventBus` emits cognitive lifecycle events.
- Checkpoints and sessions support persistence and isolation.
- `CognitiveTrace` persists inspectable telemetry.

### World knowledge and epistemics

- `WorldModel` persists entities, relationships, observations, and changes.
- Observations carry source, confidence, timestamp, and observation type.
- `BeliefStore` and `BeliefEngine` preserve evidence and contradictions.
- Competing hypotheses remain explicit instead of uncertainty being collapsed into one fact.
- Source reliability and evidence freshness affect confidence.

### Goals and decisions

- Goal Representation v2 contains desired outcomes, constraints, unknowns, required capabilities, domain, and confidence.
- `ReasoningCycle` chooses `ANSWER`, `INVESTIGATE`, `ACT`, or `DEFER`.
- Capability availability is resolved before action selection.
- Candidate strategies preserve exact payload and synthesizer provenance.
- Counterfactual simulation scores competing branches.
- Goal lifecycle transitions are validated.

### Execution and verification

- `ActionProposal` is the executable contract.
- `ActionGate` applies policy, resource, and prediction checks.
- `ExecutionResult` records attempted/executed/failed status without pretending it is a world observation.
- The perception layer creates direct observations separately.
- Goal verification is subject-bound and routes evidence by condition type.
- Condition verification is tri-state: `SATISFIED`, `FAILED`, or `UNKNOWN`.
- Missing evidence triggers re-observation or deferral rather than fabricated success.
- Replanning excludes a failed strategy instance, identified by `strategy_id`, rather than an entire capability.

## Exact focus of the previous agent

The final development sequence was a concentrated P0 epistemic correctness pass. The main invariant was:

> **Attempted action ≠ tool success ≠ observed environmental state ≠ verified goal achievement.**

Recent work, newest last:

1. Introduced `ExecutionResult` / `ExecutionStatus` as first-class types.
2. Separated execution results from environmental observations.
3. Injected one authoritative `WorldModel` through execution and grounding.
4. Separated world-state evidence from trace and assistant-response payloads.
5. Bound verification evidence to canonical target entities.
6. Required direct observation provenance for environmental conditions.
7. Added tri-state condition verification.
8. Routed condition types so language output cannot satisfy environmental action goals.
9. Added canonical entity matching to prevent substring collisions.
10. Preserved exact candidate action payload/provenance.
11. Made `strategy_id` the replanning failure unit.
12. Prevented self-reported execution facts from creating world-model entities.
13. Made process probes establish only `running` or `not_running`, without fabricating a `launched` observation.

This is the logical thread to preserve in future work.

## Validation performed during recovery

### Passed

- `python -m compileall -q app tests`
- AST parsing across 229 Python source/test files.
- `python -m pip check`
- FastAPI import and route construction.
- `python -m pytest -q`: **255 passed**.
- Latest GitHub Actions runs: successful.
- Dashboard HTML parsing: valid enough for BeautifulSoup, 372 elements, 85 unique IDs, no duplicates.
- Dashboard inline JavaScript: `node --check` passed.
- Dashboard-to-API route inventory: every JavaScript endpoint has a corresponding FastAPI route.
- FastAPI in-process smoke checks for HTML root, JSON root, status, manifest, service worker, Swagger UI, and OpenAPI.

### Environment-dependent validation not performed

- Real LM Studio inference.
- Real microphone or Faster-Whisper model execution.
- Real Tesseract OCR.
- Real desktop GUI automation.
- Real Android ADB device control.
- Real Windows-only operator behavior.
- Real Docker/WSL isolation.
- Browser rendering with Playwright. The browser package was installed, but the Chromium binary download failed because the CDN connection reset.

## P0 findings

### 1. Unauthenticated host-control API

**Severity: critical**

The app and tray documentation historically bind to `0.0.0.0`, but the API has no authentication or centralized route authorization. Direct endpoints expose functionality including:

- Shell command execution through `/sandbox/run`.
- OS click, typing, hotkeys, app launch, and software update.
- Filesystem move/compress/write operations.
- Android ADB actions.
- Dynamic code generation and import.
- Self-healing and capability synthesis.
- Server shutdown.

Most direct routes call tool methods without passing through `ActionGate`. Until fixed, use `127.0.0.1` only.

### 2. “Sandbox” may be a host shell

**Severity: critical**

`DisposableSandbox` always creates a directory, but that directory is not an isolation boundary. Depending on host and requested guest OS, commands run via `subprocess.run(..., shell=True)` on the host. If Docker/WSL/Wine/ADB execution fails, the code may fall back to a native host shell.

A changed working directory does not restrict filesystem, process, or network access. Untrusted model-generated code must never use this fallback.

### 3. Self-evolution can fabricate success

**Severity: high**

`SelfEvolvingAgent` currently:

- Prompts an LLM for executable Python.
- Runs a sandbox test but does not require that test to pass before writing/importing.
- Writes into `app/tools/`.
- Imports and executes the module in the live process.
- Forces `success=True` on returned dictionaries.
- Converts import/execution exceptions into a successful synthesis result.

This violates the final closed-loop correctness invariant.

### 4. Capability factory reports success after failed registration

**Severity: high**

`CapabilityFactory` calls `WorldModel.add_entity`, but the current world-model API provides `upsert_entity`. The resulting exception is logged and swallowed, after which the factory returns success. The factory docstring also claims sandbox verification and hot reload that the implementation does not perform.

### 5. Speaker verification fails open

**Severity: high**

When no voice profile exists, all audio is accepted. When parsing/verification raises an exception, `verify_speaker_voice` returns `verified=True`. Voice identity must not be used as an authorization boundary until it fails closed and uses a validated biometric design.

### 6. Voice-cloning claim is inaccurate

**Severity: high for truthfulness, medium operational risk**

The UI and API refer to voice cloning, but the TTS implementation uses `pyttsx3`; it stores a reference WAV without applying that reference to synthesized timbre. It can return `custom_voice_cloned=True` even though no cloning engine is used.

### 7. Browser fallback can fabricate navigation

**Severity: high for truthfulness**

If Playwright and HTTP extraction both fail, `BrowserAutomation.navigate_and_extract` still returns `success=True` with synthetic text saying navigation initialized successfully.

### 8. Documentation and architecture drift

**Severity: medium**

Before this recovery pass, the README described 15 tests, an early Version 0 architecture, and roadmap phases that had already been implemented. The main API module is 1,471 lines and the dashboard is a roughly 119 KB single HTML file.

### 9. Duplicate/stale modules

**Severity: low/medium**

- `app/scheduler.py` and the `app/scheduler/` package coexist. Python resolves imports to the package; the file is effectively stale and both copies start a scheduler at import time.
- `app/cognition/pipeline.py` is a compatibility bridge over `cognitive_pipeline.py`.
- Some older cognitive primitives are tested in isolation but no longer participate directly in the canonical runtime.

These should be removed only with explicit compatibility tests.

## Prioritized continuation plan

### Milestone A — secure the perimeter

1. Bind launchers to loopback by default.
2. Add explicit local/remote deployment mode.
3. Add authenticated sessions or API tokens stored outside Git.
4. Add trusted-host/origin and CSRF protections.
5. Define a route-level capability/permission dependency.
6. Require expiring approval records for Level 3 actions.
7. Add tests proving every mutating route is classified and gated.

### Milestone B — carry truthfulness through legacy tools

1. Make speaker verification fail closed.
2. Correct voice-reference and TTS result claims.
3. Make browser fallback return failure when no content was retrieved.
4. Rewrite `CapabilityFactory` around the real `WorldModel` API.
5. Require successful compile, static review, isolated test, and explicit approval before dynamic tool activation.
6. Stop forcing tool-returned success values.
7. Add negative-path tests for every exception and unavailable dependency.

### Milestone C — establish real isolation

1. Split trusted developer subprocesses from untrusted execution.
2. Require a configured container/VM for untrusted code.
3. Remove host-native fallback from the untrusted path.
4. Set CPU, memory, process, filesystem, network, and timeout limits.
5. Make the isolation backend and guarantees explicit in every result.

### Milestone D — dashboard and maintainability

1. Add authentication and approval UX.
2. Split dashboard CSS/HTML/JavaScript into modules.
3. Add browser-based tests and accessibility checks.
4. Generate an API client or validate payloads against OpenAPI.
5. Move FastAPI routes into domain routers.
6. Remove duplicate modules after deprecation coverage.

### Milestone E — intelligence evaluation

1. Define task suites with objective outcomes and direct observation.
2. Measure calibration, false-success rate, recovery rate, and supervision burden.
3. Add long-horizon interruption/resumption tests.
4. Evaluate memory transfer and catastrophic error resistance.
5. Track resource budgets and local-model quality by model/hardware profile.

## Non-negotiable continuation invariants

1. Never use LLM text as direct environmental evidence.
2. Never mark a goal achieved solely because a tool returned success.
3. Never convert an exception into success.
4. Never treat a placeholder/fallback result as performed work.
5. Never claim isolation without an enforced isolation boundary.
6. Never let identity verification fail open.
7. Preserve exact candidate payload and provenance through execution.
8. Keep one injected world model/memory/tool registry per runtime context.
9. Every P0 correction gets a negative-path regression test.
10. Keep secrets, recordings, model files, databases, and runtime data out of Git.

## Useful commands

```bash
# Environment
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Validation
python -m pytest -q
python -m compileall -q app tests
python -m pip check

# Safe local launch
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Inspect recent recovered work
git log --oneline -60
```
