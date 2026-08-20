from app.cognition.information_gain import InformationNeed
from app.cognition.reasoning_cycle import ReasoningAction, ReasoningCycle


def test_high_confidence_belief_can_answer():
    cycle = ReasoningCycle()
    # Use a direct probe source (provenance weight 1.0) so weighted confidence exceeds threshold
    decision = cycle.observe_and_decide("chrome", "status", "running", source="os_process_probe", confidence=0.95)
    assert decision.action is ReasoningAction.ANSWER


def test_uncertainty_prefers_investigation():
    """When belief is uncertain (no admissible evidence) and information needs exist, investigate."""
    cycle = ReasoningCycle()
    need = InformationNeed("Is Chrome responsive?", "chrome", "status is uncertain", 0.9)
    # Use self_reported source → inadmissible → no belief → uncertainty → investigate
    decision = cycle.observe_and_decide("chrome", "status", "running",
                                         source="self_reported", confidence=0.5,
                                         information_needs=[need],
                                         observation_type="self_reported")
    assert decision.action is ReasoningAction.INVESTIGATE
    assert decision.information_need == need


def test_weak_evidence_defers_without_information_or_action():
    """When belief has no admissible evidence and no information needs or actions, defer."""
    cycle = ReasoningCycle()
    # Use self_reported source → inadmissible → no belief → defer
    decision = cycle.observe_and_decide("chrome", "status", "running",
                                         source="self_reported", confidence=0.3,
                                         observation_type="self_reported")
    assert decision.action is ReasoningAction.DEFER


def test_conflicting_sources_produce_uncertainty():
    """Two independent admissible sources disagreeing produces ~0.5 confidence."""
    cycle = ReasoningCycle()
    cycle.observe_and_decide("chrome", "status", "running", source="probe_a", confidence=0.9)
    decision = cycle.observe_and_decide("chrome", "status", "stopped", source="probe_b", confidence=0.9)
    # Two sources disagree → confidence ~0.5, below answer_threshold (0.85)
    assert decision.belief.belief_confidence < 0.6
    assert decision.action is not ReasoningAction.ANSWER
