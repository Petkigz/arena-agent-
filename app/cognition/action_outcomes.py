"""Learned action→outcome statistics from Arena's verified execution history.

The existing app/cognition/world_model.py is an entity/observation state graph
("what things are in the world"); THIS module is its complement: "what my
actions DO". It learns empirical outcome distributions per action type from
the controlled-execution store and feeds them into the prediction engine — so
the uncertainty gate (F1.2), the counterfactual simulator, and every
prediction consumer get smarter with experience.

Honest scope, stated plainly:
  * v1 learns OUTCOME DISTRIBUTIONS per action type (verified success /
    verified failure / verification-unknown / unverified tool success), not
    full state-transition functions.
  * Estimates use Laplace smoothing toward the global rate plus Wilson
    confidence intervals; below MIN_SAMPLES the prior dominates and the
    estimate is labeled as such. Small samples never masquerade as knowledge.
  * Data comes only from recorded execution evidence; nothing is invented.
    Idempotent by execution id.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger

VERIFIED_SUCCESS = "verified_success"
VERIFIED_FAILURE = "verified_failure"
VERIFICATION_UNKNOWN = "verification_unknown"
UNVERIFIED_SUCCESS = "unverified_success"

_MIN_SAMPLES = 3
_PRIOR_STRENGTH = 5.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_digest(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass
class OutcomeEstimate:
    action_type: str
    n: int
    verified_successes: int
    verified_failures: int
    verification_unknown: int
    unverified_successes: int
    raw_success_rate: float
    smoothed_success_rate: float
    global_rate: float
    wilson_low: float
    wilson_high: float
    evidence_sufficient: bool
    confidence_source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_outcome(result: Dict[str, Any]) -> Optional[str]:
    """Map an execution result to an honest outcome class (or None if unusable)."""
    if not isinstance(result, dict):
        return None
    if result.get("goal_verified") is True:
        return VERIFIED_SUCCESS
    if result.get("verification_unknown") is True:
        return VERIFICATION_UNKNOWN
    if result.get("goal_verified") is False:
        return VERIFIED_FAILURE
    if result.get("success") is True:
        return UNVERIFIED_SUCCESS
    if result.get("success") is False:
        return VERIFIED_FAILURE
    return None


class ActionOutcomeStore:
    """Persistent action→outcome statistics with idempotent evidence intake."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "action_outcomes.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._estimate_cache: Dict[str, tuple] = {}
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS action_outcomes (
                transition_id TEXT PRIMARY KEY,
                execution_id TEXT,
                action_type TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                outcome TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outcome_action ON action_outcomes(action_type)")
            conn.commit()

    def record(self, action_type: str, payload: Dict[str, Any], outcome: str,
               *, execution_id: Optional[str] = None, source: str = "manual") -> Dict[str, Any]:
        if outcome not in (VERIFIED_SUCCESS, VERIFIED_FAILURE, VERIFICATION_UNKNOWN, UNVERIFIED_SUCCESS):
            return {"recorded": False, "error": f"unknown outcome class '{outcome}'"}
        with self._lock:
            if execution_id:
                with sqlite3.connect(self.db_path) as conn:
                    exists = conn.execute(
                        "SELECT 1 FROM action_outcomes WHERE execution_id=?", (execution_id,)
                    ).fetchone()
                if exists:
                    return {"recorded": False, "reason": "duplicate execution evidence (idempotent)"}
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO action_outcomes VALUES (?,?,?,?,?,?,?)",
                    (f"ao_{uuid4().hex[:14]}", execution_id, str(action_type),
                     _payload_digest(payload or {}), outcome, source, _now()),
                )
                conn.commit()
            self._estimate_cache.pop(str(action_type), None)
            self._estimate_cache.pop(None, None)
            return {"recorded": True}

    def ingest_execution_registry(self, registry) -> Dict[str, Any]:
        """Bulk-import outcome evidence from the controlled-execution store."""
        imported, skipped = 0, 0
        try:
            with sqlite3.connect(registry.db_path) as conn:
                rows = conn.execute(
                    """SELECT ce.execution_id, ce.action_type, cr.result_json
                       FROM controlled_executions ce
                       JOIN controlled_execution_results cr ON ce.execution_id = cr.execution_id"""
                ).fetchall()
        except Exception as exc:
            app_logger.warning(f"Action-outcome registry ingest failed: {exc}")
            return {"imported": 0, "skipped": 0, "error": str(exc)}
        for execution_id, action_type, result_json in rows:
            try:
                outcome = classify_outcome(json.loads(result_json))
            except Exception:
                outcome = None
            if outcome is None:
                skipped += 1
                continue
            result = self.record(action_type, {}, outcome,
                                 execution_id=execution_id, source="execution_registry")
            imported += 1 if result.get("recorded") else 0
        if imported:
            audit_logger.info("Action outcomes ingested %d execution results", imported)
        return {"imported": imported, "skipped": skipped}

    def _counts(self) -> Dict[str, Dict[str, int]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT action_type, outcome, COUNT(*) FROM action_outcomes GROUP BY action_type, outcome"
            ).fetchall()
        counts: Dict[str, Dict[str, int]] = {}
        for action_type, outcome, n in rows:
            counts.setdefault(action_type, {})[outcome] = int(n)
        return counts

    def estimate(self, action_type: str, *, refresh: bool = False) -> OutcomeEstimate:
        with self._lock:
            cached = self._estimate_cache.get(action_type)
            if cached and not refresh and time.time() - cached[0] < 60:
                return cached[1]
            counts = self._counts()
            total = sum(sum(c.values()) for c in counts.values())
            total_successes = sum(
                c.get(VERIFIED_SUCCESS, 0) + c.get(UNVERIFIED_SUCCESS, 0) for c in counts.values()
            )
            global_rate = (total_successes / total) if total else 0.5
            c = counts.get(action_type, {})
            n = sum(c.values())
            successes = c.get(VERIFIED_SUCCESS, 0) + c.get(UNVERIFIED_SUCCESS, 0)
            # Honest denominator: unknown outcomes are neither success nor
            # failure; they shrink effective evidence instead of counting as wins.
            informative = successes + c.get(VERIFIED_FAILURE, 0)
            raw = successes / n if n else 0.0
            smoothed = (
                (successes + _PRIOR_STRENGTH * global_rate) / (informative + _PRIOR_STRENGTH)
                if (informative + _PRIOR_STRENGTH) > 0 else global_rate
            )
            low, high = _wilson_interval(successes, informative) if informative else (0.0, 1.0)
            estimate = OutcomeEstimate(
                action_type=action_type, n=n,
                verified_successes=c.get(VERIFIED_SUCCESS, 0),
                verified_failures=c.get(VERIFIED_FAILURE, 0),
                verification_unknown=c.get(VERIFICATION_UNKNOWN, 0),
                unverified_successes=c.get(UNVERIFIED_SUCCESS, 0),
                raw_success_rate=round(raw, 4),
                smoothed_success_rate=round(max(0.0, min(1.0, smoothed)), 4),
                global_rate=round(global_rate, 4),
                wilson_low=round(low, 4), wilson_high=round(high, 4),
                evidence_sufficient=informative >= _MIN_SAMPLES,
                confidence_source=(
                    f"world_model:n={informative}" if informative >= _MIN_SAMPLES else "prior (insufficient evidence)"
                ),
            )
            self._estimate_cache[action_type] = (time.time(), estimate)
            return estimate

    def report(self, limit: int = 50) -> Dict[str, Any]:
        counts = self._counts()
        rows = [self.estimate(a).to_dict()
                for a in sorted(counts, key=lambda x: -sum(counts[x].values()))[:limit]]
        return {"success": True, "actions": rows,
                "note": "Empirical outcome rates from recorded execution evidence only."}


# Module-level singleton, mirroring the other stores.
action_outcome_store = ActionOutcomeStore()


def learned_confidence(action_type: str) -> Optional[float]:
    """Empirical success estimate for the action, or None when evidence is thin."""
    estimate = action_outcome_store.estimate(action_type)
    if not estimate.evidence_sufficient:
        return None
    return estimate.smoothed_success_rate
