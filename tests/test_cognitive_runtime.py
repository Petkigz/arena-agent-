from unittest.mock import patch, MagicMock
from app.cognition.runtime import CognitiveRuntime
from app.cognition.action_selection import InvestigationPlan
from app.cognition.information_gain import InformationNeed
from app.cognition.action_proposal import ActionProposal, GateResult
from app.cognition.goal_verifier import GoalVerificationResult


def test_runtime_composes_phase3_components(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"), max_steps=1)
    runtime.actions.registry.register(
        "service",
        lambda need: InvestigationPlan(
            tool="service_probe", arguments={}, target=need.target,
            reason=need.reason, priority=need.priority, predicate="health",
        ),
    )
    runtime.executor.register("service_probe", lambda: "healthy")
    trace = runtime.loop.run(
        "service", "status", value="unknown", source="monitor", confidence=0.2,
        information_needs=[InformationNeed("Is it healthy?", "service", "uncertain", 0.9)],
    )
    assert trace.results[0].success
    assert runtime.world.latest_observation("service", "health").value == "healthy"


def test_replan_blocked_by_action_gate_handles_gracefully(tmp_path):
    """
    Ensure that when Plan A fails verification and Plan B (replan) is blocked by ActionGate,
    no UnboundLocalError occurs and the cycle completes safely.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    # Mock reasoning cycle to choose ACT
    from app.cognition.reasoning_cycle import ReasoningDecision, ReasoningAction
    from app.cognition.reasoning_loop import CycleTrace

    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.ACT, confidence=0.9, reason="Action required")]
    )

    plan_a_proposal = ActionProposal(action_type="launch_app", payload={"app": "test_app"})
    plan_b_proposal = ActionProposal(action_type="web_search", payload={"query": "test"})

    # Plan A gate passes, Plan B gate blocks
    gate_pass = GateResult(allowed=True, gate_name="passed_all_gates", reason="Allowed")
    gate_block = GateResult(allowed=False, gate_name="policy_gate", reason="Blocked for test")

    def gate_eval_side_effect(proposal):
        if proposal.action_type == "web_search":
            return gate_block
        return gate_pass

    # Goal verification fails on Plan A
    from app.cognition.goal_lifecycle import GoalLifecycleState
    failed_verify = GoalVerificationResult(goal_id="g1", verified_success=False, final_state=GoalLifecycleState.FAILED, verification_reason="Failed initial condition")

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch("app.cognition.action_proposal.ActionGate.evaluate_proposal", side_effect=gate_eval_side_effect), \
         patch("app.agents.master_agent.MasterAgentOrchestrator.execute_proposal", return_value={"executed_actions": ["Launched app"], "assistant_reply": "App launched but failed verification", "model_used": "fast"}), \
         patch("app.cognition.goal_verifier.GoalVerifier.verify_goal_achievement", return_value=failed_verify), \
         patch("app.cognition.goal_replanner.GoalReplanner.execute_reassessment_and_replan", return_value=plan_b_proposal):

        res = runtime.process_cognitive_cycle(user_text="launch test_app and do something", complexity="fast")

        assert res["success"] is True
        assert res["goal_verified"] is False
        assert "App launched but failed verification" in res["assistant_reply"]
