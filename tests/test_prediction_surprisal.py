import pytest
from app.cognition.prediction_engine import PredictionEngine, WorldPrediction

def test_prediction_surprisal_loop():
    pe = PredictionEngine()

    # 1. Predict launch action
    pred1 = pe.predict_action("launch_app", {"app_query": "firefox"})
    assert pred1.action_type == "launch_app"
    assert pred1.expected_changes["success"] is True

    # 2. Perfect match outcome -> 0.0 surprisal
    surprisal1 = pe.evaluate_surprisal(pred1, {"success": True, "app_state": "running"})
    assert surprisal1 == 0.0

    # 3. Unexpected failure outcome -> 1.0 surprisal
    surprisal2 = pe.evaluate_surprisal(pred1, {"success": False, "error": "App not found"})
    assert surprisal2 == 1.0
