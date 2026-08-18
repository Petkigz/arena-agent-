from unittest.mock import MagicMock
from app.cognition.goal_replanner import GoalReplanner
from app.cognition.goal_verifier import GoalVerificationResult
from app.cognition.goal_lifecycle import GoalLifecycleState, GoalTracker
from app.cognition.goal_interpreter import SemanticGoalRepresentation


def test_is_failed_strategy_instance_differentiates_queries_and_engines():
    """
    Verify GoalReplanner.is_failed_strategy_instance correctly distinguishes:
    1. Exact failed strategy instance (same action_type AND same payload query) -> True
    2. Different query on same action_type (search_files query A vs query B) -> False
    3. Different search engine on same action_type (web_search Google vs YouTube) -> False
    """
    failed_action_type = "search_files"
    failed_payload = {"query": "contract_v1.pdf", "action_type": "search_files"}

    # Exact failed strategy instance -> True
    exact_candidate = {
        "name": "Local Filesystem Search",
        "action_type": "search_files",
        "payload": {"query": "contract_v1.pdf", "action_type": "search_files"}
    }
    assert GoalReplanner.is_failed_strategy_instance(exact_candidate, failed_action_type, failed_payload) is True

    # Same action_type but DIFFERENT query (query B) -> False (should NOT be eliminated)
    different_query_candidate = {
        "name": "Broader Filesystem Search",
        "action_type": "search_files",
        "payload": {"query": "contract", "action_type": "search_files"}
    }
    assert GoalReplanner.is_failed_strategy_instance(different_query_candidate, failed_action_type, failed_payload) is False

    # Same action_type but DIFFERENT engine -> False
    google_failed_payload = {"query": "Qwen2.5", "engine": "google", "action_type": "web_search"}
    youtube_candidate = {
        "name": "YouTube Search",
        "action_type": "web_search",
        "payload": {"query": "Qwen2.5", "engine": "youtube", "action_type": "web_search"}
    }
    assert GoalReplanner.is_failed_strategy_instance(youtube_candidate, "web_search", google_failed_payload) is False


def test_execute_reassessment_and_replan_keeps_alternative_strategy_instances():
    """
    Verify GoalReplanner.execute_reassessment_and_replan keeps candidate strategies
    sharing action_type if their queries or engines differ.
    """
    tracker = GoalTracker(user_query="find contract")
    tracker.transition(GoalLifecycleState.UNDERSTOOD, "Understood")
    tracker.transition(GoalLifecycleState.PLANNED, "Planned")
    tracker.transition(GoalLifecycleState.EXECUTING, "Executing")
    tracker.transition(GoalLifecycleState.VERIFYING, "Verifying")
    tracker.transition(GoalLifecycleState.FAILED, "Failed")

    goal_rep = SemanticGoalRepresentation(
        user_query="find contract",
        primary_intent_type="action_intent",
        target_domain="filesystem",
        goal="Find contract",
        desired_outcome="File found",
        entities=["contract"],
        constraints=[],
        assumptions=[],
        unknowns=[],
        preconditions=[],
        success_conditions=["file_path_identified = true"],
        failure_conditions=[],
        required_capabilities=["filesystem.search"],
        risk_factors=[]
    )

    failed_result = GoalVerificationResult(
        goal_id=tracker.goal_id,
        verified_success=False,
        final_state=GoalLifecycleState.FAILED,
        verification_reason="File contract_v1.pdf not found",
        failed_action_type="search_files",
        failed_payload={"query": "contract_v1.pdf", "action_type": "search_files"}
    )

    proposal = GoalReplanner.execute_reassessment_and_replan(
        user_text="find contract",
        goal_rep=goal_rep,
        failed_result=failed_result,
        tracker=tracker,
        failed_payload={"query": "contract_v1.pdf", "action_type": "search_files"}
    )

    assert proposal is not None
    assert tracker.current_state in [GoalLifecycleState.REPLAN, GoalLifecycleState.PLANNED, GoalLifecycleState.REASSESSING]
