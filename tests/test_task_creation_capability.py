"""P1 (live 2026-09-01, D3, owner review item 3): task creation must select
the TASK CREATION capability, not a finance lookalike.

Live incident: 'Create a task: review the quarterly budget report
(diag-xxxxxx), with priority high.' executed budget_summary (a finance
summarizer) and the verifier accepted it — no task row exists. Reproduced
offline, the chain is fully deterministic:

  * NO task-creation capability existed in the manifest — there was
    nothing correct to select;
  * the goal interpreter classified the request as target_domain=finance
    (the word 'budget' in the task's DESCRIPTION dragged the domain) and
    emitted ['budget_summary', 'list_transactions', 'crypto_price'] as
    required capabilities — the wrong capability was REQUIRED, not just
    selected;
  * the tool matcher had no task-creation entry.

Contract under test:
  * the manifest registers create_task (productivity, Level 1 — same
    class as create_document: a reversible local write) wrapping the
    real TaskManager, so a DB row is the ground truth;
  * the matcher deterministically routes create/add/make/new-task
    phrasings to it, carrying title and priority;
  * the interpreter classifies task-creation requests as productivity
    with required_capabilities=['create_task'] — never finance;
  * plain budget/expense talk still classifies as finance.
"""

import re

import pytest

from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.tool_matcher import match_control_tool


D3_TEXT = ("Create a task: review the quarterly budget report "
           "(diag-test1), with priority high.")


def _cleanup_marker(marker):
    from app.tasks import TaskManager
    for t in TaskManager.get_all_tasks():
        if marker in (t.title or "") or marker in (t.goal or ""):
            TaskManager.delete_task(t.id)


# ── the capability exists and writes the ground truth ──────────────────

def test_manifest_registers_create_task():
    from app.cognition.tool_registry import capability_entry
    entry = capability_entry("create_task")
    assert entry is not None, "create_task must be a registered capability"
    assert str(entry.get("category")) == "productivity"
    assert int(entry.get("safety_level", 99)) == 1  # reversible local write


def test_create_task_handler_creates_db_row():
    from app.cognition.tool_registry import capability_entry
    marker = f"diag-{__name__}-row"
    try:
        entry = capability_entry("create_task")
        res = entry["handler"]({
            "title": f"review the quarterly budget report ({marker})",
            "priority": "high",
        })
        assert res["success"] is True
        assert res["task_id"]
        from app.tasks import TaskManager
        rows = [t for t in TaskManager.get_all_tasks() if marker in t.title]
        assert rows, "the DB row is the ground truth"
        assert rows[0].priority == "high"
    finally:
        _cleanup_marker(marker)


def test_create_task_handler_requires_title():
    from app.cognition.tool_registry import capability_entry
    res = capability_entry("create_task")["handler"]({"priority": "high"})
    assert res["success"] is False
    assert "title" in str(res.get("error", "")).lower()


# ── the matcher routes task creation deterministically ─────────────────

def test_matcher_routes_the_live_d3_request():
    m = match_control_tool(D3_TEXT)
    assert m is not None
    assert m.action_type == "create_task"
    assert "review the quarterly budget report" in m.payload["title"]
    assert "(diag-test1)" in m.payload["title"]  # the marker must survive
    assert m.payload["priority"] == "high"


def test_matcher_task_variants():
    m = match_control_tool("add a task to buy milk")
    assert m.action_type == "create_task"
    assert m.payload["title"] == "buy milk"
    assert m.payload["priority"] == "medium"  # default
    m = match_control_tool("new task: call the dentist")
    assert m.action_type == "create_task"
    assert m.payload["title"] == "call the dentist"


def test_matcher_ignores_budget_talk():
    m = match_control_tool("Summarize my budget and expenses for me")
    assert (m is None) or (m.action_type != "create_task")


def test_matcher_priority_normalized():
    m = match_control_tool("create a task: fix the door, priority urgent")
    assert m.payload["priority"] == "urgent"
    m = match_control_tool("create a task: fix the roof, priority ridiculous")
    assert m.payload["priority"] == "medium"  # unknown priority -> default


# ── the interpreter no longer classifies task creation as finance ──────

def test_interpreter_task_creation_not_finance():
    rep = SemanticGoalInterpreter.interpret_goal(D3_TEXT)
    assert rep.target_domain == "productivity"
    assert rep.required_capabilities == ["create_task"]
    assert "task_created = true" in rep.success_conditions


def test_interpreter_task_creation_variant():
    rep = SemanticGoalInterpreter.interpret_goal("add a task to buy milk")
    assert rep.target_domain == "productivity"
    assert rep.required_capabilities == ["create_task"]


def test_interpreter_finance_unaffected():
    rep = SemanticGoalInterpreter.interpret_goal(
        "Summarize my budget and expenses for the last month")
    assert rep.target_domain == "finance"
    assert "create_task" not in rep.required_capabilities
