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
│   ├── cognition/        # Cognitive pipeline (reasoning, goals, verification)
│   │   ├── runtime.py           # CognitiveRuntime (main orchestration loop)
│   │   ├── goal_interpreter.py  # Semantic goal parsing
│   │   ├── goal_verifier.py     # Tri-state condition verification
│   │   ├── goal_replanner.py    # Plan B generation on failure
│   │   ├── perception.py        # Environmental observation strategies
│   │   ├── world_model.py       # Entity/observation store
│   │   ├── reasoning_loop.py    # ACT/INVESTIGATE/DEFER/ANSWER routing
│   │   ├── counterfactual_simulator.py
│   │   └── action_proposal.py   # ActionGate safety evaluation
│   ├── memory/           # Memory systems (episodic, semantic, procedural)
│   ├── perception/       # Low-level perception (screen, OCR, audio)
│   ├── runtime/          # Runtime state management
│   ├── scheduler/        # Task scheduling
│   ├── static/           # Dashboard UI (HTML/JS PWA)
│   ├── tools/            # 115+ capability tools (118 in the manifest)
│   ├── utils/            # Logging, helpers
│   ├── main.py           # FastAPI application (134 routes)
│   ├── llm.py            # LM Studio client & model router
│   ├── database.py       # SQLite persistence
│   └── policy.py         # Action policy (Levels 0-3)
├── docs/                 # Architecture documentation
├── memory/               # User rules & operating manual
│   ├── rules.md          # Permission boundaries
│   └── user_operating_manual.md
├── tests/                # pytest suite (1414 tests) + frontend vitest (184 tests)
├── requirements.txt
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

### Run Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

Current baseline: **1414 backend + 184 frontend tests passing**

> **Live verification:** tools that hit external APIs (prices, RSS, search,
> Telegram/WhatsApp) are unit-tested for degradation only in CI — run
> `python scripts/live_check.py` on your machine to exercise them for real
> (see [`LIVE_VERIFICATION.md`](LIVE_VERIFICATION.md)).

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

Approval is configurable per-action, not per-domain. A capability is never permanently removed — it enters an approval gate instead.

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
