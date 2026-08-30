"""P0 review #5: an agent must not pretend it knows the domain.

The defensive fallback used to map unknown domains by intent:
    action_intent      -> desktop_os
    information_need   -> diagnostic
    else               -> conversation
That made 'not classified' behave as 'definitely desktop'. The honest
state is domain='unknown' with a neutral baseline — capability discovery
(manifest semantics, world-model caps, memory lessons) resolves the goal.
"""

from app.cognition.goal_interpreter import SemanticGoalInterpreter


def test_unknown_domain_is_not_guessed_from_intent():
    intent, domain = SemanticGoalInterpreter.normalize_and_validate("action_intent", "quantum_flux")
    assert (intent, domain) == ("action_intent", "unknown")  # was desktop_os

    intent, domain = SemanticGoalInterpreter.normalize_and_validate("information_need", "warp_drive")
    assert domain == "unknown"  # was diagnostic

    intent, domain = SemanticGoalInterpreter.normalize_and_validate("knowledge_query", "dream_weaving")
    assert domain == "unknown"  # was conversation


def test_empty_domain_is_unknown():
    _, domain = SemanticGoalInterpreter.normalize_and_validate("action_intent", "")
    assert domain == "unknown"


def test_unknown_is_a_first_class_domain():
    """'unknown' round-trips instead of being re-classified."""
    _, domain = SemanticGoalInterpreter.normalize_and_validate("action_intent", "unknown")
    assert domain == "unknown"
    assert "unknown" in SemanticGoalInterpreter._valid_domains()


def test_real_domains_are_still_recognized():
    _, domain = SemanticGoalInterpreter.normalize_and_validate("action_intent", "desktop_os")
    assert domain == "desktop_os"
    _, domain = SemanticGoalInterpreter.normalize_and_validate("action_intent", "code")
    assert domain == "code"  # manifest categories stay valid


def test_unknown_domain_baseline_is_honest():
    """No domain prior -> no guessed candidates. Only the truthful
    conversational answer; discovery adds the real capabilities."""
    candidates = SemanticGoalInterpreter.build_candidates_for_domain("unknown", "do the thing")
    assert [c["action_type"] for c in candidates] == ["formulate_answer"]


def test_capability_discovery_resolves_unknown_domain_goals():
    """THE point: with no domain prior, the manifest semantic discovery
    still proposes the capability the goal actually needs."""
    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="unknown", user_text="compress my vacation photos into a zip",
    )
    actions = {c.get("action_type") for c in candidates}
    assert "compress_files" in actions
    assert "formulate_answer" in actions  # honest fallback coexists


def test_llm_may_answer_unknown_domain_honestly():
    """The LLM decomposition is allowed to say 'unknown' instead of being
    forced to pick a domain it cannot justify."""
    payload = {
        "primary_intent_type": "action_intent",
        "target_domain": "unknown",
        "goal": "Reorganize the flux archive",
        "desired_outcome": "Archive reorganized",
    }
    res = SemanticGoalInterpreter.validate_schema(payload)
    assert res.is_valid is True
    assert res.data["target_domain"] == "unknown"
