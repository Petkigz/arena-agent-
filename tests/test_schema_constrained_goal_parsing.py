from unittest.mock import patch
from app.cognition.goal_interpreter import SemanticGoalInterpreter


def test_validate_schema_accepts_valid_representation():
    """
    Verify validate_schema accepts schema-compliant JSON payloads carrying
    valid intent, domain, goal, outcome, entities, conditions, capabilities, and risks.
    """
    valid_payload = {
        "primary_intent_type": "action_intent",
        "target_domain": "desktop_os",
        "goal": "Launch Photoshop",
        "desired_outcome": "Photoshop process running",
        "entities": ["Photoshop"],
        "constraints": ["user_session_active"],
        "assumptions": ["installed"],
        "unknowns": [],
        "preconditions": ["os_gui_running"],
        "success_conditions": ["process_running = true"],
        "failure_conditions": ["launch_failed = true"],
        "required_capabilities": ["os.launch_app"],
        "risk_factors": ["low"]
    }

    res = SemanticGoalInterpreter.validate_schema(valid_payload)
    assert res.is_valid is True
    assert res.data["primary_intent_type"] == "action_intent"
    assert res.data["target_domain"] == "desktop_os"
    assert res.data["goal"] == "Launch Photoshop"
    assert res.data["entities"] == ["Photoshop"]
    assert res.data["success_conditions"] == ["process_running = true"]


def test_validate_schema_rejects_invalid_intent_or_domain():
    """
    Verify validate_schema explicitly rejects malformed semantic representations
    with unsupported intent types or domains.
    """
    invalid_intent_payload = {
        "primary_intent_type": "telepathic_projection",
        "target_domain": "desktop_os",
        "goal": "Do magic",
        "desired_outcome": "Magic done"
    }
    res_intent = SemanticGoalInterpreter.validate_schema(invalid_intent_payload)
    assert res_intent.is_valid is False
    assert "Invalid 'primary_intent_type'" in res_intent.validation_error

    invalid_domain_payload = {
        "primary_intent_type": "action_intent",
        "target_domain": "multiverse_portal",
        "goal": "Do magic",
        "desired_outcome": "Magic done"
    }
    res_domain = SemanticGoalInterpreter.validate_schema(invalid_domain_payload)
    assert res_domain.is_valid is False
    assert "Invalid 'target_domain'" in res_domain.validation_error


def test_validate_schema_rejects_non_list_array_fields():
    """
    Verify validate_schema explicitly rejects malformed representations
    where array fields (entities, conditions, capabilities) are malformed types.
    """
    malformed_entities_payload = {
        "primary_intent_type": "action_intent",
        "target_domain": "desktop_os",
        "goal": "Open app",
        "desired_outcome": "App running",
        "entities": "Photoshop"  # Should be a list, not a string
    }
    res = SemanticGoalInterpreter.validate_schema(malformed_entities_payload)
    assert res.is_valid is False
    assert "Field 'entities' must be a list" in res.validation_error


def test_interpret_goal_rejects_malformed_llm_representation_and_falls_back():
    """
    Verify interpret_goal rejects malformed LLM responses that fail schema validation
    and falls back to heuristic baseline with provenance 'rejected_malformed_llm_schema'.
    """
    mock_malformed_llm_reply = {
        "choices": [{
            "message": {
                "content": '{"primary_intent_type": "unsupported_type", "target_domain": "desktop_os", "goal": "Open", "desired_outcome": "Done", "entities": "Photoshop"}'
            }
        }]
    }

    with patch("app.llm.llm_client.generate_chat_completion", return_value=mock_malformed_llm_reply):
        goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop", complexity="main")
        assert goal_rep.provenance_source == "rejected_malformed_llm_schema"
        assert goal_rep.confidence == 0.50
