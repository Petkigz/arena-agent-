import pytest
from unittest.mock import patch, MagicMock
from app.cognition.runtime import CognitiveRuntime
from app.cognition.action_proposal import ActionProposal, GateResult
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_verifier import GoalVerificationResult, GoalVerifier
from app.cognition.goal_replanner import GoalReplanner
from app.cognition.goal_interpreter import SemanticGoalInterpreter, SemanticGoalRepresentation
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.reasoning_cycle import ReasoningDecision, ReasoningAction
from app.cognition.reasoning_loop import CycleTrace


def test_invariant_a_counterfactual_winner_is_executed_proposal(tmp_path):
    """
    Test A: Verify that the candidate strategy selected as counterfactual winner
    is the exact ActionProposal passed to MasterAgentOrchestrator.execute_proposal.

    The reasoning decision is forced to ACT with an explicit proposal so the test
    deterministically exercises the ACT branch (independent of live-LLM routing).

    Owner-machine run (2026-09-02, dbe71c2, LM Studio up): the live
    interpreter's goal rep left verification at waiting_for_evidence, the
    GoalReplanner ran an `investigate` re-observation, and the single
    capture variable recorded the LAST execution — the test failed even
    though the forced proposal HAD executed first. Robust capture: a list,
    asserting on the FIRST execution. The goal interpretation is pinned
    too, so the test is hermetic (LM Studio up or down).
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    executed_proposals = []

    def mock_execute_proposal(proposal, user_text, complexity="fast", **kwargs):
        executed_proposals.append(proposal)
        from app.cognition.world_model import Observation
        import os
        runtime.world.upsert_entity(name="report.pdf", entity_type="file", attributes={"status": "identified"})
        runtime.world.observe(Observation(id=f"obs_a_{os.urandom(4).hex()}", subject="filesystem", predicate="file_path", value="/home/user/documents/report.pdf", source="fs"))
        return {
            "executed_actions": [f"Executed {proposal.action_type}"],
            "assistant_reply": "Found file report.pdf at /home/user/documents/report.pdf",
            "model_used": "fast"
        }

    mock_trace = CycleTrace(decisions=[ReasoningDecision(
        action=ReasoningAction.ACT, confidence=0.9, reason="Action required",
        proposed_action=ActionProposal(action_type="search_files", payload={"query": "report.pdf"}),
    )])

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch("app.agents.master_agent.MasterAgentOrchestrator.execute_proposal", side_effect=mock_execute_proposal), \
         patch("app.cognition.observation_router.plan_observation", return_value=None), \
         patch("app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal",
               return_value=SemanticGoalRepresentation(
                   user_query="Find document report.pdf",
                   primary_intent_type="action_intent",
                   target_domain="filesystem",
                   goal="locate report.pdf",
                   desired_outcome="report.pdf path identified",
                   entities=["report.pdf"], constraints=[], assumptions=[],
                   unknowns=[], preconditions=[],
                   success_conditions=["file_path_identified = true"],
                   failure_conditions=[], required_capabilities=[],
                   risk_factors=[])):
        res = runtime.process_cognitive_cycle(user_text="Find document report.pdf", complexity="fast")

        assert res["success"] is True
        assert executed_proposals, "the forced proposal must have executed"
        # The FIRST execution is exactly the counterfactual winner — a
        # later re-observation may append, never replace it.
        assert executed_proposals[0].action_type == "search_files"
        # And the cycle's identity is that winner, not the last action.
        assert res["action_type"] == "search_files"


def test_invariant_a2_reobservation_does_not_overwrite_cycle_identity(tmp_path):
    """Owner Priority 1 (owner-machine run 2026-09-02): when verification
    returns waiting_for_evidence and the replanner runs a re-observation
    (`investigate`), the re-observation is ALLOWED — but the cycle's
    identity stays the originally selected proposal. The re-observation
    is disclosed separately (replan_action_type + executed sequence),
    never as the cycle's action_type. Reproduces the owner's exact
    sequence: search_files executes -> UNKNOWN -> replanner ->
    investigate executes."""
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    executed_proposals = []

    def mock_execute_proposal(proposal, user_text, complexity="fast", **kwargs):
        executed_proposals.append(proposal)
        return {
            "executed_actions": [f"Executed {proposal.action_type}"],
            "assistant_reply": "Gathering evidence.",
            "model_used": "fast"
        }

    mock_trace = CycleTrace(decisions=[ReasoningDecision(
        action=ReasoningAction.ACT, confidence=0.9, reason="Action required",
        proposed_action=ActionProposal(action_type="search_files", payload={"query": "report.pdf"}),
    )])

    # NOTE: the REAL GoalReplanner runs here (not a mock) — the UNKNOWN
    # verification result drives its diagnostic re-observation probe
    # path, exactly the owner's live sequence.
    unknown_verify = GoalVerificationResult(
        goal_id="g_a2",
        verified_success=False,
        final_state=GoalLifecycleState.WAITING_FOR_EVIDENCE,
        verification_reason="evidence incomplete",
        unknown_conditions=["unverifiable_condition: file_path_identified = true"],
        is_unknown=True,
    )

    def mock_verify(*args, **kwargs):
        # Mirror the real verifier's entry transition (EXECUTING ->
        # VERIFYING); the UNKNOWN outcome rides on the result's
        # final_state, exactly as the real verifier reports it.
        tracker = kwargs.get("tracker")
        if tracker is None and len(args) >= 2:
            tracker = args[1] if hasattr(args[1], "transition") else None
        if tracker is not None and tracker.current_state != GoalLifecycleState.VERIFYING:
            tracker.transition(GoalLifecycleState.VERIFYING,
                               "evaluating (mock)")
        return unknown_verify

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch("app.agents.master_agent.MasterAgentOrchestrator.execute_proposal", side_effect=mock_execute_proposal), \
         patch("app.cognition.goal_verifier.GoalVerifier.verify_goal_achievement", side_effect=mock_verify), \
         patch("app.cognition.observation_router.plan_observation", return_value=None), \
         patch("app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal",
               return_value=SemanticGoalRepresentation(
                   user_query="Find document report.pdf",
                   primary_intent_type="action_intent",
                   target_domain="filesystem",
                   goal="locate report.pdf",
                   desired_outcome="report.pdf path identified",
                   entities=["report.pdf"], constraints=[], assumptions=[],
                   unknowns=[], preconditions=[],
                   success_conditions=["file_path_identified = true"],
                   failure_conditions=[], required_capabilities=[],
                   risk_factors=[])):
        res = runtime.process_cognitive_cycle(user_text="Find document report.pdf", complexity="fast")

        # The owner's exact sequence: winner first, re-observation second.
        assert [p.action_type for p in executed_proposals] == ["search_files", "investigate"]
        # The cycle's identity is the ORIGINALLY selected proposal.
        assert res["action_type"] == "search_files"
        # The re-observation is disclosed — explicitly, not as identity.
        assert res.get("replan_action_type") == "investigate"
        assert "Executed investigate" in [str(a) for a in res["executed_actions"]]


def test_invariant_b_plan_a_fails_triggers_differentiating_simulated_and_executed_plan_b(tmp_path):
    """
    Test B: Plan A fails verification -> Plan B differs from A -> Plan B is simulated -> Plan B is executed.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    executed_proposals = []

    def mock_execute_proposal(proposal, user_text, complexity="fast", **kwargs):
        executed_proposals.append(proposal)
        if proposal.action_type == "search_files":
            # Realistic orchestrator output: the failure text lives in the
            # executed ACTIONS, not just the reply (live-class bug: Plan A's
            # stale error keywords poisoned Plan B's re-verification).
            return {
                "executed_actions": [
                    "search_files failed: no file matching 'report.pdf' "
                    "found in workspace roots"],
                "assistant_reply": "Error: File report.pdf not found in workspace.",
                "model_used": "fast"
            }
        else:
            from app.cognition.world_model import Observation
            runtime.world.upsert_entity(name="report.pdf", entity_type="file", attributes={"status": "identified"})
            runtime.world.observe(Observation(
                id="obs_web1", subject="filesystem", predicate="file_path", value="/home/user/downloads/report.pdf", source="web_researcher"
            ))
            return {
                "executed_actions": ["Executed Plan B web search"],
                "assistant_reply": "Found and downloaded report.pdf at /home/user/downloads/report.pdf",
                "model_used": "fast"
            }

    plan_b_proposal = ActionProposal(action_type="web_search", payload={"query": "report.pdf"})
    mock_trace = CycleTrace(decisions=[ReasoningDecision(
        action=ReasoningAction.ACT, confidence=0.9, reason="Action required",
        proposed_action=ActionProposal(action_type="search_files", payload={"query": "report.pdf"}),
    )])

    def mock_replan(user_text, goal_rep, failed_result, tracker, **kwargs):
        # Mirror the real GoalReplanner's lifecycle transitions so Plan-B execution
        # follows the legal FAILED → REASSESSING → REPLAN → EXECUTING path.
        tracker.transition(GoalLifecycleState.REASSESSING, "reassessing for test")
        tracker.transition(GoalLifecycleState.REPLAN, "replan for test")
        return plan_b_proposal

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch("app.agents.master_agent.MasterAgentOrchestrator.execute_proposal", side_effect=mock_execute_proposal), \
         patch("app.cognition.goal_replanner.GoalReplanner.execute_reassessment_and_replan", side_effect=mock_replan), \
         patch("app.cognition.observation_router.plan_observation", return_value=None), \
         patch("app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal",
               return_value=SemanticGoalRepresentation(
                   user_query="Find document report.pdf",
                   primary_intent_type="action_intent",
                   target_domain="filesystem",
                   goal="locate report.pdf",
                   desired_outcome="report.pdf path identified",
                   entities=["report.pdf"], constraints=[], assumptions=[],
                   unknowns=[], preconditions=[],
                   success_conditions=["file_path_identified = true"],
                   failure_conditions=[], required_capabilities=[],
                   risk_factors=[])):
        res = runtime.process_cognitive_cycle(user_text="Find document report.pdf", complexity="fast")

        # Plan A executed, failed, Plan B executed
        assert len(executed_proposals) == 2
        plan_a = executed_proposals[0]
        plan_b = executed_proposals[1]

        # Plan B MUST differ from Plan A
        assert plan_b.action_type != plan_a.action_type
        assert plan_a.action_type == "search_files"
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
    observed_state = {
        "entities": [{"name": "photoshop.exe", "type": "process", "status": "running",
                       "source": "os_process_probe", "observation_type": "direct", "confidence": 1.0}],
        "observations": {"photoshop.status": {
            "value": "running", "source": "os_process_probe",
            "confidence": 1.0, "observation_type": "direct"
        }}
    }

    res = GoalVerifier.verify_goal_achievement(goal_rep, executed_actions, reply, observed_state=observed_state)

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


def test_invariant_d7_investigate_reply_is_grounded_in_evidence(tmp_path):
    """Owner diagnostics D7 (live 2026-09-02): the probe returned
    'search_files: []' (empty evidence) and the reply still claimed
    'Found 3 such songs' — an invented count the loop never produced.

    The investigation branch must hand the model an AUTHORITATIVE
    grounding instruction with the evidence: when results exist, claims
    must come from them; when results are EMPTY, the reply must say
    nothing was found. Pinned here with the LLM mocked so the captured
    system prompt is asserted directly (hermetic, LM Studio up or down).
    """
    from app.cognition.action_selection import ActionResult

    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    def run_case(trace_results):
        system_prompts = []

        def mock_completion(messages, complexity="fast", **kwargs):
            if messages and messages[0].get("role") == "system":
                system_prompts.append(messages[0]["content"])
            return {"choices": [{"message": {"content": "checked"}}],
                    "model": "fast"}

        mock_trace = CycleTrace(
            decisions=[ReasoningDecision(
                action=ReasoningAction.INVESTIGATE, confidence=0.9,
                reason="Evidence required")],
            results=trace_results,
        )

        with patch.object(runtime.loop, "run", return_value=mock_trace), \
             patch("app.cognition.observation_router.plan_observation", return_value=None), \
             patch("app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal",
                   return_value=SemanticGoalRepresentation(
                       user_query="do i have songs called kaba",
                       primary_intent_type="action_intent",
                       target_domain="filesystem",
                       goal="locate songs named kaba",
                       desired_outcome="song files identified or absence stated",
                       entities=["kaba"], constraints=[], assumptions=[],
                       unknowns=[], preconditions=[],
                       success_conditions=["song_files_identified = true"],
                       failure_conditions=[], required_capabilities=[],
                       risk_factors=[])), \
             patch("app.llm.llm_client.generate_chat_completion",
                   side_effect=mock_completion):
            runtime.process_cognitive_cycle(
                user_text="do i have songs called kaba", complexity="fast")
        # The evidence answer is one of several LLM calls in the cycle
        # (learning/reflection fire afterwards) — assert the grounding is
        # present in the set, not in the last call.
        assert system_prompts, "the evidence answer call must have happened"
        return system_prompts

    # Case 1 — results exist (even empty-looking ones): claims must be
    # confined to them.
    with_results = run_case([ActionResult(success=True, tool="search_files", output=[])])
    grounded = [p for p in with_results if "[GROUNDING" in p]
    assert grounded, "the evidence answer must carry the grounding instruction"
    assert "must come from those results" in grounded[0]

    # Case 2 — NO results gathered: the reply must state emptiness, never
    # invent counts (the live 'Found 3' regression).
    empty = run_case([])
    grounded = [p for p in empty if "[GROUNDING" in p]
    assert grounded, "the evidence answer must carry the grounding instruction"
    assert "NO results" in grounded[0]
    assert "do NOT invent" in grounded[0]
