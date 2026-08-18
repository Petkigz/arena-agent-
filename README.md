# Local Personal Assistant — Cognitive Agent Platform

An experimental, local-first personal assistant built around FastAPI, SQLite, LM Studio, a browser dashboard, and an evidence-aware cognitive runtime.

> [!IMPORTANT]
> This repository contains a substantial agent architecture, but it is **not a validated human-level AGI system**. Treat autonomy, self-modification, speaker verification, and “sandbox” claims as experimental until they have passed the safety work listed below.

> [!WARNING]
> **Run on loopback only.** The API does not yet authenticate requests, and several routes can control the host, move files, run commands, operate Android devices, or stop the server. Do not bind it to `0.0.0.0`, expose it to a LAN, port-forward it, or publish it through a tunnel until the API security milestone is complete.

## Current status

Snapshot audited on **2026-08-18**:

- 258 commits recovered from the previous development branch.
- 260 automated tests passing locally.
- Latest GitHub Actions baseline runs passing.
- 122 OpenAPI paths / 128 API operations, plus dashboard and static routes.
- 230 Python source and test files parse successfully.
- FastAPI app imports successfully with 134 total registered routes, including framework/static routes.
- Dashboard HTML and inline JavaScript pass structural and syntax checks.

See:

- [`docs/recovery-handoff.md`](docs/recovery-handoff.md) — recovered architecture, recent work, risks, and continuation plan.
- [`docs/dashboard-audit.md`](docs/dashboard-audit.md) — dashboard/PWA audit and validation results.
- [`docs/phase3-reasoning.md`](docs/phase3-reasoning.md) — evidence and closed-loop reasoning.
- [`docs/phase4-memory-learning.md`](docs/phase4-memory-learning.md) — persistent memory and controlled learning.

## Architecture

```text
Dashboard / API / voice input
            |
            v
     CognitivePipeline
            |
            v
     CognitiveRuntime
       |    |    |
       |    |    +--> Memory, reflection, trace telemetry
       |    +-------> World model, evidence, beliefs, hypotheses
       +------------> Goal interpretation and reasoning loop
                              |
                              v
                    Candidate action proposal
                              |
             Policy + resource + prediction gates
                              |
                              v
                    Capability/tool execution
                              |
                              v
                   Direct perception/observation
                              |
                              v
              Goal verification -> replan/defer/finish
```

The recent implementation deliberately distinguishes four facts that must not be collapsed:

1. An action was attempted.
2. A tool reported successful execution.
3. The environment was directly observed afterward.
4. The user’s goal was verified as achieved.

A successful tool call alone is not proof that the world changed or that the goal was achieved.

## Main components

| Area | Important modules | Responsibility |
|---|---|---|
| API and dashboard | `app/main.py`, `app/static/` | FastAPI endpoints, dashboard, PWA shell |
| Canonical pipeline | `app/cognition/cognitive_pipeline.py`, `app/cognition/pipeline.py` | Single entry path into the cognitive runtime |
| Cognitive composition | `app/cognition/runtime.py` | Owns state, world model, memory, reasoning, planning, verification, and tracing |
| Goals | `goal_interpreter.py`, `goal_lifecycle.py`, `goal_verifier.py`, `goal_replanner.py` | Structured goals, state transitions, tri-state verification, strategy-level replanning |
| Epistemics | `world_model.py`, `beliefs.py`, `belief_engine.py`, `hypotheses.py`, `confidence.py` | Evidence provenance, observations, belief revision, contradictions, confidence |
| Decisions and actions | `reasoning_cycle.py`, `reasoning_loop.py`, `action_planner.py`, `action_proposal.py` | Decide whether to answer, investigate, act, or defer; gate proposed actions |
| Execution | `app/agents/master_agent.py`, `app/tools/` | Execute supported capabilities and return structured execution results |
| Perception | `app/cognition/perception.py`, `app/perception/` | Convert tool output into separately sourced observations; STT/TTS integrations |
| Memory and learning | `app/cognition/memory.py`, `memory_learning.py`, `reflection.py`, `app/memory/` | Episodic/semantic/procedural memory, bounded retrieval, explicit consolidation |
| Persistence | `app/database.py`, SQLite under `data/` | Tasks, memories, audit records, cognitive state and telemetry |
| Safety | `app/policy.py`, `memory/rules.md`, action gates | Permission classification and proposal checks; not yet a complete API perimeter |

## Features

### Cognitive core

- Shared cognitive state, attention, blackboard, event bus, sessions, and checkpoints.
- Persistent world model with entities, relationships, observations, provenance, and changes.
- Evidence-backed belief revision with contradictions and competing hypotheses.
- Bounded investigate/observe/reason loops.
- Goal Representation v2 with desired outcomes, constraints, unknowns, and required capabilities.
- Candidate strategy synthesis and counterfactual branch simulation.
- Policy/resource/prediction action gates.
- First-class execution results separate from environmental observations.
- Direct-observation, subject-bound, tri-state goal verification.
- Strategy-instance replanning rather than eliminating an entire capability.
- Reflection, memory learning, prediction surprisal, and trace persistence.

### Interfaces and tools

- Single-file responsive dashboard with simple/expert modes.
- LM Studio dual-model routing for fast and deep requests.
- Task queue, memories, audit logs, user manual, and rules editor.
- Faster-Whisper transcription and system TTS integration.
- Screen capture, OCR, and local vision-model requests.
- Browser automation and HTTP extraction fallback.
- Desktop, filesystem, Android ADB, data analysis, and workflow tools.
- Local specialist helpers for coding, defensive security, finance simulation, content, media, and documents.
- Experimental capability synthesis, taught skills, self-healing, and self-evolution modules.

Some integrations are platform-dependent and are not validated by the default test suite against real hardware. See [External requirements](#external-requirements).

## Safe local setup

### Requirements

- Python 3.11+
- LM Studio for local model inference
- Git

```bash
python3 -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optional configuration uses Pydantic’s `LPA_` environment prefix. Copy the example and edit model names or the LM Studio URL:

```bash
cp .env.example .env
```

Start the application on loopback:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

- Dashboard: <http://127.0.0.1:8000/>
- Swagger UI: <http://127.0.0.1:8000/docs>
- JSON status: `curl -H 'Accept: application/json' http://127.0.0.1:8000/`

Do **not** use the tray launcher’s current LAN binding on an untrusted network. It still starts Uvicorn on `0.0.0.0` and is tracked as a security-hardening item.

## LM Studio configuration

The defaults are:

```text
LPA_LM_STUDIO_URL=http://localhost:1234/v1
LPA_FAST_MODEL=qwen2.5-3b-instruct
LPA_MAIN_MODEL=qwen2.5-9b-instruct
LPA_DEFAULT_TIMEOUT=180
```

Model IDs must match the IDs exposed by LM Studio’s OpenAI-compatible `/v1/models` endpoint. Model availability, VRAM offload, and response quality depend on the local machine and selected GGUF models.

## Tests

```bash
python -m pytest -q
```

Audited result:

```text
260 passed, 3 warnings in 7.31s
```

The warnings came from Starlette’s multipart import deprecation and missing Linux desktop notification packages in the sandbox. They did not indicate test failures.

The suite covers the API, persistence, policies, cognitive contracts, world state, evidence provenance, belief revision, goal lifecycle, planning, execution/result separation, verification, replanning, memory, tracing, and many tool adapters. It does **not** prove real-world AGI capability or fully exercise LM Studio, microphones, desktop GUI control, Android devices, browser binaries, Tesseract, Docker, or Windows-only integrations.

## External requirements

| Feature | Additional requirement |
|---|---|
| Local inference | LM Studio running with compatible model IDs |
| Browser screenshots/automation | Playwright browser binary: `python -m playwright install chromium` |
| OCR | Tesseract installed on the host |
| Voice transcription | Faster-Whisper model download and a supported audio input |
| System speech | Working `pyttsx3` host driver |
| Android control | Android platform tools / `adb`, authorized device |
| Desktop automation | Graphical desktop session and `pyautogui` support |
| Windows ghost operator | Windows host APIs |
| Container isolation | Docker/WSL configured; native subprocess fallback is not isolation |
| Notifications | Host notification service (`notify-send`/DBus on Linux) |

Voice reference profiles are currently stored and selected, but the `pyttsx3` backend does not implement genuine voice cloning. The UI now describes this as experimental reference-profile support.

## Data and repository boundaries

Runtime state is written under `data/` and ignored by Git:

```text
data/
├── assistant.db
├── audio/
├── logs/
├── sandboxes/
└── workspace/
```

The committed `memory/` directory contains human-authored operating guidance and policy boundaries. Do not commit private runtime data, model files, recordings, credentials, or `.env` files.

## Safety levels

The intended policy is defined in [`memory/rules.md`](memory/rules.md):

| Level | Class | Examples | Intended behavior |
|---:|---|---|---|
| 0 | Observe/read | Search, inspect, capture | Autonomous |
| 1 | Draft | Create drafts in approved workspaces | Autonomous in bounds |
| 2 | Reversible | Open an approved app, organize files | Logged |
| 3 | Sensitive/irreversible | Shell commands, submissions, deletion, transactions | Explicit approval required |

Current limitation: these rules are enforced by the canonical action proposal path, but many direct API routes bypass that path. Network authentication and centralized route-level authorization are the top priority before remote use.

## Recovery roadmap

1. **P0 — Security perimeter**
   - Loopback by default, authenticated remote mode, CSRF/origin controls, and explicit approval tokens.
   - Route every state-changing API operation through centralized authorization.
2. **P0 — Truthful execution across legacy tools**
   - Fail closed in speaker verification, self-evolution, capability synthesis, browser fallbacks, and sandbox execution.
   - Never convert an exception, placeholder, or unobserved side effect into success.
3. **P0 — Real isolation**
   - Remove native-shell fallback for untrusted code and define enforceable Docker/WSL sandbox guarantees.
4. **P1 — Dashboard hardening**
   - Modularize the 119 KB single-file UI, improve accessibility, add browser-level tests, and add approval workflows.
5. **P1 — Real integration tests**
   - Add opt-in tests for LM Studio, browser, OCR, voice, desktop, Android, and container environments.
6. **P2 — Cognitive evaluation**
   - Add measurable task suites for calibration, long-horizon recovery, transfer, resource use, and human supervision—not only unit assertions.

## Repository layout

```text
app/
├── agents/       # Orchestration, multi-agent, proactive and self-evolving agents
├── cognition/    # State, world, evidence, reasoning, goals, planning, verification
├── memory/       # RAG, reflection, constitution, user-model helpers
├── perception/   # Speech input/output
├── runtime/      # Resource-aware runtime helpers
├── scheduler/    # Proactive jobs and self-healing
├── static/       # Dashboard and PWA assets
├── tools/        # Host, web, document, data, media and specialist capabilities
├── main.py       # FastAPI composition and routes
├── database.py   # SQLite persistence
├── llm.py        # LM Studio client
└── policy.py     # Permission classifier

docs/             # Architecture, recovery, and audit notes
memory/           # User-maintained rules and operating manual
tests/            # Unit and integration contracts
```

## Development principles

- Preserve the four-way distinction: **attempted ≠ executed ≠ observed ≠ achieved**.
- Treat model output as a proposal or interpretation, not environmental evidence.
- Require provenance for durable beliefs and goal verification.
- Fail closed at safety and identity boundaries.
- Keep deterministic bookkeeping local and cheap.
- Add a regression test for every corrected invariant.
- Keep runtime data and secrets out of Git.
