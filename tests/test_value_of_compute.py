"""Value-of-compute policy contracts and UNKNOWN handling."""

from types import SimpleNamespace

from app.cognition.resource_allocator import (
    ResourceAllocator,
    TaskComplexity,
    ValueOfComputePolicy,
)


def test_high_risk_novel_irreversible_goal_favors_deliberation():
    assessment = ValueOfComputePolicy.assess(
        goal_rep=SimpleNamespace(
            risk_factors=["external side effect", "sensitive target"],
            unknowns=["which target is intended", "what is the rollback path"],
        ),
        proposal=SimpleNamespace(
            action_type="unknown_sensitive_capability",
            safety_level=0,
            reversibility=False,
        ),
        history_available=False,
    )

    assert assessment.recommended_route == "deliberate"
    assert assessment.signals["risk"] == 1.0
    assert assessment.signals["irreversibility"] == 1.0
    assert assessment.signals["novelty"] == 1.0
    assert assessment.signal_status["owner_stakes"] == "unknown"
    assert assessment.signal_status["predicted_user_usefulness"] == "unknown"
    assert assessment.to_dict()["advisory_only"] is True
    assert assessment.to_dict()["calibration_status"] == "not_calibrated"


def test_low_risk_known_reversible_goal_can_use_fast_route():
    assessment = ValueOfComputePolicy.assess(
        goal_rep=SimpleNamespace(risk_factors=[], unknowns=[]),
        proposal=SimpleNamespace(
            action_type="list_capabilities",
            reversibility=True,
        ),
        history_available=True,
        expected_information_gain=0.0,
        owner_stakes=0.0,
        predicted_user_usefulness=0.0,
    )

    assert assessment.recommended_route == "fast"
    assert assessment.score <= 0.25
    assert assessment.signal_status["novelty"] == "verified_action_history_present"


def test_unknown_compute_value_does_not_claim_fast_or_deliberate():
    assessment = ValueOfComputePolicy.assess()

    assert assessment.recommended_route == "standard"
    assert assessment.score == 0.5
    assert all(value == "unknown" for value in assessment.signal_status.values())


def test_allocator_exposes_value_of_compute_assessment():
    allocator = ResourceAllocator()
    assessment = allocator.assess_value_of_compute(
        goal_rep=SimpleNamespace(risk_factors=["data modification"], unknowns=["target"]),
        history_available=False,
    )

    assert assessment.decision_stage == "value_of_compute_advisory"
    assert assessment.recommended_route in {"standard", "deliberate"}
    assert TaskComplexity.COMPLEX.value == "complex"
