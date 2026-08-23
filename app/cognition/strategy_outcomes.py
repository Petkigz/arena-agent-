"""Phase 1B: Strategy Outcome Tracking & Outcome-Influenced Selection.

Records every task outcome (goal_type, strategy_used, success/failure,
latency, surprisal) and provides historical success rates to influence
future strategy selection.

Strategies that repeatedly fail for a task_type are deprioritized.
Strategies that succeed are boosted. Failed strategies are never deleted —
they remain available as fallbacks when preferred strategies are unavailable.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class StrategyOutcome:
    """A single recorded task outcome."""
    outcome_id: str
    goal_type: str          # e.g. "open_app", "search_files", "web_search"
    action_type: str        # the strategy used: "open_application", "search_files", etc.
    success: bool           # did goal verification pass?
    latency_ms: float       # how long the task took
    surprisal: float        # prediction error (0.0 = expected, 1.0 = total surprise)
    goal_text: str          # original user request (truncated)
    timestamp: str = field(default_factory=_now)


@dataclass(frozen=True)
class StrategyScore:
    """Aggregated performance score for a (goal_type, action_type) pair."""
    goal_type: str
    action_type: str
    total_attempts: int
    successes: int
    failures: int
    success_rate: float     # successes / total_attempts
    avg_latency_ms: float
    avg_surprisal: float
    last_used: str          # most recent timestamp
    consecutive_failures: int  # current streak of failures


class StrategyOutcomeStore:
    """
    SQLite-backed store for strategy outcomes.
    Records every task outcome and provides historical success rates
    for outcome-influenced strategy selection.
    """

    # Minimum attempts before historical data influences selection
    MIN_ATTEMPTS_FOR_INFLUENCE = 2

    # Maximum weight historical data can have on utility score (0.0-1.0)
    MAX_HISTORY_WEIGHT = 0.4

    # Consecutive failure threshold for strong deprioritization
    CONSECUTIVE_FAILURE_THRESHOLD = 3

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._outcomes: List[StrategyOutcome] = []
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_outcomes (
                outcome_id TEXT PRIMARY KEY,
                goal_type TEXT NOT NULL,
                action_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                latency_ms REAL NOT NULL DEFAULT 0.0,
                surprisal REAL NOT NULL DEFAULT 0.0,
                goal_text TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_outcomes_goal_action
            ON strategy_outcomes(goal_type, action_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_outcomes_timestamp
            ON strategy_outcomes(timestamp)
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT outcome_id, goal_type, action_type, success, latency_ms, surprisal, goal_text, timestamp FROM strategy_outcomes ORDER BY timestamp")
        for row in cursor.fetchall():
            self._outcomes.append(StrategyOutcome(
                outcome_id=row[0], goal_type=row[1], action_type=row[2],
                success=bool(row[3]), latency_ms=row[4], surprisal=row[5],
                goal_text=row[6], timestamp=row[7]
            ))
        conn.close()

    def _save_to_db(self, outcome: StrategyOutcome) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO strategy_outcomes
            (outcome_id, goal_type, action_type, success, latency_ms, surprisal, goal_text, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (outcome.outcome_id, outcome.goal_type, outcome.action_type,
              int(outcome.success), outcome.latency_ms, outcome.surprisal,
              outcome.goal_text, outcome.timestamp))
        conn.commit()
        conn.close()

    def record_outcome(
        self,
        goal_type: str,
        action_type: str,
        success: bool,
        latency_ms: float = 0.0,
        surprisal: float = 0.0,
        goal_text: str = ""
    ) -> StrategyOutcome:
        """Record a completed task outcome."""
        outcome = StrategyOutcome(
            outcome_id=uuid4().hex[:12],
            goal_type=goal_type,
            action_type=action_type,
            success=success,
            latency_ms=latency_ms,
            surprisal=surprisal,
            goal_text=goal_text[:200]
        )
        self._outcomes.append(outcome)
        self._save_to_db(outcome)
        return outcome

    def score_strategy(self, goal_type: str, action_type: str) -> Optional[StrategyScore]:
        """
        Compute aggregated performance score for a (goal_type, action_type) pair.
        Returns None if no outcomes recorded.
        """
        matching = [
            o for o in self._outcomes
            if o.goal_type == goal_type and o.action_type == action_type
        ]
        if not matching:
            return None

        successes = sum(1 for o in matching if o.success)
        failures = len(matching) - successes

        # Count consecutive failures from most recent
        consecutive = 0
        for o in reversed(matching):
            if not o.success:
                consecutive += 1
            else:
                break

        return StrategyScore(
            goal_type=goal_type,
            action_type=action_type,
            total_attempts=len(matching),
            successes=successes,
            failures=failures,
            success_rate=successes / len(matching),
            avg_latency_ms=sum(o.latency_ms for o in matching) / len(matching),
            avg_surprisal=sum(o.surprisal for o in matching) / len(matching),
            last_used=matching[-1].timestamp,
            consecutive_failures=consecutive
        )

    def adjustment_factor(self, goal_type: str, action_type: str) -> float:
        """
        Compute a multiplier for utility scores based on historical outcomes.

        Returns a value that adjusts the strategy's utility:
        - No history → 1.0 (no adjustment)
        - High success rate → boost (up to 1.0 + MAX_HISTORY_WEIGHT)
        - Low success rate → penalize (down to 1.0 - MAX_HISTORY_WEIGHT)
        - Consecutive failures → strong penalty
        """
        score = self.score_strategy(goal_type, action_type)
        if score is None or score.total_attempts < self.MIN_ATTEMPTS_FOR_INFLUENCE:
            return 1.0  # Not enough data to influence

        # Base adjustment from success rate (centered at 0.5)
        # success_rate=1.0 → +MAX_HISTORY_WEIGHT, success_rate=0.0 → -MAX_HISTORY_WEIGHT
        rate_adjustment = (score.success_rate - 0.5) * 2.0 * self.MAX_HISTORY_WEIGHT

        # Extra penalty for consecutive failures
        consecutive_penalty = 0.0
        if score.consecutive_failures >= self.CONSECUTIVE_FAILURE_THRESHOLD:
            consecutive_penalty = -0.2 * min(score.consecutive_failures / 5.0, 1.0)

        adjustment = 1.0 + rate_adjustment + consecutive_penalty
        return max(0.1, min(1.5, adjustment))  # Clamp between 0.1 and 1.5

    def all_scores(self, goal_type: Optional[str] = None) -> List[StrategyScore]:
        """List all strategy scores, optionally filtered by goal_type."""
        pairs = set()
        for o in self._outcomes:
            if goal_type is None or o.goal_type == goal_type:
                pairs.add((o.goal_type, o.action_type))

        scores = []
        for gt, at in sorted(pairs):
            s = self.score_strategy(gt, at)
            if s:
                scores.append(s)
        return scores

    def recent_outcomes(
        self, goal_type: str, action_type: str, limit: int = 10
    ) -> List[StrategyOutcome]:
        """Get the most recent outcomes for a strategy."""
        matching = [
            o for o in self._outcomes
            if o.goal_type == goal_type and o.action_type == action_type
        ]
        return matching[-limit:]

    def all_outcomes(self, limit: int = 500) -> List[StrategyOutcome]:
        """Return a bounded chronological snapshot for calibration/measurement."""
        return list(self._outcomes[-max(1, min(limit, 5000)):])

    def total_recorded(self) -> int:
        """Total number of recorded outcomes."""
        return len(self._outcomes)
