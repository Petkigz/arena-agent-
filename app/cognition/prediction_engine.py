"""Phase C: Prediction & World-State Outcome Engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class WorldPrediction:
    action_type: str
    expected_changes: Dict[str, Any]
    confidence: float = 0.85
    prediction_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=_now)

class PredictionEngine:
    """Predicts expected world state changes before tool execution and computes prediction error."""

    def __init__(self) -> None:
        self._predictions: List[WorldPrediction] = []

    def predict_action(self, action_type: str, payload: Dict[str, Any]) -> WorldPrediction:
        expected = {}
        if "open_application" in action_type or "launch" in action_type:
            expected = {"app_state": "running", "active_window": payload.get("app_query", "app")}
        elif "file" in action_type:
            expected = {"file_modified": True, "file_path": payload.get("file_path", "workspace")}
        else:
            expected = {"action_executed": True}

        pred = WorldPrediction(action_type=action_type, expected_changes=expected)
        self._predictions.append(pred)
        return pred

    def evaluate_surprisal(self, prediction: WorldPrediction, actual_state: Dict[str, Any]) -> float:
        """
        Computes prediction error (0.0 = perfect prediction, 1.0 = total surprise).
        """
        if not prediction.expected_changes:
            return 0.0

        matches = sum(1 for k, v in prediction.expected_changes.items() if actual_state.get(k) == v)
        accuracy = matches / len(prediction.expected_changes)
        surprisal = round(1.0 - accuracy, 2)
        return surprisal
