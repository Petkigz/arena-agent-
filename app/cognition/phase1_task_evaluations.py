"""Append-only owner-recorded evaluations for Phase 1 held-out tasks.

A task evaluation links an owner-observed outcome and usefulness signal to a
durable cognitive trace.  The store is measurement-only: it does not rewrite
trace truth, train a model, authorize an action, or convert paired results into
a causal improvement claim.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.submissions import submission_record_id, require_same_submission

_ALLOWED_OUTCOMES = {"success", "failure", "unknown"}
_ALLOWED_USEFULNESS = {"helpful", "partially_helpful", "not_helpful", "unknown"}
_ALLOWED_SPLITS = {"held_out", "contract"}
_ALLOWED_CONDITIONS = {"single", "baseline", "adapted"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Phase1TaskEvaluation:
    evaluation_id: str
    task_key: str
    split: str
    condition: str
    trace_id: str
    observed_outcome: str
    usefulness: str
    correction_received: bool
    strategy_goal_type: str
    strategy_action_type: str
    route: str
    evidence_ids: List[str] = field(default_factory=list)
    note: str = ""
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Phase1TaskEvaluationStore:
    """Store explicit held-out task observations and descriptive comparisons."""

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        *,
        trace_db_path: Optional[str | Path] = None,
    ) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "phase1_task_evaluations.db"))
        self.trace_db_path = str(trace_db_path or settings.DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS phase1_task_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    task_key TEXT NOT NULL,
                    split TEXT NOT NULL,
                    condition_name TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    observed_outcome TEXT NOT NULL,
                    usefulness TEXT NOT NULL,
                    correction_received INTEGER NOT NULL DEFAULT 0,
                    strategy_goal_type TEXT NOT NULL DEFAULT '',
                    strategy_action_type TEXT NOT NULL DEFAULT '',
                    route TEXT NOT NULL DEFAULT '',
                    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_phase1_eval_task "
                "ON phase1_task_evaluations(task_key, condition_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_phase1_eval_created "
                "ON phase1_task_evaluations(created_at)"
            )
            conn.commit()

    def _trace_context(self, trace_id: str) -> Optional[Dict[str, str]]:
        path = Path(self.trace_db_path)
        if not path.exists():
            return None
        try:
            with sqlite3.connect(path) as conn:
                columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(cognitive_traces)")
                }
                if "trace_id" not in columns:
                    return None
                fields = ("strategy_goal_type", "strategy_action_type", "route_comparison_json")
                selected = ", ".join(field if field in columns else "''" for field in fields)
                row = conn.execute(
                    f"SELECT {selected} FROM cognitive_traces WHERE trace_id=?", (trace_id,),
                ).fetchone()
                if row is None:
                    return None
                context = dict(zip(fields, (str(value or "") for value in row)))
                try:
                    comparison = json.loads(context.pop("route_comparison_json") or "{}")
                except (TypeError, ValueError):
                    comparison = {}
                selected_route = comparison.get("selected_route") if isinstance(comparison, dict) else None
                context["route"] = selected_route if isinstance(selected_route, str) else ""
                return context
        except sqlite3.Error:
            return None

    def record(
        self,
        *,
        task_key: str,
        trace_id: str,
        observed_outcome: str,
        usefulness: str = "unknown",
        split: str = "held_out",
        condition: str = "single",
        correction_received: bool = False,
        strategy_goal_type: str = "",
        strategy_action_type: str = "",
        route: str = "",
        evidence_ids: Optional[List[str]] = None,
        note: str = "",
        created_at: Optional[str] = None,
        submission_id: Optional[str] = None,
    ) -> Phase1TaskEvaluation:
        task_key = str(task_key or "").strip()[:200]
        trace_id = str(trace_id or "").strip()[:200]
        split = str(split or "").strip().lower()
        condition = str(condition or "").strip().lower()
        observed_outcome = str(observed_outcome or "").strip().lower()
        usefulness = str(usefulness or "unknown").strip().lower()
        if len(task_key) < 3:
            raise ValueError("task_key must contain at least 3 characters")
        if split not in _ALLOWED_SPLITS:
            raise ValueError("split must be held_out or contract")
        if condition not in _ALLOWED_CONDITIONS:
            raise ValueError("condition must be single, baseline, or adapted")
        if observed_outcome not in _ALLOWED_OUTCOMES:
            raise ValueError("observed_outcome must be success, failure, or unknown")
        if usefulness not in _ALLOWED_USEFULNESS:
            raise ValueError(
                "usefulness must be helpful, partially_helpful, not_helpful, or unknown"
            )
        trace_context = self._trace_context(trace_id) if trace_id else None
        if trace_context is None:
            raise KeyError(f"Trace not found: {trace_id}")
        # The web client need only send the exact trace. Fill missing strategy
        # metadata from its persisted facts, never from a guessed current task.
        strategy_goal_type = strategy_goal_type or trace_context["strategy_goal_type"]
        strategy_action_type = strategy_action_type or trace_context["strategy_action_type"]
        route = route or trace_context["route"]
        evidence = [str(item).strip()[:200] for item in (evidence_ids or []) if str(item).strip()]
        evaluation = Phase1TaskEvaluation(
            evaluation_id=submission_record_id("phase1_eval_", submission_id),
            task_key=task_key,
            split=split,
            condition=condition,
            trace_id=trace_id,
            observed_outcome=observed_outcome,
            usefulness=usefulness,
            correction_received=bool(correction_received),
            strategy_goal_type=str(strategy_goal_type or "")[:100],
            strategy_action_type=str(strategy_action_type or "")[:100],
            route=str(route or "")[:100],
            evidence_ids=evidence[:20],
            note=str(note or "")[:1000],
            created_at=str(created_at or _now()),
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM phase1_task_evaluations WHERE evaluation_id=?",
                (evaluation.evaluation_id,),
            ).fetchone()
            if existing is not None:
                receipt = self._from_row(existing)
                require_same_submission(receipt.to_dict(), evaluation.to_dict())
                return receipt
            conn.execute(
                """INSERT INTO phase1_task_evaluations
                (evaluation_id, task_key, split, condition_name, trace_id,
                 observed_outcome, usefulness, correction_received,
                 strategy_goal_type, strategy_action_type, route,
                 evidence_ids_json, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    evaluation.evaluation_id,
                    evaluation.task_key,
                    evaluation.split,
                    evaluation.condition,
                    evaluation.trace_id,
                    evaluation.observed_outcome,
                    evaluation.usefulness,
                    int(evaluation.correction_received),
                    evaluation.strategy_goal_type,
                    evaluation.strategy_action_type,
                    evaluation.route,
                    json.dumps(evaluation.evidence_ids),
                    evaluation.note,
                    evaluation.created_at,
                ),
            )
            conn.commit()
        return evaluation

    def history(
        self, *, limit: int = 5000, split: Optional[str] = None, trace_id: Optional[str] = None,
    ) -> List[Phase1TaskEvaluation]:
        bounded_limit = max(1, min(int(limit), 5000))
        query = """SELECT evaluation_id, task_key, split, condition_name,
                          trace_id, observed_outcome, usefulness,
                          correction_received, strategy_goal_type,
                          strategy_action_type, route, evidence_ids_json,
                          note, created_at
                   FROM phase1_task_evaluations"""
        params: List[Any] = []
        filters = []
        if split is not None:
            if split not in _ALLOWED_SPLITS:
                raise ValueError("split must be held_out or contract")
            filters.append("split=?")
            params.append(split)
        if trace_id is not None:
            filters.append("trace_id=?")
            params.append(str(trace_id))
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(bounded_limit)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row) -> Phase1TaskEvaluation:
        return Phase1TaskEvaluation(
            evaluation_id=row[0], task_key=row[1], split=row[2], condition=row[3],
            trace_id=row[4], observed_outcome=row[5], usefulness=row[6],
            correction_received=bool(row[7]), strategy_goal_type=row[8],
            strategy_action_type=row[9], route=row[10],
            evidence_ids=list(json.loads(row[11] or "[]")), note=row[12], created_at=row[13],
        )

    def report(
        self, *, limit: int = 5000, split: str = "held_out", trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        evaluations = self.history(limit=limit, split=split, trace_id=trace_id)
        outcome_counts = Counter(item.observed_outcome for item in evaluations)
        usefulness_counts = Counter(
            item.usefulness for item in evaluations if item.usefulness != "unknown"
        )
        known_outcomes = sum(
            item.observed_outcome in {"success", "failure"} for item in evaluations
        )
        known_usefulness = sum(
            item.usefulness in {"helpful", "partially_helpful", "not_helpful"}
            for item in evaluations
        )
        strategy_groups: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"evaluations": 0, "successes": 0}
        )
        for item in evaluations:
            strategy = "|".join((item.strategy_goal_type, item.strategy_action_type)).strip("|")
            if strategy:
                strategy_groups[strategy]["evaluations"] += 1
                strategy_groups[strategy]["successes"] += int(item.observed_outcome == "success")
        for group in strategy_groups.values():
            group["success_rate"] = round(
                group["successes"] / group["evaluations"], 4
            ) if group["evaluations"] else 0.0

        by_task: Dict[str, Dict[str, Phase1TaskEvaluation]] = defaultdict(dict)
        for item in evaluations:
            if item.condition in {"baseline", "adapted"}:
                by_task[item.task_key][item.condition] = item
        paired = []
        for task_key, conditions in sorted(by_task.items()):
            if "baseline" not in conditions or "adapted" not in conditions:
                continue
            baseline = conditions["baseline"]
            adapted = conditions["adapted"]
            if baseline.observed_outcome not in {"success", "failure"} or adapted.observed_outcome not in {"success", "failure"}:
                continue
            paired.append({
                "task_key": task_key,
                "baseline_outcome": baseline.observed_outcome,
                "adapted_outcome": adapted.observed_outcome,
                "observed_change": (
                    "improved" if baseline.observed_outcome == "failure" and adapted.observed_outcome == "success"
                    else "regressed" if baseline.observed_outcome == "success" and adapted.observed_outcome == "failure"
                    else "unchanged"
                ),
            })
        improved = sum(item["observed_change"] == "improved" for item in paired)
        regressed = sum(item["observed_change"] == "regressed" for item in paired)
        return {
            "status": "measured" if evaluations else "insufficient_evidence",
            "split": split,
            "evaluation_count": len(evaluations),
            "evidence_sufficient": len(evaluations) >= 2,
            "known_outcome_count": known_outcomes,
            "outcome_counts": dict(sorted(outcome_counts.items())),
            "outcome_success_rate": round(
                outcome_counts["success"] / known_outcomes, 4
            ) if known_outcomes else None,
            "known_usefulness_count": known_usefulness,
            "usefulness_counts": dict(sorted(usefulness_counts.items())),
            "usefulness_rate": round(
                (usefulness_counts["helpful"] + 0.5 * usefulness_counts["partially_helpful"])
                / known_usefulness,
                4,
            ) if known_usefulness else None,
            "correction_received_count": sum(item.correction_received for item in evaluations),
            "strategies": dict(sorted(strategy_groups.items())),
            "paired_comparison_count": len(paired),
            "paired_improved_count": improved,
            "paired_regressed_count": regressed,
            "paired_observations": paired[:100],
            "note": (
                "Outcomes and paired changes are owner-recorded observations. "
                "They are descriptive and do not establish causality, generalization, "
                "or an AGI score."
            ),
        }
