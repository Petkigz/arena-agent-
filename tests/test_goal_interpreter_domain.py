"""Domain-specific semantic attribute tests.

These verify the STRUCTURAL contract of SemanticGoalInterpreter: every query
produces a well-formed representation with a valid intent + domain, populated
list fields, and an in-range confidence. The exact strings inside the lists are
model-dependent (a live LLM produces different but valid phrasing than the
offline heuristic), so they are NOT asserted here.
"""

from app.cognition.goal_interpreter import SemanticGoalInterpreter, SemanticGoalRepresentation

VALID_INTENTS = {"action_intent", "information_need", "knowledge_query"}
VALID_DOMAINS = {
    "desktop_os", "filesystem", "web_research", "mobile_phone",
    "vision_desktop", "diagnostic", "conversation",
}
LIST_FIELDS = [
    "constraints", "assumptions", "unknowns", "preconditions",
    "success_conditions", "failure_conditions", "required_capabilities",
    "risk_factors", "entities",
]


def _assert_well_formed(goal_rep):
    assert isinstance(goal_rep, SemanticGoalRepresentation)
    assert goal_rep.primary_intent_type in VALID_INTENTS
    assert goal_rep.target_domain in VALID_DOMAINS
    assert 0.0 <= goal_rep.confidence <= 1.0
    assert isinstance(goal_rep.provenance_source, str) and goal_rep.provenance_source
    for field in LIST_FIELDS:
        assert isinstance(getattr(goal_rep, field), list), f"{field} must be a list"
    # A well-formed goal carries at least one success + failure criterion.
    assert len(goal_rep.success_conditions) >= 1
    assert len(goal_rep.failure_conditions) >= 1


def test_desktop_os_query_assigns_domain_specific_semantic_attributes():
    goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
    _assert_well_formed(goal_rep)


def test_filesystem_query_assigns_domain_specific_semantic_attributes():
    goal_rep = SemanticGoalInterpreter.interpret_goal("Find document contract.pdf")
    _assert_well_formed(goal_rep)


def test_web_research_query_assigns_domain_specific_semantic_attributes():
    goal_rep = SemanticGoalInterpreter.interpret_goal("Search web for Qwen2.5 benchmarks")
    _assert_well_formed(goal_rep)
