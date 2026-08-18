import pytest
from app.cognition.blackboard import Blackboard
from app.cognition.cognitive_state import CognitiveState

def test_workspace_boundary_contract():
    # 1. CognitiveState handles stable structured system state
    state = CognitiveState()
    state.session.session_id = "test_session_001"
    state.attention.focus = "search_files"
    assert state.session.session_id == "test_session_001"

    # 2. Blackboard handles dynamic reasoning artifacts
    bb = Blackboard()
    bb.set(Blackboard.KEY_CANDIDATE_PLANS, ["Plan A", "Plan B"], source="planner")
    bb.set(Blackboard.KEY_ACTIVE_HYPOTHESES, ["H1: File exists", "H2: File deleted"], confidence=0.85)

    assert bb.has(Blackboard.KEY_CANDIDATE_PLANS) is True
    assert bb.get(Blackboard.KEY_ACTIVE_HYPOTHESES) == ["H1: File exists", "H2: File deleted"]
    assert len(bb.snapshot()) == 2
