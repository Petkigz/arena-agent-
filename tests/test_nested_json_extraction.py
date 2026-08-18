from app.cognition.goal_interpreter import SemanticGoalInterpreter


def test_extract_json_object_handles_nested_braces_and_strings():
    """
    Verify extract_json_object extracts outer JSON object containing nested objects
    or braces inside strings without regex non-nesting truncation errors.
    """
    nested_json_raw = '''
    Here is the goal v2 decomposition:
    ```json
    {
        "primary_intent_type": "action_intent",
        "target_domain": "desktop_os",
        "goal": "Open Photoshop {v2024}",
        "desired_outcome": "Process active",
        "nested_details": {
            "app_path": "C:\\Program Files\\Adobe\\Photoshop.exe",
            "flags": ["--no-splash"]
        },
        "entities": ["Photoshop"]
    }
    ```
    '''

    extracted = SemanticGoalInterpreter.extract_json_object(nested_json_raw)

    assert extracted is not None
    assert extracted["primary_intent_type"] == "action_intent"
    assert extracted["target_domain"] == "desktop_os"
    assert "nested_details" in extracted
    assert extracted["nested_details"]["app_path"] == "C:\\Program Files\\Adobe\\Photoshop.exe"
