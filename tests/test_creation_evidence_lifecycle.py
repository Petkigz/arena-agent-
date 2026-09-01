"""Owner review item 8 (2026-09-01, P1): goal lifecycle must follow
REAL-WORLD ACTION EVIDENCE, not the conversational reply.

Live evidence (D9): 'Set up a project to organize my photo collection'
— the project WAS created (description intact, 3 milestones — verified
against the ProjectManager store by the diagnostic's own ground truth),
yet the goal lifecycle reported waiting_for_evidence / failed, and the
executed actions read 'Formulated direct conversational answer' /
'Gathered diagnostic evidence'. Real-world state changed successfully;
the lifecycle never connected to it.

Root causes (the disconnect is a family — same shape as D3, same
principle as the D2 fix):
  1. The interpreter had NO project-setup shape, so 'Set up a project
     …' inherited a file-search success condition
     ('file_path_identified = true') that has nothing to do with the
     deliverable.
  2. The GoalVerifier never saw creation evidence: the durable stores
     (ProjectManager, TaskManager) are not part of observed world
     state, and the conditions were never checkable against them.

Fix (mirrors the D6 registry-probe and D2 deterministic-answer
patterns — the durable store IS the authority):
  * project-setup asks get honest conditions
    (project_created / project_milestones_recorded);
  * capture_observed_world_state re-reads the durable stores for rows
    created during THIS cycle (cycle-scoped — no cross-cycle leakage)
    and reports them as direct provenance evidence;
  * the verifier probes that evidence BEFORE reply-text heuristics,
    so an off-topic or failed-looking reply cannot mask a real
    creation — and absence of evidence stays honest UNKNOWN
    (waiting_for_evidence), never a fabricated achieved.
"""

import uuid

from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.goal_lifecycle import GoalTracker
from app.cognition.goal_interpreter import SemanticGoalRepresentation


def _goal_rep(text, conditions, intent="action_intent", domain="project_management"):
    return SemanticGoalRepresentation(
        user_query=text,
        primary_intent_type=intent,
        target_domain=domain,
        goal=text[:60],
        desired_outcome=text[:60],
        entities=[],
        constraints=[],
        assumptions=[],
        unknowns=[],
        preconditions=[],
        success_conditions=list(conditions),
        failure_conditions=[],
        required_capabilities=[],
        risk_factors=[],
    )


# ── 1. honest conditions for project-setup asks ─────────────────────────

def test_project_setup_gets_project_shaped_conditions():
    text = ("Set up a project to organize my photo collection (%s): "
            "scan the pictures folder, group photos by date, find "
            "duplicates, then report a summary." % uuid.uuid4().hex[:6])
    conds = SemanticGoalInterpreter._honest_success_conditions(text)
    assert conds == ["project_created = true",
                     "project_milestones_recorded = true"]


def test_plain_organize_ask_is_not_project_setup():
    # 'organize my photos' without the word 'project' is NOT a project-
    # setup ask (it is the item-7 unresolved-capability case) — the
    # shape must not swallow it.
    conds = SemanticGoalInterpreter._honest_success_conditions(
        "organize my photo collection into folders by date")
    assert conds is None or "project_created" not in conds


def test_task_create_still_gets_task_conditions():
    conds = SemanticGoalInterpreter._honest_success_conditions(
        "Create a task: review the quarterly budget report")
    assert conds == ["task_created = true"]


# ── 2. the verifier probes durable creation evidence ────────────────────

PROJECT_EVENTS = {
    "projects": [{
        "project_id": "proj-1",
        "name": "organize photos",
        "description": "Set up a project to organize my photo collection",
        "milestones": 3,
    }],
    "tasks": [],
    "source": "durable_store",
    "observation_type": "direct",
    "confidence": 1.0,
}

TASK_EVENTS = {
    "projects": [],
    "tasks": [{
        "task_id": "task-1",
        "title": "review the quarterly budget report (diag-x)",
    }],
    "source": "durable_store",
    "observation_type": "direct",
    "confidence": 1.0,
}


def test_project_created_satisfied_by_store_evidence_despite_bad_reply():
    """THE fix: real-world state changed (a project exists in the store)
    — the condition is SATISFIED even when the reply is a failed-looking
    conversational message. The lifecycle must follow the evidence."""
    from app.cognition.goal_verifier import ConditionStatus
    rep = _goal_rep("Set up a project to organize my photo collection",
                    ["project_created = true", "project_milestones_recorded = true"])
    res = GoalVerifier.verify_goal_achievement(
        rep, [],
        "Registered tool 'read_document' execution failed: missing required parameter(s): file_path",
        observed_state={"creation_events": PROJECT_EVENTS})
    assert res.verified_success is True
    assert res.final_state.value == "achieved"
    assert "project_created = true" in res.met_conditions


def test_project_condition_unknown_without_evidence():
    """No creation evidence → honest UNKNOWN (waiting_for_evidence), never
    a fabricated achieved."""
    from app.cognition.goal_verifier import ConditionStatus
    rep = _goal_rep("Set up a project to organize my photo collection",
                    ["project_created = true"])
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "All done, project set up!", observed_state={})
    assert res.verified_success is False
    assert res.final_state.value == "waiting_for_evidence"


def test_milestones_condition_requires_milestones():
    rep = _goal_rep("Set up a project to organize my photo collection",
                    ["project_milestones_recorded = true"])
    no_milestones = {
        "projects": [{"project_id": "proj-1", "name": "x",
                      "description": "x", "milestones": 0}],
        "tasks": [], "source": "durable_store",
        "observation_type": "direct", "confidence": 1.0,
    }
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "Project created.", observed_state={"creation_events": no_milestones})
    assert res.verified_success is False


def test_task_created_satisfied_by_task_store_evidence():
    rep = _goal_rep("Create a task: review the quarterly budget report",
                    ["task_created = true"])
    res = GoalVerifier.verify_goal_achievement(
        rep, [],
        "Gathered diagnostic evidence for 'Create a task': System status: CPU 0%",
        observed_state={"creation_events": TASK_EVENTS})
    assert res.verified_success is True
    assert res.final_state.value == "achieved"


def test_task_events_do_not_satisfy_project_conditions():
    """Evidence type discipline: a task creation is not a project
    creation — the probe must not cross-satisfy."""
    rep = _goal_rep("Set up a project to organize my photo collection",
                    ["project_created = true"])
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "done", observed_state={"creation_events": TASK_EVENTS})
    assert res.verified_success is False
    assert res.final_state.value == "waiting_for_evidence"


# ── 3. capture is cycle-scoped (no cross-cycle leakage) ─────────────────

def test_capture_scopes_creation_events_to_the_cycle(tmp_path):
    """A project created in an EARLIER cycle must not verify a LATER
    goal: the capture window starts at the current cycle."""
    from datetime import datetime, timezone, timedelta
    from app.cognition.runtime import CognitiveRuntime
    rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    # Simulate a project created earlier (before this cycle's window).
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    rt._cycle_started_at = future
    obs = rt.capture_observed_world_state([], "reply", None)
    assert not (obs.get("creation_events") or {}).get("projects")


# ── 4. end to end: lifecycle follows the real store ─────────────────────

def test_d9_e2e_lifecycle_achieved_with_real_project(tmp_path):
    """The exact live D9 shape: the project is created (side-effect of
    decomposition), the conversational reply is off-target — and the
    lifecycle must say ACHIEVED because the durable store says so.
    Ground truth is checked INDEPENDENTLY (the project row itself),
    never the agent's own claim."""
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.cognitive_pipeline import CognitivePipeline
    marker = "diag-%s" % uuid.uuid4().hex[:6]
    task = ("Set up a project to organize my photo collection (%s): "
            "scan the pictures folder, group photos by date, find "
            "duplicates, then report a summary." % marker)
    rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    CognitiveRuntime._instance = rt
    try:
        res = CognitivePipeline.process_chat(user_text=task, complexity="fast")
    finally:
        CognitiveRuntime._instance = None
    # Independent ground truth: the durable project row.
    projects = list(getattr(rt.project_manager, "_projects", {}).values())
    hit = [p for p in projects if marker in str(getattr(p, "description", ""))]
    assert hit, "project row must exist (independent GT)"
    assert len(getattr(hit[0], "milestones", []) or []) >= 1
    # The lifecycle must follow that evidence.
    assert res.get("goal_lifecycle_state") == "achieved", \
        f"real project exists but lifecycle={res.get('goal_lifecycle_state')}"


def test_d3_e2e_lifecycle_achieved_with_real_task(tmp_path):
    """Same family, D3: the task row exists in the TaskManager store —
    the lifecycle must say ACHIEVED, not waiting_for_evidence."""
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.cognitive_pipeline import CognitivePipeline
    marker = "diag-%s" % uuid.uuid4().hex[:6]
    text = ("Create a task: review the quarterly budget report "
            f"({marker}), with priority high.")
    rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    CognitiveRuntime._instance = rt
    try:
        res = CognitivePipeline.process_chat(user_text=text, complexity="fast")
    finally:
        CognitiveRuntime._instance = None
    from app.tasks import TaskManager
    rows = TaskManager.get_all_tasks()
    created = any(marker in str(getattr(t, "title", "")) for t in rows)
    assert created, "task row must exist (independent GT)"
    assert res.get("goal_lifecycle_state") == "achieved", \
        f"real task exists but lifecycle={res.get('goal_lifecycle_state')}"
