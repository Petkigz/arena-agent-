# Local Personal Assistant — Version 0 Core Engine

Welcome to your **Local Personal Assistant** repository! This is the complete, high-quality, fully tested **Version 0 Core Engine** of your local personal assistant system. 

It is designed to run **completely locally** on your computer, using your powerful **Intel Core i9-14900K CPU**, **RX 580 GPU (8 GB)**, and system RAM, connected to **LM Studio** for model inference (e.g., Qwen 3B/4B and Qwen 9B quantized GGUF models).

---

## 🏗️ Architecture Overview

The system is designed with a **modular architecture** that separates reasoning, task planning, safety policies, memory, and native operating tools:

```
                         ┌─────────────────────────────┐
                         │         User Interface      │
                         │    (FastAPI / Client Apps)  │
                         └──────────────┬──────────────┘
                                        │
                  ┌─────────────────────▼─────────────────────┐
                  │          Orchestrator / Agent Core        │
                  │        (FastAPI, Tasks, SQLite, DB)       │
                  └───────┬────────────┬────────────┬─────────┘
                          │            │            │
               ┌──────────▼───┐  ┌─────▼─────┐ ┌───▼─────────────┐
               │ Fast Model   │  │ Main Model│ │ Memory Service  │
               │ (Qwen 3B-4B) │  │ (Qwen 9B) │ │  (SQLite DB)    │
               └──────────────┘  └───────────┘ └─────────────────┘
                          │            │            │
        ┌─────────────────┴────────────┴────────────┴─────────────────┐
        │                      Perception Layer                         │
        │     (Speech-to-Text, Screenshots/OCR, Event Observers)      │
        └──────────────────────────────┬──────────────────────────────┘
                                       │
                                ┌──────▼──────┐
                                │ Tools Layer │
                                └─────────────┘
```

### Key Components:
1. **FastAPI Web Service (`app/main.py`)**: Exposes structured JSON endpoints for chat interaction, task queues, audit logs, memory, and safety policy checking.
2. **Local LLM Client (`app/llm.py`)**: Coordinates connection to your local LM Studio service. Supports request routing to use a fast, lightweight model (Qwen 3B/4B) for routine operations, or your main thoughtful model (Qwen 9B) for deep reasoning.
3. **Database Manager (`app/database.py`)**: Uses a lightweight, high-performance SQLite database (`data/assistant.db`) to persist tasks, memories, preferences, and action logs.
4. **Task Persistence (`app/tasks.py`)**: Implements durable background tasks that can survive assistant restarts, checkpoints, step tracing, and queue states.
5. **Safety Policy Evaluator (`app/policy.py`)**: An authorization check layer that ensures autonomous operations stay within Level 0/1/2 and block Level 3 sensitive operations (like sending emails, running system scripts, placing trades, or betting) without explicit human confirmation.
6. **Audit & Safety Logs (`app/utils/logger.py`)**: Implements a dedicated audit log (`data/logs/audit.log`) that records every action, state transition, and security status.

---

## 📁 Repository Directory Structure

```text
arena-agent-/
├── app/
│   ├── __init__.py
│   ├── config.py              # Configuration loader (Pydantic settings)
│   ├── database.py            # SQLite connection, CRUD for tasks, memory, logs
│   ├── llm.py                 # LM Studio OpenAI-compatible client & router
│   ├── main.py                # FastAPI endpoints
│   ├── policy.py              # Action policy validator (Levels 0-3)
│   ├── tasks.py               # Task manager and models
│   └── utils/
│       ├── __init__.py
│       └── logger.py          # App logging & security audit logging
├── config/                    # Shared settings
├── data/                      # Auto-created directory for SQLite & audit files
│   ├── assistant.db           # Persistent SQLite database
│   └── logs/
│       ├── app.log            # General application logs
│       └── audit.log          # Security audit logs
├── memory/
│   ├── rules.md               # User-defined permission boundaries
│   └── user_operating_manual.md # Personal operating handbook
├── tests/                     # Comprehensive Pytest suite
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_llm.py
│   ├── test_main.py
│   ├── test_policy.py
│   └── test_tasks.py
├── .gitignore
├── requirements.txt           # Main python dependencies
└── README.md                  # This file
```

---

## ⚙️ Setup & Installation

### 1. Prerequisites
- **Python 3.11+**
- **LM Studio** installed and running on your local machine.

### 2. Install Dependencies
Create a virtual environment and install the required modules:
```bash
# Create a virtual environment
python3 -m venv .venv

# Activate it (Windows)
.venv\Scripts\activate
# Activate it (Linux / macOS)
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Configure LM Studio
Make sure LM Studio is running on your PC with the **Local Server** enabled on port `1234` (or update it in `.env` if you use a different port).
- Load **Qwen2.5-Coder-7B-Instruct** or **Qwen2.5-3B-Instruct** quantized in `GGUF` format.
- Ensure GPU Offload is maxed to load layers into your **RX 580 VRAM**.

---

## 🧪 Running Local Tests

We have created a **comprehensive test suite** (15 unit/integration tests) verifying your configuration, database, LLM client, task management, safety policies, and API endpoints.

To run the test suite:
```bash
PYTHONPATH=. .venv/bin/pytest
```

Output:
```text
tests/test_config.py .                                                   [  6%]
tests/test_database.py ..                                                [ 20%]
tests/test_llm.py ..                                                     [ 33%]
tests/test_main.py .....                                                 [ 66%]
tests/test_policy.py ....                                                [ 93%]
tests/test_tasks.py .                                                    [100%]

======================== 15 passed in 0.65s =========================
```

---

## 🚀 Running the FastAPI Server

To start the local web engine:
```bash
PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

You can then access:
- **API Documentation (Swagger UI)**: `http://localhost:8000/docs`
- **Root Status Check**: `http://localhost:8000/`

---

## 🔒 Safety & Authorization Levels

Your assistant follows strict **permission boundaries** defined in `memory/rules.md`:

| Level | Classification | Example Actions | Behavior |
| :---: | :--- | :--- | :--- |
| **0** | **Read/Observe** | `read_file`, `capture_screen`, `web_search` | Fully Autonomous |
| **1** | **Drafting** | `write_draft`, `browser_draft` | Autonomous inside `data/` / drafts folders |
| **2** | **Reversible** | `open_application`, `organize_files` | Autonomous with Active Audit Log |
| **3** | **Sensitive** | `send_email`, `delete_file`, `trade_action` | **Requires explicit human confirmation** |

---

## 🛠️ Next Roadmap Phases
- **Phase 1**: Frontend dashboard in TS/React to manage active tasks, approvals, and logs visually.
- **Phase 2**: Local Voice (Whisper.cpp speech-to-text + Piper text-to-speech) and Screen/OCR vision perception.
- **Phase 3**: Integration of browser automation (using Python Playwright) and advanced specialist skill plugins for business analysis, trading simulation, and security scanning.
