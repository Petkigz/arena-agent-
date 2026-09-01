"""Owner review item 12 / P0 #2 (2026-09-01): the Execution Truth Layer.

The owner's diagnosis: failures are increasingly at the INTERFACES
between cognitive layers — Arena has the tools, but the layers don't
consistently agree about what happened. The prescription: ONE subsystem
between execution and verification that answers 'What objectively
happened?' from evidence, never from the LLM's own account:

    TOOL EXECUTION
          │
    ┌──────────────────┐
    │ Execution Truth  │   RESULT        — deterministic computations
    │     Layer        │   STATE CHANGE  — durable-store rows
    └──────────────────┘   ARTIFACT      — files on disk
          │
        VERIFY → GOAL STATE

The RESULT and STATE-CHANGE classes landed with the D2/D6/D8/D3/D9
fixes (deterministic answers; registry probe; creation_events). This
item consolidates them under the named subsystem and closes the missing
class, ARTIFACT: files created by this cycle's executions, re-stat'ed
on disk at collection time — so LLM-emitted conditions like
'file_created = true' resolve from the filesystem instead of landing in
UNKNOWN (waiting_for_evidence) forever.
"""

import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.cognition.execution_truth import ExecutionTruth
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.goal_interpreter import SemanticGoalRepresentation


def _goal_rep(text, conditions):
    return SemanticGoalRepresentation(
        user_query=text,
        primary_intent_type="action_intent",
        target_domain="filesystem",
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


# ── ARTIFACT: candidate extraction from execution payloads ──────────────

def test_artifact_candidates_extracted_from_result_payloads():
    payload = {
        "success": True,
        "file_path": "/tmp/report.pdf",
        "outputs": {
            "save_path": "/tmp/other.xlsx",
            "ignored": "not a path",
        },
        "results": [{"output_path": "/tmp/third.png"}],
    }
    cands = ExecutionTruth.extract_artifact_candidates(payload)
    assert "/tmp/report.pdf" in cands
    assert "/tmp/other.xlsx" in cands
    assert "/tmp/third.png" in cands
    assert all(c.startswith("/tmp/") or Path(c).is_absolute() for c in cands)


def test_artifact_extraction_ignores_nonexistent_and_junk():
    cands = ExecutionTruth.extract_artifact_candidates({
        "file_path": 42,                 # not a string
        "path": "not a path at all",     # no separator, not a file
        "error": "/nonexistent/x.txt",   # path-like but absent
    })
    assert cands == []


# ── ARTIFACT: disk verification + cycle window ──────────────────────────

def test_artifacts_verified_against_disk_and_cycle_window(tmp_path):
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4")
    before = datetime.now(timezone.utc) - timedelta(minutes=1)
    after = datetime.now(timezone.utc) + timedelta(minutes=1)

    # Created this cycle (mtime after cycle start) and on disk → truth.
    arts = ExecutionTruth.collect_artifacts([str(f)], cycle_started_at=before)
    assert len(arts) == 1
    assert arts[0]["path"] == str(f)
    assert arts[0]["size_bytes"] == 8
    assert arts[0]["exists"] is True

    # Created BEFORE this cycle's window → not this cycle's artifact.
    arts = ExecutionTruth.collect_artifacts([str(f)], cycle_started_at=after)
    assert arts == []

    # A path that does not exist on disk → never truth.
    arts = ExecutionTruth.collect_artifacts(
        [str(tmp_path / "ghost.txt")], cycle_started_at=before)
    assert arts == []


# ── STATE CHANGE: the durable-store class (consolidated from item 8) ────

def test_state_changes_read_from_durable_stores(tmp_path):
    from app.cognition.runtime import CognitiveRuntime
    previous = CognitiveRuntime._instance
    try:
        rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
        rt._cycle_started_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        marker = uuid.uuid4().hex[:6]
        rt.project_manager.create_project(
            name=f"organize {marker}", description=f"organize {marker}",
            milestones=[{"description": "step 1"}])
        record = ExecutionTruth.collect_state_changes(
            rt, cycle_started_at=rt._cycle_started_at)
        assert any(marker in p.get("description", "")
                   for p in record["projects"])
    finally:
        CognitiveRuntime._instance = previous


# ── runtime integration: the truth record rides on observed state ───────

def test_runtime_collects_execution_truth_with_artifacts(tmp_path):
    from app.cognition.runtime import CognitiveRuntime
    previous = CognitiveRuntime._instance
    try:
        rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
        rt._cycle_started_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        f = tmp_path / "shot.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        # An execution result reports a created file — the runtime notes
        # it as an artifact candidate (the observation/capability choke
        # points do this automatically).
        rt._note_artifact_candidates({"file_path": str(f)})
        obs = rt.capture_observed_world_state([], "done", None)
        truth = obs.get("execution_truth")
        assert truth is not None, "the truth record must ride on observed state"
        assert truth["provenance"]["source"] == "durable_store+filesystem"
        assert any(a["path"] == str(f) for a in truth["artifacts"])
        assert isinstance(truth["state_changes"], dict)
    finally:
        CognitiveRuntime._instance = previous


def test_observation_result_noted_as_artifact_candidate(tmp_path):
    """The observation choke point: a Level-0 tool result that reports a
    file path must land in the candidate list automatically."""
    from app.cognition.runtime import CognitiveRuntime
    previous = CognitiveRuntime._instance
    try:
        rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
        rt._cycle_started_at = datetime.now(timezone.utc)
        rt._cycle_artifact_candidates = []
        f = tmp_path / "capture.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        # Directly exercise the noting helper the choke points call.
        rt._note_artifact_candidates({"success": True, "file_path": str(f)})
        assert str(f) in rt._cycle_artifact_candidates
    finally:
        CognitiveRuntime._instance = previous


def test_capability_execution_result_noted_as_artifact_candidate(tmp_path):
    """The ACT choke point: a capability execution result that reports a
    produced file becomes an artifact candidate for the truth layer."""
    from unittest.mock import patch
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.action_proposal import ActionProposal
    previous = CognitiveRuntime._instance
    try:
        rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
        rt._cycle_started_at = datetime.now(timezone.utc)
        rt._cycle_artifact_candidates = []
        f = tmp_path / "report.pdf"
        f.write_bytes(b"%PDF-1.4")

        class _FakeResult:
            def to_dict(self):
                return {
                    "success": True,
                    "executed_actions": ["generate_document"],
                    "assistant_reply": "Document created.",
                    "outputs": {"file_path": str(f)},
                }

        proposal = ActionProposal(
            action_type="generate_document",
            payload={"title": "report"},
        )
        with patch("app.agents.master_agent.MasterAgentOrchestrator."
                   "execute_proposal", return_value=_FakeResult()):
            result = rt._execute_capability_controlled(
                proposal, "create a report", "simple")
        assert result["success"] is True
        assert str(f) in rt._cycle_artifact_candidates
    finally:
        CognitiveRuntime._instance = previous


# ── the verifier consumer: artifact conditions resolve from truth ───────

def test_file_created_condition_satisfied_by_artifact_truth():
    """The class the owner described: the LLM says whatever it says — the
    FILESYSTEM decides. A disk-verified artifact satisfies the creation
    condition even when the reply is off-target."""
    rep = _goal_rep("create a report file", ["file_created = true"])
    truth = {
        "results": [],
        "state_changes": {"projects": [], "tasks": []},
        "artifacts": [{"path": "/tmp/report.pdf", "size_bytes": 8,
                       "exists": True, "modified_at": "now"}],
        "provenance": {"source": "durable_store+filesystem",
                       "observation_type": "direct", "confidence": 1.0},
    }
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "Registered tool execution completed.",
        observed_state={"execution_truth": truth})
    assert res.verified_success is True
    assert res.final_state.value == "achieved"


def test_file_created_condition_unknown_without_artifacts():
    """No disk-verified artifact → honest UNKNOWN (waiting_for_evidence),
    never a fabricated achieved — and never satisfied by the reply alone."""
    rep = _goal_rep("create a report file", ["file_created = true"])
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "I created the report successfully!",
        observed_state={})
    assert res.verified_success is False
    assert res.final_state.value == "waiting_for_evidence"


def test_artifact_truth_does_not_satisfy_state_change_conditions():
    """Evidence-class discipline (same as item 8): a file artifact is not
    a project/task creation — the classes never cross-satisfy."""
    rep = _goal_rep("Set up a project to organize photos",
                    ["project_created = true"])
    truth = {
        "results": [], "state_changes": {"projects": [], "tasks": []},
        "artifacts": [{"path": "/tmp/report.pdf", "size_bytes": 8,
                       "exists": True, "modified_at": "now"}],
        "provenance": {"source": "durable_store+filesystem",
                       "observation_type": "direct", "confidence": 1.0},
    }
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "done", observed_state={"execution_truth": truth})
    assert res.verified_success is False
    assert res.final_state.value == "waiting_for_evidence"
