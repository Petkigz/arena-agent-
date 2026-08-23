"""Outcome-calibrated autonomy thresholds with owner-bounded exploration."""

from __future__ import annotations

import json
import math
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings
from app.utils.logger import audit_logger


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _smooth(previous: float, observed: float, weight: float = 0.3) -> float:
    return previous * (1.0 - weight) + observed * weight


@dataclass
class AdaptiveAutonomyProfile:
    prediction_error_threshold: float = 0.5
    low_success_rate_threshold: float = 0.6
    goal_auto_approve_threshold: float = 0.7
    unknown_entity_confidence: float = 0.5
    grounding_confidence: float = 0.6
    weak_causal_confidence: float = 0.4
    ram_pressure_threshold: float = 85.0
    cpu_pressure_threshold: float = 80.0
    disk_pressure_threshold: float = 90.0
    exploration_budget: int = 3
    owner_max_exploration_goals: int = 3
    sample_count: int = 0
    observed_success_rate: float = 0.0
    source: str = "defaults"

    def normalized(self) -> "AdaptiveAutonomyProfile":
        self.prediction_error_threshold = _clamp(self.prediction_error_threshold, 0.3, 0.8)
        self.low_success_rate_threshold = _clamp(self.low_success_rate_threshold, 0.4, 0.7)
        self.goal_auto_approve_threshold = _clamp(self.goal_auto_approve_threshold, 0.65, 0.9)
        self.unknown_entity_confidence = _clamp(self.unknown_entity_confidence, 0.3, 0.7)
        self.grounding_confidence = _clamp(self.grounding_confidence, 0.4, 0.8)
        self.weak_causal_confidence = _clamp(self.weak_causal_confidence, 0.2, 0.7)
        self.ram_pressure_threshold = _clamp(self.ram_pressure_threshold, 70, 95)
        self.cpu_pressure_threshold = _clamp(self.cpu_pressure_threshold, 65, 95)
        self.disk_pressure_threshold = _clamp(self.disk_pressure_threshold, 75, 97)
        self.owner_max_exploration_goals = max(0, min(10, int(self.owner_max_exploration_goals)))
        self.exploration_budget = max(
            0,
            min(int(self.exploration_budget), self.owner_max_exploration_goals),
        )
        self.sample_count = max(0, int(self.sample_count))
        self.observed_success_rate = _clamp(self.observed_success_rate, 0.0, 1.0)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AdaptiveAutonomyCalibrator:
    MIN_SAMPLES = 5

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path else settings.DATA_DIR / "adaptive_autonomy.json"
        self._lock = threading.RLock()
        self._profile = self._load()

    def _load(self) -> AdaptiveAutonomyProfile:
        if not self.path.exists():
            return AdaptiveAutonomyProfile()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            fields = AdaptiveAutonomyProfile.__dataclass_fields__
            return AdaptiveAutonomyProfile(**{
                key: value for key, value in raw.items() if key in fields
            }).normalized()
        except Exception:
            # Invalid calibration must fall back to conservative known defaults.
            return AdaptiveAutonomyProfile(source="defaults_after_invalid_file")

    def get_profile(self) -> AdaptiveAutonomyProfile:
        with self._lock:
            return AdaptiveAutonomyProfile(**self._profile.to_dict()).normalized()

    def _persist(self, profile: AdaptiveAutonomyProfile) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        temp.replace(self.path)

    def set_owner_max_exploration_goals(self, maximum: int) -> AdaptiveAutonomyProfile:
        with self._lock:
            self._profile.owner_max_exploration_goals = max(0, min(10, int(maximum)))
            self._profile.normalized()
            self._persist(self._profile)
            audit_logger.warning(
                f"Owner set maximum autonomous exploration goals to "
                f"{self._profile.owner_max_exploration_goals}"
            )
            return self.get_profile()

    def calibrate(self, outcome_store: Any) -> AdaptiveAutonomyProfile:
        """Update thresholds from verified strategy outcomes, bounded conservatively."""
        try:
            outcomes = outcome_store.all_outcomes(limit=500)
        except Exception:
            outcomes = []
        if len(outcomes) < self.MIN_SAMPLES:
            with self._lock:
                self._profile.sample_count = len(outcomes)
                self._profile.source = "defaults_insufficient_samples"
                self._profile.normalized()
                self._persist(self._profile)
                return self.get_profile()

        success_rate = sum(1 for item in outcomes if item.success) / len(outcomes)
        surprisals = sorted(_clamp(item.surprisal, 0.0, 1.0) for item in outcomes)
        percentile_index = min(
            len(surprisals) - 1,
            max(0, math.ceil(0.75 * len(surprisals)) - 1),
        )
        observed_surprisal_threshold = _clamp(surprisals[percentile_index], 0.35, 0.75)
        observed_low_success = _clamp(success_rate - 0.1, 0.4, 0.65)
        observed_approval = _clamp(0.75 + (0.6 - success_rate) * 0.2, 0.65, 0.85)
        observed_budget = 1 if success_rate < 0.5 else (2 if success_rate < 0.75 else 3)

        with self._lock:
            profile = self._profile
            profile.prediction_error_threshold = _smooth(
                profile.prediction_error_threshold, observed_surprisal_threshold
            )
            profile.low_success_rate_threshold = _smooth(
                profile.low_success_rate_threshold, observed_low_success
            )
            profile.goal_auto_approve_threshold = _smooth(
                profile.goal_auto_approve_threshold, observed_approval
            )
            profile.exploration_budget = min(
                observed_budget, profile.owner_max_exploration_goals
            )
            profile.sample_count = len(outcomes)
            profile.observed_success_rate = success_rate
            profile.source = "verified_strategy_outcomes"
            profile.normalized()
            self._persist(profile)
            return self.get_profile()


adaptive_autonomy_calibrator = AdaptiveAutonomyCalibrator()
