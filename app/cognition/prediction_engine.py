"""Phase C/P1-E: Prediction vs Outcome Surprisal Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from app.utils.logger import app_logger, audit_logger

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class WorldPrediction:
    action_type: str
    expected_changes: Dict[str, Any]
    confidence: float = 0.85
    prediction_id: str = field(default_factory=lambda: f"pred_{uuid4().hex[:8]}")
    created_at: str = field(default_factory=_now)

class PredictionEngine:
    """
    P1-E: Prediction vs. Outcome Surprisal Loop Engine.
    Generates expected world-state changes before tool execution and computes prediction error/surprisal
    to feed Bayesian belief revision and memory reflection.
    """

    def __init__(self) -> None:
        self._predictions: List[WorldPrediction] = []

    def predict_action(self, action_type: str, payload: Dict[str, Any]) -> WorldPrediction:
        expected = {}
        act_clean = action_type.lower().strip()

        if "open_application" in act_clean or "launch" in act_clean:
            expected = {"app_state": "running", "success": True}
        elif "file" in act_clean:
            expected = {"file_operation": "completed", "success": True}
        elif "search" in act_clean:
            expected = {"results_found": True, "success": True}
        else:
            expected = {"action_executed": True, "success": True}

        pred = WorldPrediction(action_type=action_type, expected_changes=expected)
        self._predictions.append(pred)
        app_logger.info(f"PredictionEngine predicted outcome for '{action_type}': {expected}")
        return pred

    def evaluate_surprisal(self, prediction: WorldPrediction, actual_state: Dict[str, Any]) -> float:
        """
        Computes prediction error/surprisal (0.0 = perfect prediction match, 1.0 = total surprise/unexpected failure).
        """
        if not prediction.expected_changes:
            return 0.0

        matches = 0
        for k, expected_v in prediction.expected_changes.items():
            actual_v = actual_state.get(k)
            if actual_v == expected_v or (isinstance(actual_v, list) and len(actual_v) > 0 and expected_v is True):
                matches += 1

        accuracy = matches / len(prediction.expected_changes)
        surprisal = round(1.0 - accuracy, 2)

        audit_logger.info(f"PredictionEngine evaluated surprisal for '{prediction.action_type}': {surprisal} (Accuracy: {accuracy:.2f})")
        return surprisal
