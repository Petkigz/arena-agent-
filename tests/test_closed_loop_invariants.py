import pytest
from unittest.mock import patch, MagicMock
from app.cognition.runtime import CognitiveRuntime
from app.cognition.action_proposal import ActionProposal, GateResult
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_verifier import GoalVerificationResult, GoalVerifier
from app.cognition.goal_replanner import GoalReplanner
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.reasoning_cycle import ReasoningDecision, ReasoningAction
from app.cognition.reasoning_loop import CycleTrace


def test_invariant_a_counterfactual_winner_is_executed_proposal(tmp_path):
    """
    Test A: Verify that the candidate strategy selected as counterfactual winner
    is the exact ActionProposal passed to MasterAgentOrchestrator.execute_proposal.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    executed_proposal = None

    def mock_execute_proposal(proposal, user_text, complexity="fast"):
        nonlocal executed_proposal
        executed_proposal = proposal
        return {
            "executed_actions": [f"Executed {proposal.action_type}"],
            "assistant_reply": f"Found file report.pdf at /home/user/documents/report.pdf",
            "model_used": "fast"
        }

    with patch("app.agents.master_agent.MasterAgentOrchestrator.execute_proposal", side_effect=mock_execute_proposal):
        res = runtime.process_cognitive_cycle(user_text="Find document report.pdf", complexity="fast")

        assert res["success"] is True
        assert executed_proposal is not None
        assert executed_proposal.action_type == "search_files"
        assert executed_proposal.action_type == res["action_type"]


def test_invariant_b_plan_a_fails_triggers_differentiating_simulated_and_executed_plan_b(tmp_path):
    """
    Test B: Plan A fails verification -> Plan B differs from A -> Plan B is simulated -> Plan B is executed.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    executed_proposals = []

    def mock_execute_proposal(proposal, user_text, complexity="fast"):
        executed_proposals.append(proposal)
        if proposal.action_type == "open_application":
            return {
                "executed_actions": ["Launched app"],
                "assistant_reply": "App launched but crashed immediately with code 1.",
                "model_used": "fast"
            }
        else:
            return {
                "executed_actions": ["Executed Plan B web search"],
                "assistant_reply": "Retrieved web search results for application troubleshooting.",
                "model_used": "fast"
            }

    with patch("app.agents.master_agent.MasterAgentOrchestrator.execute_proposal", side_effect=mock_execute_proposal):
        res = runtime.process_cognitive_cycle(user_text="Open Photoshop", complexity="fast")

        # Plan A executed, failed, Plan B executed
        assert len(executed_proposals) == 2
        plan_a = executed_proposals[0]
        plan_b = executed_proposals[1]

        # Plan B MUST differ from Plan A
        assert plan_b.action_type != plan_a.action_type
        assert plan_a.action_type == "open_application"
        assert plan_b.action_type == "web_search"
        assert res["goal_verified"] is True
        assert res["goal_lifecycle_state"] == GoalLifecycleState.ACHIEVED.value


def test_invariant_c_plan_b_gate_denied_records_blocked_replan_without_error(tmp_path):
    """
    Test C: Plan B gate denied -> no UnboundLocalError -> lifecycle records blocked replan.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.ACT, confidence=0.9, reason="Action required")]
    )

    plan_b_proposal = ActionProposal(action_type="web_search", payload={"query": "test"})

    gate_pass = GateResult(allowed=True, gate_name="passed_all_gates", reason="Allowed")
    gate_block = GateResult(allowed=False, gate_name="policy_gate", reason="Plan B blocked for test")

    def gate_eval_side_effect(proposal):
        if proposal.action_type == "web_search":
            return gate_block
        return gate_pass

    failed_verify = GoalVerificationResult(
        goal_id="g1",
        verified_success=False,
        final_state=GoalLifecycleState.FAILED,
        verification_reason="Failed initial condition",
        failed_action_type="launch_app"
    )

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch("app.cognition.action_proposal.ActionGate.evaluate_proposal", side_effect=gate_eval_side_effect), \
         patch("app.agents.master_agent.MasterAgentOrchestrator.execute_proposal", return_value={"executed_actions": ["Launched app"], "assistant_reply": "App launched but failed verification", "model_used": "fast"}), \
         patch("app.cognition.goal_verifier.GoalVerifier.verify_goal_achievement", return_value=failed_verify), \
         patch("app.cognition.goal_replanner.GoalReplanner.execute_reassessment_and_replan", return_value=plan_b_proposal):

        res = runtime.process_cognitive_cycle(user_text="launch test_app and do something", complexity="fast")

        assert res["success"] is True
        assert res["goal_verified"] is False
        assert res["goal_lifecycle_state"] == GoalLifecycleState.BLOCKED.value


def test_invariant_d_action_executes_but_success_condition_false_results_in_failed():
    """
    Test D: Action executes, but success condition is false -> goal FAILED.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    assert "app_process_running = true" in goal_rep.success_conditions

    executed_actions = ["Launched Photoshop executable"]
    reply = "Photoshop process crashed on startup with code 1."

    res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, reply)

    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED


def test_invariant_e_goal_actually_satisfied_results_in_achieved():
    """
    Test E: Goal actually satisfied in environment -> goal ACHIEVED.
    """
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

    executed_actions = ["Launched Photoshop executable"]
    reply = "Photoshop process is running active on screen."

    res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, reply)

    assert res.verified_success is True
    assert res.final_state == GoalLifecycleState.ACHIEVED
    assert "app_process_running = true" in res.met_conditions


def test_invariant_f_defer_decision_results_in_deferred_not_failed(tmp_path):
    """
    Test F: DEFER decision -> DEFERRED / WAITING_FOR_USER, not FAILED.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.DEFER, confidence=0.0, reason="Capability phone.adb is offline")]
    )

    with patch.object(runtime.loop, "run", return_value=mock_trace):
        res = runtime.process_cognitive_cycle(user_text="Call John on phone")

        assert res["goal_lifecycle_state"] == GoalLifecycleState.DEFERRED.value
        assert res["goal_lifecycle_state"] != GoalLifecycleState.FAILED.value
