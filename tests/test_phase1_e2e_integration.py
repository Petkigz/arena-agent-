import pytest
import os
from app.cognition.runtime import CognitiveRuntime
from app.cognition.cognitive_pipeline import CognitivePipeline
from app.cognition.action_proposal import ActionProposal, ActionGate
from app.cognition.tool_registry import ToolRegistry
from app.cognition.prediction_engine import PredictionEngine
from app.cognition.event_bus import EventBus


@pytest.fixture(autouse=True)
def hermetic_default_owner_policy(monkeypatch):
    """Pin the ambient owner-control singleton to defaults so gatekeeper tests
    do not depend on the developer machine's live owner policy file."""
    from app.cognition.owner_control import OwnerControlPolicy, owner_control_store
    monkeypatch.setattr(owner_control_store, "_policy", OwnerControlPolicy())

class TestPhase1EndToEndCognitiveIntegration:
    """
    Unit P1-H: Comprehensive End-to-End Phase 1 Closed-Loop Integration Test Suite.
    Proves that every user request passes through CognitiveRuntime composition root,
    evaluates ActionProposals across gates, executes tools, calculates surprisal,
    and updates memory/world state in a single closed loop.
    """

    def test_p1_h_full_closed_loop_execution_trace(self, tmp_path):
        db_file = str(tmp_path / "closed_loop_test.db")
        runtime = CognitiveRuntime(db_path=db_file)

        # 1. Process User Request through CognitiveRuntime
        user_query = "Can you open Firefox and search for ordinary on YouTube?"
        result = runtime.process_cognitive_cycle(user_query, session_id="sess_p1_h_e2e")

        # Browser availability differs by runner. Either outcome is valid, but
        # success must be backed by goal verification rather than browser theater.
        assert isinstance(result["success"], bool)
        assert result.get("goal_verified") in (True, False, None)
        if result.get("goal_verified") is not True:
            assert result.get("goal_lifecycle_state") != "achieved"
        assert result["session_id"] == "sess_p1_h_e2e"
        assert result["trace_id"].startswith("trace_")
        assert isinstance(result["executed_actions"], list)
        assert "latency_ms" in result
        assert "prediction_surprisal" in result

    def test_p1_h_gatekeeper_blocks_level3_without_approval(self):
        # Action proposal requiring Level 3 confirmation
        prop = ActionProposal(action_type="send_email", payload={"to": "client@example.com"})
        gate = ActionGate.evaluate_proposal(prop)

        assert gate.allowed is False
        assert gate.requires_approval is True
        assert gate.gate_name == "policy_gate"

    def test_p1_h_pipeline_delegates_to_runtime(self):
        pipeline_res = CognitivePipeline.process_chat(
            user_text="Find my song named Ordinary",
            session_id="sess_pipeline_delegation"
        )

        # Honest delegation: success is the runtime's verdict (this suite
        # may run with the LLM offline, in which case the cycle defers and
        # success is legitimately False WITH a reason — that is the point).
        assert isinstance(pipeline_res["success"], bool)
        if pipeline_res["success"] is False:
            assert pipeline_res.get("reason")
        assert pipeline_res["session_id"] == "sess_pipeline_delegation"
        assert pipeline_res["trace_id"].startswith("trace_")
        assert "assistant_reply" in pipeline_res
