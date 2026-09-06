"""Focused tests for conservative response/evidence reconciliation."""

from app.cognition.response_grounding import reconcile_response


def test_deterministic_answer_mismatch_is_replaced_with_authoritative_value():
    reply, result = reconcile_response(
        "The result is 41.",
        deterministic_answers=[
            {"expression": "2 + 2", "value": 4, "value_str": "4"},
        ],
    )

    assert "2 + 2 = 4" in reply
    assert result.status == "contradicted"
    assert result.recovery_applied is True
    assert result.supported is False


def test_deterministic_answer_that_matches_is_preserved():
    reply, result = reconcile_response(
        "The result is 4.",
        deterministic_answers=[
            {"expression": "2 + 2", "value": 4, "value_str": "4"},
        ],
    )

    assert reply == "The result is 4."
    assert result.status == "verified"
    assert result.recovery_applied is False
    assert result.authoritative_facts == ["2 + 2 = 4"]


def test_positive_discovery_against_empty_observation_is_replaced():
    reply, result = reconcile_response(
        "I found three matching files.",
        observation_evidence="search_files: []",
    )

    assert "no matching results" in reply
    assert result.status == "contradicted"
    assert result.recovery_applied is True


def test_nonempty_count_is_not_treated_as_empty_observation():
    reply, result = reconcile_response(
        "I found ten matching files.",
        observation_evidence="10 results returned",
    )

    assert reply == "I found ten matching files."
    assert result.status == "supported"
    assert result.recovery_applied is False


def test_honest_negative_discovery_is_not_rewritten():
    reply, result = reconcile_response(
        "I found no matching files.",
        observation_evidence="search_files: []",
    )

    assert reply == "I found no matching files."
    assert result.status == "supported"
    assert result.recovery_applied is False


def test_structured_empty_observation_does_not_depend_on_text_markers():
    reply, result = reconcile_response(
        "I found three matching files.",
        authoritative_facts=["search probe returned an empty result set"],
        observation_empty=True,
    )

    assert "no matching results" in reply
    assert result.recovery_applied is True
    assert result.authoritative_facts == ["the observation returned no matching results"]


def test_structured_authoritative_facts_are_retained():
    reply, result = reconcile_response(
        "The app is running.",
        authoritative_facts=["process_state=running", "source=direct_probe"],
        observation_empty=False,
    )

    assert reply == "The app is running."
    assert result.status == "supported"
    assert result.authoritative_facts == ["process_state=running", "source=direct_probe"]


def test_unstructured_prose_is_not_rewritten_without_authoritative_evidence():
    reply, result = reconcile_response("This might be the right explanation.")

    assert reply == "This might be the right explanation."
    assert result.status == "unknown"
    assert result.recovery_applied is False
