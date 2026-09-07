"""Owner-visible aggregation for bounded Phase 1 evidence.

This module reads durable cognitive traces, verified outcomes, grounding
metadata, route corrections, and explicit usefulness feedback.  It reports
observations and sample sufficiency separately; it does not infer causality,
quality, or general intelligence from those rows.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings


class Phase1EvidenceStore:
    """Aggregate recorded Phase 1 signals without mixing their meanings."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or settings.DB_PATH)

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        return bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone())

    @staticmethod
    def _json_object(raw: Any) -> Dict[str, Any]:
        try:
            value = json.loads(raw or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def report(self, *, limit: int = 5000) -> Dict[str, Any]:
        """Return bounded measurements from the durable trace database."""
        bounded_limit = max(1, min(int(limit), 5000))
        path = Path(self.db_path)
        if not path.exists():
            return self._empty_report("no_trace_database")

        try:
            with sqlite3.connect(self.db_path) as conn:
                if not self._table_exists(conn, "cognitive_traces"):
                    return self._empty_report("no_cognitive_trace_table")
                trace_rows = conn.execute(
                    """SELECT trace_id, goal_verified, grounding_result_json,
                              strategy_goal_type, strategy_action_type,
                              route_comparison_json, created_at
                       FROM cognitive_traces ORDER BY created_at DESC, rowid DESC LIMIT ?""",
                    (bounded_limit,),
                ).fetchall()
                feedback_rows = []
                if self._table_exists(conn, "cognitive_trace_usefulness"):
                    feedback_rows = conn.execute(
                        """SELECT usefulness, outcome_signal, retrieval_useful, trace_id
                           FROM cognitive_trace_usefulness AS feedback
                           WHERE feedback.trace_id IN (
                               SELECT trace_id FROM cognitive_traces
                               ORDER BY created_at DESC, rowid DESC LIMIT ?
                           )
                           ORDER BY created_at DESC, rowid DESC LIMIT ?""",
                        (bounded_limit, bounded_limit * 2),
                    ).fetchall()[::-1]
        except sqlite3.Error as exc:
            return self._empty_report(f"database_read_failed:{type(exc).__name__}")

        grounded_traces = 0
        grounding_recorded = 0
        unsupported_claims = 0
        unsupported_claim_traces = 0
        grounding_statuses: Counter[str] = Counter()
        verified_outcomes = 0
        strategy_rows: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"attempts": 0, "verified_successes": 0}
        )
        correction_outcomes: Counter[str] = Counter()
        correction_count = 0

        for row in trace_rows:
            goal_verified = bool(row[1])
            verified_outcomes += int(goal_verified)
            grounding = self._json_object(row[2])
            status = str(grounding.get("status") or "unrecorded")
            if grounding:
                grounding_recorded += 1
                grounded_traces += int(status in {"supported", "verified"})
                grounding_statuses[status] += 1
                claims = grounding.get("unsupported_claims") or []
                unsupported_claims += len(claims)
                unsupported_claim_traces += int(bool(claims))
            strategy_key = "|".join((str(row[3] or ""), str(row[4] or ""))).strip("|")
            if strategy_key:
                strategy_rows[strategy_key]["attempts"] += 1
                strategy_rows[strategy_key]["verified_successes"] += int(goal_verified)
            route = self._json_object(row[5])
            if route.get("correction_applied"):
                correction_count += 1
                correction_outcomes[str(route.get("correction_outcome") or "unknown")] += 1

        # Audit events remain visible, but repeat ratings of the same answer
        # are one independent response sample, as in StrategyUsefulnessStore.
        latest_feedback = {row[3]: row for row in feedback_rows}
        rated_trace_count = len(latest_feedback)
        sample_usefulness = sum(
            1.0 if row[0] == "helpful" else 0.5 if row[0] == "partially_helpful" else 0.0
            for row in latest_feedback.values()
        )
        helpful = sum(1 for row in feedback_rows if row[0] == "helpful")
        partial = sum(1 for row in feedback_rows if row[0] == "partially_helpful")
        not_helpful = sum(1 for row in feedback_rows if row[0] == "not_helpful")
        usefulness_count = helpful + partial + not_helpful
        retrieval_known = sum(row[2] is not None for row in feedback_rows)
        retrieval_useful = sum(bool(row[2]) for row in feedback_rows if row[2] is not None)

        for value in strategy_rows.values():
            value["verified_success_rate"] = round(
                value["verified_successes"] / value["attempts"], 4
            ) if value["attempts"] else None

        verified_rate = round(verified_outcomes / len(trace_rows), 4) if trace_rows else None
        unsupported_rate = round(
            unsupported_claim_traces / grounding_recorded, 4
        ) if grounding_recorded else None
        usefulness_rate = round(
            (helpful + 0.5 * partial) / usefulness_count, 4
        ) if usefulness_count else None
        report = {
            "status": "measured" if trace_rows else "insufficient_evidence",
            "evidence_sufficient": len(trace_rows) >= 2,
            "trace_count": len(trace_rows),
            "verified_outcome_count": verified_outcomes,
            "verified_outcome_rate": verified_rate,
            "grounded_trace_count": grounded_traces,
            "grounding_recorded_trace_count": grounding_recorded,
            "grounding_status_counts": dict(sorted(grounding_statuses.items())),
            "unsupported_claim_count": unsupported_claims,
            "unsupported_claim_trace_count": unsupported_claim_traces,
            "unsupported_claim_trace_rate": unsupported_rate,
            "correction_applied_count": correction_count,
            "correction_outcome_counts": dict(sorted(correction_outcomes.items())),
            "usefulness_feedback_count": usefulness_count,
            "usefulness_counts": {
                "helpful": helpful,
                "partially_helpful": partial,
                "not_helpful": not_helpful,
            },
            "usefulness_rate": usefulness_rate,
            "retrieval_feedback_count": retrieval_known,
            "retrieval_useful_count": retrieval_useful,
            "rated_trace_count": rated_trace_count,
            "usefulness_sample_rate": round(sample_usefulness / rated_trace_count, 4) if rated_trace_count else None,
            "usefulness_evidence_sufficient": rated_trace_count >= 2,
            "window": {"order": "most_recent", "trace_limit": bounded_limit},
            "strategies": dict(sorted(strategy_rows.items())),
            "note": (
                "These are recent recorded trace observations; feedback uses the same trace cohort. "
                "Usefulness event volume is separate from independent rated traces. Rates are descriptive; "
                "they do not establish causality, generalization, or an AGI score."
            ),
        }
        return report

    @staticmethod
    def _empty_report(reason: str) -> Dict[str, Any]:
        return {
            "status": "insufficient_evidence",
            "evidence_sufficient": False,
            "trace_count": 0,
            "verified_outcome_count": 0,
            "verified_outcome_rate": None,
            "grounded_trace_count": 0,
            "grounding_recorded_trace_count": 0,
            "grounding_status_counts": {},
            "unsupported_claim_count": 0,
            "unsupported_claim_trace_count": 0,
            "unsupported_claim_trace_rate": None,
            "correction_applied_count": 0,
            "correction_outcome_counts": {},
            "usefulness_feedback_count": 0,
            "usefulness_counts": {
                "helpful": 0,
                "partially_helpful": 0,
                "not_helpful": 0,
            },
            "usefulness_rate": None,
            "retrieval_feedback_count": 0,
            "retrieval_useful_count": 0,
            "rated_trace_count": 0,
            "usefulness_sample_rate": None,
            "usefulness_evidence_sufficient": False,
            "strategies": {},
            "note": (
                f"No Phase 1 trace evidence was available ({reason}); absence is "
                "unmeasured, not evidence of failure or usefulness."
            ),
        }
