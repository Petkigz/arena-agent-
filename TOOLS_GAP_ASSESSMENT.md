# Cognitive System ↔ Tools/Features Gap Assessment

**Scanned:** 2026-08-21 · Branch `arena/01a01f89-arena-agent`

## The core problem (your instinct is right, but the cause is subtle)

You feel the cognitive system is "more advanced than the tools" and that there are
"too few" tools. Both are true, but the actual reason is a **wiring gap, not a
quantity gap**:

> There are **45 tool files** and **69 cognition modules**, but the cognitive
> brain can only actually *use* about **10 tools**. The rest are unreachable to
> the agent — they only exist as REST endpoints a human can call.

So the agent *thinks* richly but *acts* thinly. That's exactly the "smart brain,
weak hands" feeling you're describing.

---

## Finding 1 — The brain can only invoke ~10 tools (the biggest gap)

Two layers decide what the agent can do, and both are far smaller than the 45 tools:

**a) `ToolRegistry` registers only 3 tools:**
```
launch_app, search_files, screen_capture
```
(`app/cognition/tool_registry.py` — the runtime's "capability registry" that
`CognitiveRuntime` and `check_capability_availability` consult.)

**b) `MasterAgentOrchestrator.execute_proposal` hard-dispatches ~10 action types:**
```
launch_app / open_application, web_search, search_files,
phone_command / send_sms, screen_capture, opsec_audit,
daily_briefing, investigate / diagnostic, answer, workflow_execute
```
(`app/agents/master_agent.py`, 398 lines — the actual executor.)

**Result:** ~35 of 45 tools — `vision_analyzer`, `ocr_reader`, `data_analyzer`,
`content_creator`, `music_studio`, `media_studio`, `finance_trader`,
`git_manager`, `business_growth`, `web_agent`, `camera_capture`,
`location_service`, `workflow_engine`, `cybersecurity_brain`, `security_lab`,
`skill_teaching_engine`, `youtube_learner`, `universal_media_learner`,
`knowledge_indexer`, etc. — are **never invoked by the cognitive pipeline**.
They exist only as `/tools/*` or `/filesystem/*` REST routes in `app/main.py`.

This is the single highest-leverage fix: **make every tool reachable through one
registered capability surface** so the agent can autonomously choose and run any
of them.

---

## Finding 2 — Three tools are fake stubs (2 lines each)

These return canned "success" strings and do nothing:

- `app/tools/dynamic_fibonacci_calc.py`
- `app/tools/dynamic_patched_run_in_sandbox.py`
- `app/tools/dynamic_systemloganalyzer.py`

They look like artifacts of a "dynamic capability synthesis" experiment
(`capability_factory.py`). They're **phantom tools** — which violates the project's
own README invariant: *"Capabilities must actually exist (no phantom tools)."*

---

## Finding 3 — Real tool-category gaps (things a personal secretary needs but you don't have)

These are **missing entirely** (not just unwired):

| Category | Status |
|---|---|
| **Email** (send/receive/read inbox) | ❌ — `send_email` exists only as a policy *action*, no real email tool |
| **Calendar / scheduling** | ❌ none |
| **Contacts** (desktop) | ❌ — only an Android permission, no read/write tool |
| **Reminders / timers / alarms** | ❌ none |
| **Weather** | ❌ none |
| **Translation** | ❌ none |
| **Notes / todo** (beyond the task queue) | ❌ none |
| **Spreadsheets** (read/write xlsx as data) | 🟡 only via `data_analyzer` (pandas read) |
| **Database query** (SQL against local DBs) | ❌ none |
| **PDF/document *generation*** | ❌ — `doc_reader` is a thin alias, `doc_manager` only reads/lists |
| **Multi-step web agent** | 🟡 `web_agent.py` is 99 lines (navigate→extract→summarize), no form-filling/clicking |
| **Code review / linter** | 🟡 `ast_janitor` + `coder_brain` are thin |

---

## Finding 4 — Depth is uneven

Some "tools" are genuinely thin (LLM-prompt wrappers or single methods):

- `content_creator.py` — 1 method (`generate_content_script`)
- `business_growth.py` — 2 methods
- `music_studio.py` — 72 lines
- `doc_reader.py` — 11-line alias to `doc_manager`
- `connectors.py` — 50 lines (unclear purpose)

Others are solid (`universal_filesystem`, `disposable_sandbox`, `security_lab`
with real scope enforcement, `camera_capture`/`location_service` which I just
added).

---

## Recommendations (in priority order)

### 1. Wire every tool into the cognitive capability surface (highest leverage)

Replace the 3-tool `ToolRegistry` + 10-branch `MasterAgentOrchestrator` with a
single **tool manifest**: one registry that maps `action_type → handler` for all
45 tools, with category + safety level + description, and have both
`check_capability_availability` and `execute_proposal` consult it. The agent then
"knows about" and can run every tool, with the existing ActionGate still gating
Level-3 actions.

**Measurable outcome:** `measure_capabilities()` gains a "tools_wired" check that
asserts e.g. 40/45 tools are registered (not 3).

### 2. Delete or implement the 3 phantom tools

Either remove the stubs (and anything in `capability_factory` that synthesizes
them) or implement them for real (the system-log analyzer is actually useful).
Doing nothing violates the no-phantom-tools invariant.

### 3. Add the high-value missing tools (a "secretary" baseline)

Start with the ones that make it feel like a real assistant, each as a
native/LLM-backed tool following your graceful-degradation pattern:

1. **Email** — SMTP send + IMAP read (local credentials in settings, Level-3 gated)
2. **Calendar/reminders** — a local schedule store + OS reminder hooks
3. **Notes** — markdown notes CRUD (backed by the existing memory store)
4. **Weather** — free keyless API (like the IP geolocation I added)
5. **Translation** — via the local Qwen LLM (no external API)
6. **Contacts** — vCard/local DB read/write
7. **SQL query** — read-only SQLite/CSV query tool
8. **Document generation** — markdown → PDF/HTML

### 4. Deepen the thin tools

Give `web_agent` multi-step action (click/fill/submit), `content_creator` real
content types, `music_studio`/`media_studio` real generation. Only where it
serves a need — don't pad for the sake of it.

---

## Honest framing

The cognition (69 modules) is genuinely more mature than the action surface.
That's the opposite of the usual AI project (which has tons of tools and no
brain). The fix is **integration, not more cognition**: make the 45 existing tools
reachable to the agent, remove the fakes, and add the handful of secretary
essentials that are truly absent. Then the "brain" and the "hands" finally match.
