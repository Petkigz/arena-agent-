from app.cognition.information_gain import InformationNeed
from app.cognition.reasoning_cycle import ReasoningAction, ReasoningCycle


def test_high_confidence_belief_can_answer():
    cycle = ReasoningCycle()
    decision = cycle.observe_and_decide("chrome", "status", "running", source="process", confidence=0.95)
    assert decision.action is ReasoningAction.ANSWER


def test_uncertainty_prefers_investigation():
    cycle = ReasoningCycle()
    need = InformationNeed("Is Chrome responsive?", "chrome", "status is uncertain", 0.9)
    decision = cycle.observe_and_decide("chrome", "status", "running", source="vision", confidence=0.5, information_needs=[need])
    assert decision.action is ReasoningAction.INVESTIGATE
    assert decision.information_need == need


def test_weak_evidence_defers_without_information_or_action():
    cycle = ReasoningCycle()
    decision = cycle.observe_and_decide("chrome", "status", "running", source="vision", confidence=0.3)
    assert decision.action is ReasoningAction.DEFER
