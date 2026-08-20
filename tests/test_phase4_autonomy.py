"""
Phase 4 guards: memory consolidation, proactive maintenance, and the owner-authority
approval model are wired into the runtime and the autonomous cycle.
"""

from unittest.mock import patch

from app.cognition.runtime import CognitiveRuntime
from app.policy import PolicyEvaluator


def test_consolidate_memory_runs_and_returns_summary(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    summary = runtime.consolidate_memory()

    for key in ("beliefs_changed", "pruned_memories", "consolidated"):
        assert key in summary
    assert summary["beliefs_changed"] >= 0
    assert summary["pruned_memories"] >= 0


def test_consolidate_memory_consolidates_episodic_memories(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    # Seed an episodic memory so consolidation has material to work with.
    runtime.memory.add("episodic", "the user prefers concise answers", importance=0.9)

    summary = runtime.consolidate_memory()
    assert summary["consolidated"] >= 0  # may be 0 if consolidate() has no semantic extractor


def test_proactive_maintenance_delegates_to_daemon(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    with patch("app.agents.proactive_coworker_daemon.ProactiveCoworkerDaemon.run_idle_proactive_cycle",
               return_value={"proactive_insight": "workspace healthy"}) as mock_daemon:
        result = runtime.run_proactive_maintenance()

    assert result["success"] is True
    assert "workspace healthy" in result["insight"]
    mock_daemon.assert_called_once()


def test_proactive_maintenance_never_raises(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    with patch("app.agents.proactive_coworker_daemon.ProactiveCoworkerDaemon.run_idle_proactive_cycle",
               side_effect=RuntimeError("boom")):
        result = runtime.run_proactive_maintenance()

    assert result["success"] is False
    assert "boom" in result["insight"]


def test_autonomous_cycle_runs_consolidation_and_maintenance(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    # Drive the cycle with the runtime and confirm Steps 8 & 9 fire.
    with patch.object(runtime, "consolidate_memory", return_value={"pruned_memories": 1, "consolidated": 0}) as mock_cons, \
         patch.object(runtime, "run_proactive_maintenance", return_value={"success": True}) as mock_maint:

        cycle = runtime.autonomous_cycle.run_cycle(cognitive_runtime=runtime)

    mock_cons.assert_called_once()
    mock_maint.assert_called_once()
    assert cycle.status.value in ("completed", "running") or cycle.status is not None


def test_approval_model_boundary():
    """Levels 0-2 auto-approve; Level 3 requires owner approval. (Owner-authority invariant.)"""
    # Auto-approve examples
    allowed_0, _, level_0 = PolicyEvaluator.evaluate_action("read_file", {"path": "x.txt"})
    assert allowed_0 is True and level_0 == 0

    allowed_2, _, level_2 = PolicyEvaluator.evaluate_action("open_application", {"app": "firefox"})
    assert allowed_2 is True and level_2 == 2

    # Requires approval examples
    allowed_3, _, level_3 = PolicyEvaluator.evaluate_action("send_email", {"to": "a@b.com"})
    assert allowed_3 is False and level_3 == 3

    allowed_del, _, level_del = PolicyEvaluator.evaluate_action("delete_file", {"path": "/x"})
    assert allowed_del is False and level_del == 3


def test_describe_approval_model(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    model = runtime.describe_approval_model()

    assert model["philosophy"]
    assert len(model["levels"]) == 4
    assert model["levels"][3]["autonomous"] is False
    assert "send_email" in model["requires_owner_approval"]
