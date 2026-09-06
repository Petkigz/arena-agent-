"""Bounded competing-hypothesis behavior and UNKNOWN preservation."""

from app.cognition.hypotheses import HypothesisSet
from app.cognition.reasoning_cycle import ReasoningAction, ReasoningCycle


def test_hypothesis_set_keeps_a_bounded_ranked_competing_set():
    hypotheses = HypothesisSet(max_hypotheses=2)
    hypotheses.upsert("service", "status", "running", score=0.9, rationale="probe A")
    hypotheses.upsert("service", "status", "stopped", score=0.8, rationale="probe B")
    hypotheses.upsert("service", "status", "degraded", score=0.1, rationale="weak claim")

    snapshot = hypotheses.snapshot("service", "status")
    assert snapshot["bounded"] is True
    assert snapshot["max_hypotheses"] == 2
    assert snapshot["count"] == 2
    assert snapshot["competing"] is True
    assert [item["value"] for item in snapshot["items"]] == ["running", "stopped"]
    assert all(item["epistemic_status"] == "hypothesis" for item in snapshot["items"])


def test_competing_hypotheses_do_not_become_a_synthesized_answer():
    cycle = ReasoningCycle()
    cycle.observe_and_decide(
        "service",
        "status",
        "running",
        source="probe_a",
        confidence=0.9,
    )
    decision = cycle.observe_and_decide(
        "service",
        "status",
        "stopped",
        source="probe_b",
        confidence=0.9,
    )

    assert decision.belief is not None
    assert decision.belief.has_competing_hypotheses is True
    assert decision.belief.hypotheses_bounded is True
    assert set(decision.belief.alternatives) == {"running"}
    assert decision.action in {ReasoningAction.INVESTIGATE, ReasoningAction.DEFER}
    assert decision.action is not ReasoningAction.ANSWER
    assert "Competing hypotheses" in decision.reason
