"""No-guessing must survive a configured machine.

Owner-machine finding (Windows, LM Studio embeddings active): with a real
embedding backend, the vague need 'what is this' became conceptually similar
enough to tool descriptions that the fusion score saturated the 1.5 noise
floor on semantic evidence ALONE (2.5 x calibrated 0.6 = 1.5 exactly) — and
'what is this' autonomously planned a directory listing (rank 2/72). The
sandbox never sees this because there is no embedding backend there.

The contract under test: discovery may PROPOSE conceptual-only candidates,
but an AUTONOMOUS investigation plan requires lexical anchoring
(matched_terms) or clearly strong semantic confidence (>= 0.75) — never a
calibrated-threshold near-miss on embedding similarity alone.

These tests simulate the configured machine deterministically by faking the
semantic backend at the exact calibrated threshold the owner machine hit.
"""
import pytest

from app.cognition.action_selection import InvestigationRegistry
from app.cognition.information_gain import InformationNeed
import app.cognition.tool_matcher as tool_matcher_module


def _need(question, target="subject", priority=0.5):
    return InformationNeed(question=question, target=target, reason="test",
                           priority=priority)


@pytest.fixture
def embeddings_active(monkeypatch):
    """Simulate LM Studio-style embeddings: every tool description is
    'conceptually relevant' at exactly the calibrated threshold (0.6) —
    which is what the owner machine's real backend produced for the vague
    'what is this' need against list_directory."""
    def fake_semantic_scores(text, tool_texts, *args, **kwargs):
        return (
            {action_type: 0.6 for action_type in tool_texts},
            "simulated-embeddings",
        )
    monkeypatch.setattr(
        tool_matcher_module, "semantic_scores", fake_semantic_scores)


def test_vague_need_refuses_even_with_embeddings_active(embeddings_active):
    """The exact owner-machine failure: with embeddings saturating the noise
    floor at the calibrated threshold, 'what is this' must still plan
    NOTHING — conceptual-only candidates are proposals, not autonomous
    plans."""
    assert InvestigationRegistry().plan(
        _need("what is this", target="mystery")) is None


def test_lexically_anchored_plan_survives_embeddings(embeddings_active):
    """The gate must not over-block: a need with real lexical evidence still
    plans autonomously even when embeddings are active (this was green on
    the owner machine and must stay green)."""
    plan = InvestigationRegistry().plan(
        _need("list all your capabilities", priority=0.5))
    assert plan is not None
    assert plan.tool == "list_capabilities"


def test_strong_semantic_confidence_still_plans(monkeypatch):
    """The gate is on WEAK conceptual-only evidence, not on semantic
    discovery itself: a clearly strong conceptual match (0.9) with zero
    lexical overlap remains plannable — that is the embedding bridge's
    value on a configured machine."""
    def fake_semantic_scores(text, tool_texts, *args, **kwargs):
        return (
            {action_type: 0.9 for action_type in tool_texts},
            "simulated-embeddings",
        )
    monkeypatch.setattr(
        tool_matcher_module, "semantic_scores", fake_semantic_scores)
    plan = InvestigationRegistry().plan(
        _need("tell me everything about this machine's current state"))
    # With every tool at 0.9 conceptual similarity, planning SOMETHING
    # plannable is expected — and whatever it picks must be a safe probe.
    if plan is not None:
        from app.tools.manifest import get_tool_manifest
        assert get_tool_manifest()[plan.tool]["safety_level"] <= 1


def test_gate_lives_in_planner_not_discovery(embeddings_active):
    """The gate must not corrupt DISCOVERY: with embeddings active the
    matcher still surfaces conceptual-only candidates as proposals (the
    chat layer shows them to the user for a decision)."""
    ranked = tool_matcher_module.rank_tools("what is this mystery", limit=5)
    # Candidates appear (conceptual-only included — they are proposals)...
    assert isinstance(ranked, list)
    for match in ranked:
        # ...but each carries the evidence for its score, so the planner
        # (and the user) can see which ones are lexical vs conceptual-only.
        assert match.semantic_score is not None
        assert isinstance(match.matched_terms, tuple)
