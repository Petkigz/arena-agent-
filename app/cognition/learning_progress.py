"""Learning-progress motivation: explore where competence is actually growing.

Curiosity spending was bounded only by the owner's exploration cap. This
module adds the human drive to practice what's LEARNING — targeting the zone
of proximal development: domains that are weak but improving fast.

Measured, not vibes:
  * Windows are computed from the action-outcome store's own evidence rows
    (recent 40% vs earlier 60%, by record order). Informative outcomes only
    (success/failure); verification-unknown never counts as a win.
  * progress = recent_rate − earlier_rate; gap = 1 − smoothed overall rate.
    learning_value = 0.6·max(0, progress) + 0.4·gap·(1 − overall_rate),
    requiring MIN_WINDOW informative outcomes in BOTH windows — otherwise the
    domain is labeled 'insufficient_data' and scores nothing.
  * Authority unchanged: this prioritizes WHICH exploratory goals get
    generated; the owner's exploration cap and all gates still bound
    everything.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger

RECENT_FRACTION = 0.4
MIN_WINDOW = 2
_INFO_OUTCOMES = ("verified_success", "verified_failure", "unverified_success")


@dataclass
class LearningProgress:
    action_type: str
    earlier_rate: Optional[float]
    recent_rate: Optional[float]
    progress: Optional[float]
    overall_rate: float
    gap: float
    learning_value: float
    earlier_n: int
    recent_n: int
    status: str  # improving | mastered | weak | declining | insufficient_data | no_data

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _window_rate(outcomes: List[str]) -> Optional[float]:
    informative = [o for o in outcomes if o in _INFO_OUTCOMES]
    if len(informative) < MIN_WINDOW:
        return None
    successes = sum(1 for o in informative if o in ("verified_success", "unverified_success"))
    return successes / len(informative)


class LearningProgressTracker:
    """Windowed success-rate progress per action type from the outcome store."""

    def __init__(self, outcomes_db: Optional[str] = None) -> None:
        self.outcomes_db = str(outcomes_db or (settings.DATA_DIR / "action_outcomes.db"))

    def _load_rows(self) -> Dict[str, List[str]]:
        per_action: Dict[str, List[str]] = {}
        try:
            with sqlite3.connect(self.outcomes_db) as conn:
                rows = conn.execute(
                    "SELECT action_type, outcome FROM action_outcomes ORDER BY created_at, transition_id"
                ).fetchall()
        except Exception as exc:
            app_logger.warning(f"Learning progress could not read outcome store: {exc}")
            return {}
        for action_type, outcome in rows:
            per_action.setdefault(str(action_type), []).append(str(outcome))
        return per_action

    def progress_for(self, action_type: str) -> LearningProgress:
        per_action = self._load_rows()
        outcomes = per_action.get(action_type, [])
        if not outcomes:
            return LearningProgress(action_type, None, None, None, 0.5, 0.5, 0.0, 0, 0, "no_data")
        recent_size = max(1, int(len(outcomes) * RECENT_FRACTION))
        recent, earlier = outcomes[-recent_size:], outcomes[:-recent_size] or outcomes
        recent_rate = _window_rate(recent)
        earlier_rate = _window_rate(earlier)
        overall_informative = [o for o in outcomes if o in _INFO_OUTCOMES]
        overall_rate = (
            sum(1 for o in overall_informative if o != "verified_failure") / len(overall_informative)
            if overall_informative else 0.5
        )
        gap = round(max(0.0, 1.0 - overall_rate), 4)
        if recent_rate is None or earlier_rate is None:
            return LearningProgress(
                action_type, earlier_rate if earlier_rate is not None else None, recent_rate,
                None, round(overall_rate, 4), gap, 0.0,
                len([o for o in earlier if o in _INFO_OUTCOMES]),
                len([o for o in recent if o in _INFO_OUTCOMES]),
                "insufficient_data",
            )
        progress = round(recent_rate - earlier_rate, 4)
        learning_value = round(
            max(0.0, min(1.0, 0.6 * max(0.0, progress) + 0.4 * gap * (1.0 - overall_rate))), 4
        )
        if progress > 0.1 and overall_rate < 0.95:
            status = "improving"
        elif overall_rate >= 0.95:
            status = "mastered"
        elif progress < -0.1:
            status = "declining"
        else:
            status = "weak" if overall_rate < 0.6 else "steady"
        return LearningProgress(
            action_type, round(earlier_rate, 4), round(recent_rate, 4), progress,
            round(overall_rate, 4), gap, learning_value,
            len([o for o in earlier if o in _INFO_OUTCOMES]),
            len([o for o in recent if o in _INFO_OUTCOMES]),
            status,
        )

    def report(self, limit: int = 25) -> Dict[str, Any]:
        per_action = self._load_rows()
        rows = []
        for action_type in per_action:
            progress = self.progress_for(action_type)
            if progress.status == "no_data":
                continue
            rows.append(progress)
        rows.sort(key=lambda p: (-p.learning_value, -p.gap))
        return {
            "success": True,
            "targets": [p.to_dict() for p in rows[: max(1, min(limit, 100))]],
            "note": "Exploration priorities from measured success-rate windows; the owner's exploration cap and all gates still bound autonomy.",
        }

    def top_targets(self, k: int = 2) -> List[LearningProgress]:
        """Best learning-value domains — only improving/weak ones qualify."""
        report = self.report(limit=100)
        eligible = [LearningProgress(**row) for row in report["targets"]
                    if row["status"] in ("improving", "weak") and row["learning_value"] > 0]
        return eligible[: max(1, k)]


# Module-level singleton reading the shared outcome store.
learning_progress_tracker = LearningProgressTracker()
