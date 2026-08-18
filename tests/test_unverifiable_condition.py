from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.goal_lifecycle import GoalLifecycleState


def test_unknown_success_condition_without_observation_fails_as_unverifiable():
    """
    Verify that an unknown success condition (e.g. quantum_state_entangled = true)
    without a WorldModel observation is marked as unverifiable_condition and fails verification,
    rather than assuming success from a non-empty reply.
    """
    goal_rep = SemanticGoalRepresentation(
        user_query="Perform quantum operation",
        primary_intent_type="action_intent",
        target_domain="quantum_domain",
        goal="Entangle qubits",
        desired_outcome="Quantum state entangled",
        entities=["qubits"],
        constraints=[],
        assumptions=[],
        unknowns=[],
        preconditions=[],
        success_conditions=["quantum_state_entangled = true"],
        failure_conditions=[],
        required_capabilities=["quantum.control"],
        risk_factors=[]
    )

    res = GoalVerifier.verify_goal_achievement(
        goal_rep,
        executed_actions=["Executed quantum attempt"],
        assistant_reply="Operation completed."
    )

    assert res.verified_success is False
    assert res.is_unknown is True
    assert any("unverifiable_condition" in uc for uc in res.unknown_conditions)
