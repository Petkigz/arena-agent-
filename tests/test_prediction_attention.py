import pytest
from app.cognition.prediction_engine import PredictionEngine
from app.cognition.attention_manager import AttentionManager

def test_prediction_engine():
    pe = PredictionEngine()
    pred = pe.predict_action("open_application", {"app_query": "firefox"})
    assert pred.action_type == "open_application"
    
    surprisal = pe.evaluate_surprisal(pred, {"app_state": "running", "success": True})
    assert surprisal == 0.0

def test_attention_manager():
    am = AttentionManager()
    f1 = am.allocate_attention("routine_task", priority_score=0.5)
    assert f1.target_name == "routine_task"

    f2 = am.allocate_attention("urgent_security_alert", priority_score=0.9, urgency="urgent")
    assert f2.target_name == "urgent_security_alert"

    released = am.release_focus()
    assert released.target_name == "routine_task"
