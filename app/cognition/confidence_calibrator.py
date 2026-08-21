"""Phase 5B: Confidence Calibration.

Tracks the relationship between predicted confidence and actual outcomes.
Adjusts future predictions so that "I'm 60% sure" actually means the
system is right 60% of the time.

Uses binned calibration: groups predictions into confidence bins and
tracks actual success rates per bin. Applies correction factors to
future predictions.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Calibration Data ─────────────────────────────────────────────────

NUM_BINS = 10  # Confidence bins: [0-10%], [10-20%], ..., [90-100%]

@dataclass(frozen=True)
class CalibrationRecord:
    """A single prediction-outcome pair for calibration tracking."""
    record_id: str
    action_type: str
    predicted_confidence: float   # what the system predicted (0.0-1.0)
    actual_outcome: bool          # did it actually succeed?
    surprisal: float              # prediction error
    goal_type: str
    timestamp: str = field(default_factory=_now)


@dataclass(frozen=True)
class CalibrationBin:
    """Aggregated statistics for a confidence bin."""
    bin_index: int          # 0-9
    bin_low: float          # e.g., 0.5
    bin_high: float         # e.g., 0.6
    total_predictions: int
    actual_successes: int
    actual_rate: float      # actual success rate in this bin
    predicted_rate: float   # average predicted confidence in this bin
    calibration_error: float  # |actual_rate - predicted_rate|


@dataclass(frozen=True)
class CalibrationReport:
    """Full calibration assessment."""
    total_records: int
    bins: List[CalibrationBin]
    overall_calibration_error: float  # weighted average calibration error
    is_calibrated: bool               # True if error < threshold
    correction_factors: Dict[int, float]  # bin_index → correction factor
    ece: float                        # Expected Calibration Error
    timestamp: str = field(default_factory=_now)


# ── Confidence Calibrator ────────────────────────────────────────────

class ConfidenceCalibrator:
    """
    Tracks predicted vs actual confidence and applies calibration corrections.

    Usage:
        calibrator = ConfidenceCalibrator(db_path="calibration.db")

        # Record a prediction-outcome pair
        calibrator.record("search_files", predicted_confidence=0.8, actual_outcome=True)

        # Get calibrated confidence for a new prediction
        calibrated = calibrator.calibrate("search_files", raw_confidence=0.8)
        # calibrated might be 0.7 if the system tends to be overconfident at 0.8
    """

    CALIBRATION_THRESHOLD = 0.1  # ECE below this = "calibrated"
    MIN_RECORDS_PER_BIN = 3      # Need at least this many to compute correction

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._records: List[CalibrationRecord] = []
        self._correction_cache: Dict[str, Dict[int, float]] = {}  # action_type → {bin → factor}
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS calibration_records (
                record_id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                predicted_confidence REAL NOT NULL,
                actual_outcome INTEGER NOT NULL,
                surprisal REAL NOT NULL DEFAULT 0.0,
                goal_type TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cal_action
            ON calibration_records(action_type)
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""SELECT record_id, action_type, predicted_confidence,
            actual_outcome, surprisal, goal_type, timestamp
            FROM calibration_records ORDER BY timestamp""")
        for row in cursor.fetchall():
            self._records.append(CalibrationRecord(
                record_id=row[0], action_type=row[1],
                predicted_confidence=row[2], actual_outcome=bool(row[3]),
                surprisal=row[4], goal_type=row[5], timestamp=row[6]
            ))
        conn.close()

    def _save_to_db(self, record: CalibrationRecord) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO calibration_records
            (record_id, action_type, predicted_confidence, actual_outcome,
             surprisal, goal_type, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (record.record_id, record.action_type, record.predicted_confidence,
              int(record.actual_outcome), record.surprisal, record.goal_type,
              record.timestamp))
        conn.commit()
        conn.close()

    @staticmethod
    def _bin_index(confidence: float) -> int:
        """Map confidence (0.0-1.0) to bin index (0-9)."""
        return min(NUM_BINS - 1, max(0, int(confidence * NUM_BINS)))

    def record(
        self,
        action_type: str,
        predicted_confidence: float,
        actual_outcome: bool,
        surprisal: float = 0.0,
        goal_type: str = ""
    ) -> CalibrationRecord:
        """Record a prediction-outcome pair for calibration tracking."""
        predicted_confidence = max(0.0, min(1.0, predicted_confidence))
        record = CalibrationRecord(
            record_id=uuid4().hex[:12],
            action_type=action_type,
            predicted_confidence=predicted_confidence,
            actual_outcome=actual_outcome,
            surprisal=surprisal,
            goal_type=goal_type
        )
        self._records.append(record)
        self._save_to_db(record)

        # Invalidate correction cache for this action type
        self._correction_cache.pop(action_type, None)
        self._correction_cache.pop("global", None)

        return record

    def compute_bins(
        self,
        action_type: Optional[str] = None
    ) -> List[CalibrationBin]:
        """Compute calibration bins from recorded data."""
        # Filter records
        records = self._records
        if action_type:
            records = [r for r in records if r.action_type == action_type]

        # Build bins
        bin_data: Dict[int, List[Tuple[float, bool]]] = {i: [] for i in range(NUM_BINS)}
        for record in records:
            idx = self._bin_index(record.predicted_confidence)
            bin_data[idx].append((record.predicted_confidence, record.actual_outcome))

        bins: List[CalibrationBin] = []
        for i in range(NUM_BINS):
            entries = bin_data[i]
            total = len(entries)
            if total == 0:
                bins.append(CalibrationBin(
                    bin_index=i,
                    bin_low=i / NUM_BINS,
                    bin_high=(i + 1) / NUM_BINS,
                    total_predictions=0,
                    actual_successes=0,
                    actual_rate=0.0,
                    predicted_rate=(i + 0.5) / NUM_BINS,
                    calibration_error=0.0,
                ))
            else:
                successes = sum(1 for _, outcome in entries if outcome)
                avg_predicted = sum(pred for pred, _ in entries) / total
                actual_rate = successes / total
                bins.append(CalibrationBin(
                    bin_index=i,
                    bin_low=i / NUM_BINS,
                    bin_high=(i + 1) / NUM_BINS,
                    total_predictions=total,
                    actual_successes=successes,
                    actual_rate=round(actual_rate, 4),
                    predicted_rate=round(avg_predicted, 4),
                    calibration_error=round(abs(actual_rate - avg_predicted), 4),
                ))

        return bins

    def compute_correction_factors(
        self,
        action_type: Optional[str] = None
    ) -> Dict[int, float]:
        """
        Compute correction factors per bin.
        Factor = actual_rate / predicted_rate (clamped to [0.5, 1.5])
        """
        key = action_type or "global"
        if key in self._correction_cache:
            return self._correction_cache[key]

        bins = self.compute_bins(action_type)
        factors: Dict[int, float] = {}

        for b in bins:
            if b.total_predictions >= self.MIN_RECORDS_PER_BIN and b.predicted_rate > 0:
                factor = b.actual_rate / b.predicted_rate
                factors[b.bin_index] = max(0.5, min(1.5, round(factor, 3)))
            else:
                factors[b.bin_index] = 1.0  # Not enough data → no correction

        self._correction_cache[key] = factors
        return factors

    def calibrate(
        self,
        action_type: str,
        raw_confidence: float,
        context: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Apply calibration correction to a raw confidence prediction.
        Returns adjusted confidence that better reflects actual success rate.

        `context` is accepted for forward-compatibility (the runtime passes
        skill_type / complexity); the current binning-based calibration does not
        yet consume it, but accepting it prevents the call from failing.
        """
        raw_confidence = max(0.0, min(1.0, raw_confidence))
        bin_idx = self._bin_index(raw_confidence)

        # Try action-specific corrections first
        action_factors = self.compute_correction_factors(action_type)
        factor = action_factors.get(bin_idx, 1.0)

        # If no action-specific data, try global corrections
        if factor == 1.0 and action_type != "global":
            global_factors = self.compute_correction_factors(None)
            factor = global_factors.get(bin_idx, 1.0)

        calibrated = raw_confidence * factor
        return max(0.0, min(1.0, round(calibrated, 4)))

    def generate_report(
        self,
        action_type: Optional[str] = None
    ) -> CalibrationReport:
        """Generate a full calibration report."""
        records = self._records
        if action_type:
            records = [r for r in records if r.action_type == action_type]

        bins = self.compute_bins(action_type)
        factors = self.compute_correction_factors(action_type)

        # Expected Calibration Error (weighted average of bin errors)
        total_weighted_error = 0.0
        total_weight = 0
        for b in bins:
            total_weighted_error += b.calibration_error * b.total_predictions
            total_weight += b.total_predictions

        ece = total_weighted_error / total_weight if total_weight > 0 else 0.0

        return CalibrationReport(
            total_records=len(records),
            bins=bins,
            overall_calibration_error=round(ece, 4),
            is_calibrated=ece < self.CALIBRATION_THRESHOLD,
            correction_factors=factors,
            ece=round(ece, 4),
        )

    def total_records(self) -> int:
        return len(self._records)
