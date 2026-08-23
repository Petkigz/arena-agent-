# Local Cognitive Assistant — Coworker Platform

A **full-capability local-first coworker** that perceives its environment, understands goals, reasons under uncertainty, plans and executes actions, observes what actually happened, verifies success, remembers lessons, and improves — while the owner retains control over sensitive actions through configurable approval gates.

Runs **entirely locally** on Intel Core i9-14900K, RX 580 GPU (8 GB), and system RAM, connected to **LM Studio** for model inference (Qwen 3B fast model + Qwen 9B reasoning model).

> **📖 Documentation:** see [`AGI_MEASURED_STATUS.md`](AGI_MEASURED_STATUS.md) for the
> authoritative, measured status (test counts, module wiring, capability scorecard)
> and [`docs/README.md`](docs/README.md) for the full documentation index. Earlier
> "X% AGI" status docs have been archived under `docs/archive/` and are not
> authoritative.

---

## Core Philosophy

```
Local before cloud. Evidence before belief.
Verification before success. Safety before autonomy.
Owner authority before self-action.
```

### Full-Capability Design

This is a **coworker**, not a capability-restricted demo. No domain is permanently forbidden:

- **Cybersecurity**, **trading**, **system administration**, **communications**, **automation** — all exist as capabilities
- Sensitive actions enter an **approval state** rather than being deleted from the capability set
- The owner defines which commands require confirmation and what environments the assistant controls
- Capability ≠ autonomous execution. The policy system distinguishes:
  - *Can the agent do this?* (capability availability)
  - *May it execute this autonomously right now?* (approval gate)

---

## Cognitive Architecture

The system implements a closed-loop cognitive pipeline that separates four fundamental facts:

```
1. "I tried it"           → ExecutionResult.attempted = True
2. "The tool said it worked" → ExecutionResult.status = SUCCEEDED
3. "I observed it worked" → WorldModel Observation (direct environmental probe)
4. "The goal is proven"   → GoalVerifier verified_success = True (ACHIEVED)
```

### Pipeline Flow

```
User Request
    → SemanticGoalInterpreter (structured goal, success/failure conditions)
    → ReasoningCycle (ACT / INVESTIGATE / DEFER / ANSWER)
    → CounterfactualSimulator (parallel strategy simulation)
    → ActionPlanner (select winning strategy)
    → ActionGate (safety policy, capability check)
    → MasterAgentOrchestrator (execute selected action)
    → ObservationCollector (independent environmental probes)
    → GoalVerifier (tri-state: SATISFIED / FAILED / UNKNOWN)
    → GoalReplanner (Plan B on failure)
    → Reflection & Memory
```

### Evidence Architecture

**Primitive evidence is not authoritative.** Every environmental claim must carry structured provenance:

```python
# ✅ Authoritative — structured with provenance
{"value": "running", "source": "os_process_probe",
 "confidence": 1.0, "observation_type": "direct"}

# ❌ Not authoritative — primitive value, no provenance
"running"   # → UNKNOWN
"crashed"   # → UNKNOWN
```

Both positive and negative claims require provenance. Unknown remains unknown until direct observation resolves it.

---

## Capability-Specific Observation Strategies

Each capability family has dedicated post-action environmental probes. Execution success is **never** used as evidence:

| Capability | Observation Strategy |
|---|---|
| `open_application` | Process probe via psutil — running or not_running |
| `search_files` | Filesystem probe — first result + complete result set |
| `web_search` | Fresh independent search probe via urllib |
| `screen_capture` | File existence + Pillow image validation |
| `phone_command` | Action-specific ADB probes (battery, call state, foreground app) |
| `run_command` | Declared postcondition probe (file/process/port) |
| `diagnostic` | Independent filesystem + hardware telemetry |

Actions without reliable postcondition sensors (SMS, screen taps, camera) remain **UNKNOWN** rather than claiming success.

---

## Directory Structure

```
arena-agent-/
├── app/
│   ├── agents/           # Thin agent loops (coding, data analysis) sharing the one brain
│   │   ├── coding_agent.py      # Plan→write→test→iterate, shares ONE brain
│   │   ├── data_analysis_agent.py # Read-only SQL/pandas, shares ONE brain
│   │   └── self_evolving_agent.py # Verified: synthesize→pytest→hotload only if green (P2)
│   ├── cognition/        # Cognitive pipeline (reasoning, goals, verification) — 17 modules wired
│   │   ├── runtime.py           # CognitiveRuntime (main orchestration, 17 modules, multimodal)
│   │   ├── goal_interpreter.py  # Semantic goal parsing
│   │   ├── goal_verifier.py     # Tri-state condition verification
│   │   ├── goal_replanner.py    # Plan B generation (resource-aware)
│   │   ├── goal_decomposer.py   # Long-horizon decomposition → sub-goals DAG (P2)
│   │   ├── project_manager.py   # Multi-session project tracking (P2)
│   │   ├── temporal_vision.py   # Persistent stream-isolated object continuity + events
│   │   ├── perception.py        # Environmental observation strategies
│   │   ├── world_model.py       # Entity/observation store
│   │   ├── reasoning_loop.py    # ACT/INVESTIGATE/DEFER/ANSWER routing
│   │   ├── counterfactual_simulator.py # Resource-aware (cpu/memory/time) + Hist/Lesson/Skill/Res
│   │   ├── causal_inference.py  # Learns from execution + surprisal (Bayesian) (P1-2)
│   │   ├── language_grounding.py # Perceptual/motor/multimodal groundings (populated via detector)
│   │   ├── social_cognition.py  # Theory of mind + emotion from prosody + text (P2)
│   │   └── action_proposal.py   # ActionGate safety evaluation
│   ├── memory/           # Verifier-authored episodes → provenance-linked semantic/procedural memory
│   ├── perception/       # Low-level perception (screen, OCR, audio, Piper)
│   ├── runtime/          # Runtime state management
│   ├── scheduler/        # Task scheduling + autonomous cycle (hourly)
│   ├── static/           # Dashboard UI (HTML/JS PWA)
│   ├── tools/            # 137 capability tools (manifest) — vision grounding + VLM + LoRA + prosody
│   │   ├── object_detector.py   # Face via Haar + YOLO/SSD fallback + auto-grounding (P1-1)
│   │   ├── vlm_analyzer.py      # True VLM Moondream2/Llava with OCR+LLM fallback (P3, optional)
│   │   ├── prosody_analyzer.py  # Voice pitch/energy/ZCR → emotion from real signals (P2)
│   │   ├── lora_manager.py      # Owner-reviewed train/eval datasets + PEFT adapter tooling (P3)
│   │   └── manifest.py          # Single source of truth for all tools
│   ├── utils/            # Logging, hardware monitor/governor (P/E cores, VRAM)
│   ├── main.py           # FastAPI core router (now 140+ routes: vision grounding, VLM, LoRA, projects)
│   ├── llm.py            # LM Studio client & model router (single loaded model)
│   ├── database.py       # SQLite persistence (conversations, memories, beliefs)
│   ├── settings_store.py # Shared settings (backend source of truth for web/desktop/Android)
│   └── policy.py         # Action policy (Levels 0-3, approval-gated not removed)
├── docs/                 # Architecture documentation
├── memory/               # User rules & operating manual
│   ├── rules.md          # Permission boundaries
│   └── user_operating_manual.md
├── tests/                # backend pytest suite + frontend Vitest suite
├── requirements.txt                 # Core + software-only developer/CI tools
├── requirements-core.txt            # Minimal API/cognitive runtime
├── requirements-test.txt            # Software-only broad test dependencies
├── requirements-optional-tools.txt   # Media/speech/hardware tools
├── requirements-all.txt             # Complete owner-machine installation
└── README.md
```

---

## Setup & Installation

### Prerequisites
- **Python 3.11+**
- **LM Studio** running locally with Local Server enabled on port `1234`
- Load Qwen 2.5 models (3B-4B fast + 9B reasoning) in GGUF format

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` is the software-only developer/CI environment. It avoids GPU
and native audio stacks so a clean runner can install it reliably. For the
smallest core runtime, or every owner-machine capability, use respectively:

```bash
pip install -r requirements-core.txt
pip install -r requirements-all.txt
```

The full owner-machine install may need platform packages first (for example,
PortAudio development headers before PyAudio). Optional tool modules are loaded
only when invoked. A missing optional package marks that capability unavailable
without preventing the API or `CognitiveRuntime` from starting. Inspect status
without loading tool modules at `GET /tools/availability`; explicitly probe one
tool with, for example,
`GET /tools/availability?tool=web_search&probe=true`.

### Run Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Current software-only baseline (2026-08-23): **1589 backend passed, 2 skipped, 4 e2e deselected; 184 frontend passed; production frontend build passed**. The measured architecture retains 27/27 deterministic scorecard checks, 137 manifest tools, and 17 wired cognition modules.

> **Live verification:** tools that hit external APIs (prices, RSS, search,
> Telegram/WhatsApp) are unit-tested for degradation only in CI — run
> `python scripts/live_check.py` on your machine to exercise them for real
> (see [`LIVE_VERIFICATION.md`](LIVE_VERIFICATION.md)).

### Run the Capability Demo

The demo exercises the measured P1–P3 capability path, including grounding,
causal learning, resource-aware planning, projects, optional VLM status, and
LoRA management. It reports unavailable optional hardware/models honestly.
Run it from the repository root after installing the Python dependencies:

```bash
PYTHONPATH=. python scripts/demo_agi.py
```

This is a local capability demonstration, not a human-level-AGI benchmark.
For real external integrations, use `scripts/live_check.py` separately.

LoRA behavior deployment is evidence-gated. `POST /loras/evaluations` compares
distinct provider base and adapter/merged model IDs on reviewed skill and
unrelated-domain holdouts (minimum three examples each). A passing report still
does not deploy anything; the owner separately calls
`POST /loras/deploy-evaluated`, which performs a fresh provider identity probe.
The resulting default-model route is in-memory and is intentionally cleared on
restart rather than claiming the external provider remains loaded.

Functional self-awareness is exposed at `GET /self-awareness`, with claim history
at `GET /self-awareness/claims/history`, structured belief changes at
`GET /self-awareness/belief-revisions`, conservative agency records at
`GET /self-awareness/agency`, calibrated competence in the main report, an explicit sensor/actuator boundary at `GET /self-awareness/embodied-boundary`, restart discontinuity checks at `POST /self-awareness/identity-checkpoint`, and restart-safe commitments at
`GET/POST /self-awareness/commitments`, and trace-grounded explanations at
`GET /self-awareness/introspection/{trace_id}`. These endpoints report
operational evidence and explicitly do not claim hidden chain-of-thought,
consciousness, or subjective experience. Verified application/process/window targets
are inspectable through `GET /os-grounding` and `GET /os-grounding/resolve`.
Semantic UI targets are available through `/os-grounding/accessibility/*`; activation
requires a unique accessibility role/name match with observed screen bounds.

Autonomous resource limits are optional through `GET/PUT /owner-control/autonomy-envelope`
and are disabled by default. The owner can cap cycle duration, cooldown, execution,
project work, and failures when desired, preempt active work through persistent
cancellation/resume receipts, and inspect/approve/reject/reprioritize the planning queue at `GET /owner-control/autonomous-goals`, schedule one-time/daily/weekly directives at `GET/POST /owner-control/autonomy-schedule`, and inspect stage-by-stage run evidence at `GET /owner-control/autonomy-runs`. For a specific command, the owner can issue
an exact short-lived authorization with `override_owner_policy: true`; this overrides
the owner's own mode/block/level rules but never emergency pause, resource-critical
shutdown, missing capability, payload binding, or verification honesty.

Run the isolated longitudinal regression suite separately:

```bash
PYTHONPATH=. python scripts/benchmark_intelligence.py
```

It persists per-check evidence and pass→fail regressions. The pass count is not
an “AGI percentage” and the probes do not mutate the live cognitive stores.

### Run Server

A single unified entry point serves everything — the WebSocket chat, the 127 core
REST routes, the `/api/*` routers (files/code/attachments), voice, and the SPA.

**Localhost-only by default** (secure — no API key needed):

```bash
PYTHONPATH=. .venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 8000 --reload
```

To expose beyond localhost (LAN / Android over the network), authentication is
**required** — set a strong key and it is enforced on *every* route and the
WebSocket:

```bash
export ARENA_API_KEY=<a strong random key>
PYTHONPATH=. .venv/bin/uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Binding `0.0.0.0` with no `ARENA_API_KEY` is refused unless you explicitly set
`ARENA_ALLOW_INSECURE_LAN=1` (not recommended).

(`app.main:app` and `backend.main:app` are kept as backward-compatible aliases of
the same unified server.)

---

## Approval Levels

| Level | Classification | Behavior |
|:---:|---|---|
| **0** | Read/Observe | Autonomous — file reads, search, web research |
| **1** | Drafting | Autonomous in workspaces — code, reports, drafts |
| **2** | Reversible | Autonomous with audit trail — organize files, open apps |
| **3** | Sensitive | **Requires explicit owner approval** — send messages, delete files, execute trades, install packages |

Approval is configurable per-action, not per-domain. A capability is never permanently removed from consideration — execution enters the Owner Control gate instead. Control modes include observe-only, suggest-only, approve-every-action, approve-each-plan, bounded autonomy, and custom allowlists. Explicit approval creates a short-lived exact-payload grant; execution still passes through independent observation and tri-state goal verification. Running capabilities receive persistent execution IDs and cooperative stop controls; rollback is offered only through deterministic compensation receipts and fresh approval.

---

## Development Rules

### For Coding Agents

These rules govern how AI coding agents should work on this repository:

1. **Never fabricate success.** Attempted ≠ tool worked ≠ environment changed ≠ goal achieved. These are four separate facts.

2. **Preserve unconventional code.** If code looks unusual but works and has tests, do not change it without understanding why it exists. Check call sites, tests, and git history first.

3. **Report problems, don't auto-fix.** If you discover issues outside the current task scope, report them but don't change unrelated code.

4. **Explain all changes.** After implementation, report: files changed, logic added, behavior preserved, behavior changed, dependencies added, tests run, consequences, and limitations.

5. **Implementation freedom.** You may install packages, add supporting modules, refactor when necessary for the requested feature, and make reasonable implementation decisions — but explain what you did and why.

6. **Push after each tested commit** so the owner can audit incrementally.

### Evidence Invariants

- LLM output is not environmental evidence
- Unknown must remain unknown (three states: SATISFIED, FAILED, UNKNOWN)
- Beliefs remain revisable with provenance-tracked evidence
- Capabilities must actually exist (no phantom tools)
- One authoritative cognitive path (no hidden fallback routers)
- Goals need explicit verifiable success conditions
- Replan intelligently (eliminate failed strategy instance, not entire capability)
