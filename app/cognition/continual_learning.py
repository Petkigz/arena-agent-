"""Regression-gated continual-learning cycles (F3 orchestration).

Training examples are proposed, redacted, and owner-approved — but nothing
orchestrates a full training cycle or proves the trained model did not get
WORSE. This module adds the missing loop discipline:

  1. plan_training(): snapshot the approved dataset readiness and record a
     BASELINE benchmark run (before).
  2. The owner trains (existing train_lora path — owner-authorized as always).
  3. evaluate(): run the benchmark again (after) and apply the regression
     gate: every check that passed at baseline must still pass, and the total
     must not shrink. Any regression fails the cycle honestly, check by check.

Nothing here trains anything by itself; the gate only measures and reports.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TrainingCycle:
    cycle_id: str
    status: str  # planned | evaluated_pass | evaluated_fail | abandoned
    created_at: str
    dataset_summary: Dict[str, Any]
    before_benchmark: Optional[Dict[str, Any]] = None
    after_benchmark: Optional[Dict[str, Any]] = None
    gate: Optional[Dict[str, Any]] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _benchmark_to_dict(run: Any) -> Dict[str, Any]:
    if isinstance(run, dict):
        return run
    checks = getattr(run, "checks", []) or []
    return {
        "passed_count": getattr(run, "passed_count", sum(1 for c in checks if getattr(c, "passed", False))),
        "total_count": getattr(run, "total_count", len(checks)),
        "checks": [
            {"name": getattr(c, "name", ""), "passed": bool(getattr(c, "passed", False))}
            for c in checks
        ],
    }


def _run_checks(run_dict: Dict[str, Any]) -> Dict[str, bool]:
    return {c["name"]: bool(c["passed"]) for c in run_dict.get("checks", [])}


class ContinualLearningStore:
    """Persistent training cycles with baseline and post-training benchmarks."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "continual_learning.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS training_cycles (
                cycle_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                dataset_summary_json TEXT NOT NULL,
                before_benchmark_json TEXT,
                after_benchmark_json TEXT,
                gate_json TEXT,
                note TEXT NOT NULL DEFAULT ''
            )""")
            conn.commit()

    def _row(self, row: sqlite3.Row) -> TrainingCycle:
        return TrainingCycle(
            cycle_id=row[0], status=row[1], created_at=row[2],
            dataset_summary=json.loads(row[3]),
            before_benchmark=json.loads(row[4]) if row[4] else None,
            after_benchmark=json.loads(row[5]) if row[5] else None,
            gate=json.loads(row[6]) if row[6] else None,
            note=row[7] or "",
        )

    def create(self, dataset_summary: Dict[str, Any],
               before_benchmark: Optional[Dict[str, Any]], note: str = "") -> TrainingCycle:
        cycle = TrainingCycle(
            cycle_id=f"tc_{uuid4().hex[:14]}", status="planned", created_at=_now(),
            dataset_summary=dataset_summary, before_benchmark=before_benchmark, note=note,
        )
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO training_cycles VALUES (?,?,?,?,?,?,?,?)",
                (cycle.cycle_id, cycle.status, cycle.created_at,
                 json.dumps(cycle.dataset_summary, default=str),
                 json.dumps(cycle.before_benchmark) if cycle.before_benchmark else None,
                 None, None, cycle.note),
            )
            conn.commit()
        return cycle

    def get(self, cycle_id: str) -> Optional[TrainingCycle]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM training_cycles WHERE cycle_id=?", (cycle_id,)
            ).fetchone()
        return self._row(row) if row else None

    def list(self, limit: int = 25) -> List[TrainingCycle]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM training_cycles ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [self._row(r) for r in rows]

    def record_evaluation(self, cycle_id: str, after_benchmark: Dict[str, Any],
                          gate: Dict[str, Any], status: str) -> TrainingCycle:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE training_cycles SET after_benchmark_json=?, gate_json=?, status=? WHERE cycle_id=?",
                (json.dumps(after_benchmark), json.dumps(gate), status, cycle_id),
            )
            conn.commit()
        result = self.get(cycle_id)
        assert result is not None
        return result


class ContinualLearningCycle:
    """Plan → (owner trains) → evaluate with a hard regression gate."""

    def __init__(self, store: Optional[ContinualLearningStore] = None,
                 benchmark_runner: Optional[Callable[[], Any]] = None,
                 training_examples: Optional[Any] = None) -> None:
        self.store = store or ContinualLearningStore()
        self._benchmark_runner = benchmark_runner
        self._training_examples = training_examples

    def _run_benchmark(self) -> Any:
        if self._benchmark_runner is not None:
            return self._benchmark_runner()
        from app.cognition.intelligence_benchmark import IntelligenceBenchmarkSuite
        return IntelligenceBenchmarkSuite().run()

    def _dataset_readiness(self) -> Dict[str, Any]:
        if self._training_examples is None:
            from app.cognition.training_examples import TrainingExampleStore
            self._training_examples = TrainingExampleStore()
        store = self._training_examples
        counts: Dict[str, int] = {"pending": 0, "approved": 0, "rejected": 0}
        per_skill: Dict[str, int] = {}
        try:
            for candidate in store.list(status=None) if hasattr(store, "list") else []:
                status = str(getattr(candidate, "status", "")).split(".")[-1]
                counts[status] = counts.get(status, 0) + 1
                if status == "approved":
                    skill = getattr(candidate, "skill_name", "?")
                    per_skill[skill] = per_skill.get(skill, 0) + 1
        except Exception as exc:
            app_logger.warning(f"Dataset readiness scan failed: {exc}")
        min_export = getattr(type(store), "MIN_APPROVED_FOR_EXPORT", 5) if store else 5
        exportable = {skill: n for skill, n in per_skill.items() if n >= min_export}
        return {
            "counts": counts,
            "approved_per_skill": per_skill,
            "export_ready_skills": sorted(exportable),
            "min_approved_for_export": min_export,
        }

    def plan_training(self, *, run_baseline: bool = True, note: str = "") -> Dict[str, Any]:
        """Record a cycle plan with a baseline benchmark run.

        Planning authorizes NOTHING — training remains a separate,
        owner-authorized action through the existing paths.
        """
        dataset = self._dataset_readiness()
        baseline = None
        baseline_error = None
        if run_baseline:
            try:
                baseline = _benchmark_to_dict(self._run_benchmark())
            except Exception as exc:
                baseline_error = str(exc)
        cycle = self.store.create(dataset, baseline, note=note)
        audit_logger.info("Continual-learning cycle planned: %s", cycle.cycle_id)
        return {
            "success": True, "cycle": cycle.to_dict(),
            "baseline_error": baseline_error,
            "note": "Plan only. Train via the owner-authorized path, then call evaluate for the regression gate.",
        }

    def evaluate(self, cycle_id: str) -> Dict[str, Any]:
        """Run the post-training benchmark and apply the regression gate."""
        cycle = self.store.get(cycle_id)
        if cycle is None:
            return {"success": False, "error": "Cycle not found"}
        if cycle.status != "planned":
            return {"success": False, "error": f"Cycle already {cycle.status}"}
        if cycle.before_benchmark is None:
            return {"success": False, "error": "Cycle has no baseline benchmark; re-plan with one"}
        try:
            after = _benchmark_to_dict(self._run_benchmark())
        except Exception as exc:
            return {"success": False, "error": f"Post-training benchmark failed: {exc}"}

        before_checks = _run_checks(cycle.before_benchmark)
        after_checks = _run_checks(after)
        regressed = [name for name, passed in before_checks.items() if passed and not after_checks.get(name, False)]
        gained = [name for name, passed in after_checks.items() if passed and not before_checks.get(name, False)]
        before_total = int(cycle.before_benchmark.get("total_count", len(before_checks)))
        after_total = int(after.get("total_count", len(after_checks)))
        passed = (
            not regressed
            and after_total >= before_total
            and int(after.get("passed_count", 0)) >= int(cycle.before_benchmark.get("passed_count", 0))
        )
        gate = {
            "verdict": "pass" if passed else "fail",
            "regressed_checks": regressed,
            "newly_passing_checks": gained,
            "before_passed": cycle.before_benchmark.get("passed_count"),
            "after_passed": after.get("passed_count"),
            "before_total": before_total,
            "after_total": after_total,
        }
        status = "evaluated_pass" if passed else "evaluated_fail"
        updated = self.store.record_evaluation(cycle_id, after, gate, status)
        audit_logger.warning(
            "Continual-learning regression gate %s for %s (regressed=%s)",
            gate["verdict"], cycle_id, regressed or "none",
        )
        return {
            "success": True, "cycle": updated.to_dict(),
            "gate": gate,
            "note": "PASS releases nothing automatically; the owner decides whether to keep the trained model." if passed
            else "FAIL: the trained model regressed — keep the previous model.",
        }

    def status(self) -> Dict[str, Any]:
        cycles = self.store.list(limit=10)
        return {
            "success": True,
            "dataset": self._dataset_readiness(),
            "recent_cycles": [c.to_dict() for c in cycles],
        }


# Module-level singleton.
continual_learning = ContinualLearningCycle()
