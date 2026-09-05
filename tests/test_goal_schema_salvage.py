"""LLM goal-representation salvage (owner diagnostics F1, 2026-09).

The owner's live run rejected the model's ENTIRE semantic goal
representation four times because ONE field failed validation:

    Rejected malformed LLM semantic goal representation:
    Invalid 'target_domain' 'code/data'. Must be one of [...]

For compound requests the model consistently answers 'code/data' — a
compound domain the strict schema rejects. The all-or-nothing validator
then discarded the model's intent, goal, entities, success conditions and
required capabilities, silently degrading D3/D4/D7 to the weak rule-based
fallback — the brain's best output was binned over one field.

The contract now: a malformed representation is SALVAGED field-by-field.
Fields that pass their own checks are used; an invalid domain is
normalized (a compound like 'code/data' resolves to its first valid
component; garbage keeps the heuristic domain); provenance honestly says
'llm_schema_salvaged'. A payload with nothing usable is still rejected
wholesale (the old behavior for true garbage).
"""

import json
from unittest.mock import patch

from app.cognition.goal_interpreter import SemanticGoalInterpreter


def llm_reply(payload: dict):
    return {
        "success": True,
        "choices": [{"message": {"content": json.dumps(payload)}}],
    }


FOUR_STEP_TEXT = ("Find files matching requirements, read the first one, "
                  "summarize it, then check the tests still pass.")

MODEL_FOUR_STEP = {
    "primary_intent_type": "action_intent",
    "target_domain": "code/data",  # the observed malformed field
    "goal": "Locate, read, summarize requirements and verify tests",
    "desired_outcome": "All four steps completed and verified",
    "entities": ["requirements"],
    "constraints": ["read_only"],
    "assumptions": [],
    "unknowns": [],
    "preconditions": [],
    "success_conditions": [
        "file_path_identified = true",
        "file_read = true",
        "summary_delivered = true",
        "tests_passed = true",
    ],
    "failure_conditions": ["tests_failed = true"],
    "required_capabilities": ["filesystem.search", "filesystem.read"],
    "risk_factors": [],
}


def test_compound_domain_representation_is_salvaged_not_discarded():
    """The exact live failure: 'code/data' must not bin the model's
    four-step success conditions."""
    with patch("app.llm.llm_client.generate_chat_completion",
               return_value=llm_reply(MODEL_FOUR_STEP)):
        rep = SemanticGoalInterpreter.interpret_goal(FOUR_STEP_TEXT,
                                                     complexity="main")
    # the model's per-step conditions SURVIVE (the live run got 1/4 from
    # the fallback; the model had enumerated all four)
    conditions = " | ".join(rep.success_conditions).lower()
    for step in ["file_path_identified", "file_read",
                 "summary_delivered", "tests_passed"]:
        assert step in conditions, (step, rep.success_conditions)
    # the compound domain is normalized to its first valid component
    assert rep.target_domain == "code"
    # Since 2026-09-05 compound domains are normalized AT VALIDATION
    # (review P4) — the representation passes the strict schema, so it
    # no longer routes through salvage. Provenance is the clean
    # disambiguation path; the salvage layer remains for genuinely
    # malformed representations.
    assert rep.provenance_source == "llm_semantic_disambiguation"
    # and the model's goal phrase is used, not the heuristic's
    assert "requirements" in rep.goal.lower()


def test_invalid_domain_without_valid_component_keeps_heuristic_domain():
    payload = dict(MODEL_FOUR_STEP, target_domain="definitely_not_a_domain")
    with patch("app.llm.llm_client.generate_chat_completion",
               return_value=llm_reply(payload)):
        rep = SemanticGoalInterpreter.interpret_goal(FOUR_STEP_TEXT,
                                                     complexity="main")
    # conditions still salvaged; domain falls back to the heuristic reading
    assert "tests_passed" in " ".join(rep.success_conditions).lower()
    assert rep.provenance_source == "llm_schema_salvaged"
    assert rep.target_domain != "definitely_not_a_domain"


def test_truly_unusable_payload_is_still_rejected_wholesale():
    """Nothing salvageable (no valid intent, no goal string, no lists) —
    the old full-rejection path must survive for real garbage."""
    payload = {
        "primary_intent_type": 42,
        "target_domain": "",
        "goal": "   ",
        "desired_outcome": None,
        "success_conditions": "not-a-list",
    }
    with patch("app.llm.llm_client.generate_chat_completion",
               return_value=llm_reply(payload)):
        rep = SemanticGoalInterpreter.interpret_goal(FOUR_STEP_TEXT,
                                                     complexity="main")
    assert rep.provenance_source == "rejected_malformed_llm_schema"
    # heuristic conditions stand (the pre-salvage behavior): the garbage
    # payload contributed NOTHING. The conditions after it are the
    # deterministic per-step backstop (F3a) for this compound request —
    # the heuristic filesystem condition comes first, untouched.
    assert rep.success_conditions[0] == "file_path_identified = true"
    assert "not-a-list" not in " ".join(rep.success_conditions)
    # F3a: the other three steps are covered by the compound backstop.
    assert len(rep.success_conditions) == 4


def test_fully_valid_representation_takes_the_clean_path():
    """Guard against overcorrection: a schema-clean representation is used
    as-is with the original provenance vocabulary."""
    payload = dict(MODEL_FOUR_STEP, target_domain="filesystem")
    with patch("app.llm.llm_client.generate_chat_completion",
               return_value=llm_reply(payload)):
        rep = SemanticGoalInterpreter.interpret_goal(FOUR_STEP_TEXT,
                                                     complexity="main")
    assert rep.provenance_source != "llm_schema_salvaged"
    assert rep.target_domain == "filesystem"
    assert "tests_passed" in " ".join(rep.success_conditions).lower()


def test_salvage_schema_is_field_level():
    """The mechanism itself: salvage_schema returns only usable fields."""
    salvaged = SemanticGoalInterpreter.salvage_schema(MODEL_FOUR_STEP)
    assert salvaged["target_domain"] == "code"  # compound normalization
    assert salvaged["primary_intent_type"] == "action_intent"
    assert len(salvaged["success_conditions"]) == 4
    # nothing usable -> empty salvage (caller rejects wholesale)
    assert SemanticGoalInterpreter.salvage_schema({"goal": " "}) == {}
    assert SemanticGoalInterpreter.salvage_schema("not a dict") == {}
