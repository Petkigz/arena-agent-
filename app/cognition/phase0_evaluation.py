"""Isolated Phase 0 evaluation runner for evidence-centered behavior.

The runner measures behavior rather than module presence. Every check runs
against temporary SQLite stores and the live cognitive stores are never used.
Reports are persisted separately so pass→fail regressions are visible over
time without producing an "AGI percentage".
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from app.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Phase0Check:
    name: str
    category: str
    passed: bool
    evidence: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class Phase0Run:
    run_id: str
    created_at: str
    checks: List[Phase0Check]
    passed_count: int
    total_count: int
    regressions: List[str]
    environment: str = "isolated_deterministic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "checks": [asdict(check) for check in self.checks],
            "passed_count": self.passed_count,
            "total_count": self.total_count,
            "regressions": list(self.regressions),
            "environment": self.environment,
        }


class Phase0HistoryStore:
    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "phase0_evaluations.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS phase0_evaluation_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                report_json TEXT NOT NULL,
                passed_count INTEGER NOT NULL,
                total_count INTEGER NOT NULL
            )""")
            conn.commit()

    def save(self, run: Phase0Run) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO phase0_evaluation_runs VALUES (?, ?, ?, ?, ?)",
                (
                    run.run_id, run.created_at, json.dumps(run.to_dict()),
                    run.passed_count, run.total_count,
                ),
            )
            conn.commit()

    @staticmethod
    def _from_json(raw: str) -> Phase0Run:
        data = json.loads(raw)
        return Phase0Run(
            run_id=data["run_id"],
            created_at=data["created_at"],
            checks=[Phase0Check(**item) for item in data["checks"]],
            passed_count=int(data["passed_count"]),
            total_count=int(data["total_count"]),
            regressions=list(data.get("regressions", [])),
            environment=data.get("environment", "isolated_deterministic"),
        )

    def history(self, limit: int = 20) -> List[Phase0Run]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT report_json FROM phase0_evaluation_runs "
                "ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self._from_json(row[0]) for row in rows]

    def latest(self) -> Optional[Phase0Run]:
        history = self.history(limit=1)
        return history[0] if history else None


@contextmanager
def _temporary_trace_database(path: Path):
    """Make CognitiveTrace write only into a benchmark-owned database."""
    previous = settings.DB_PATH
    settings.DB_PATH = path
    try:
        yield path
    finally:
        settings.DB_PATH = previous


class Phase0EvaluationSuite:
    """Behavioral checks for Phase 0 and the core evidence boundary."""

    def __init__(self, history_store: Optional[Phase0HistoryStore] = None) -> None:
        self.history_store = history_store or Phase0HistoryStore()

    @staticmethod
    def _run_check(
        name: str,
        category: str,
        function: Callable[[], tuple[bool, str, Dict[str, Any]]],
    ) -> Phase0Check:
        started = time.perf_counter()
        try:
            passed, evidence, metrics = function()
        except Exception as exc:
            passed, evidence, metrics = False, f"{type(exc).__name__}: {exc}", {}
        return Phase0Check(
            name=name,
            category=category,
            passed=bool(passed),
            evidence=evidence,
            metrics=metrics,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    @staticmethod
    def _create_trace(root: Path, *, verified: bool = False) -> tuple[Path, str]:
        from app.cognition.epistemic_presentation import presentation_for_cycle
        from app.cognition.trace import CognitiveTrace

        db_path = root / "trace.db"
        presentation = presentation_for_cycle(
            goal_verified=verified,
            environment_observed=verified,
            evidence_items=["isolated benchmark observation"] if verified else ["no authoritative observation"],
            unknown=not verified,
        )
        with _temporary_trace_database(db_path):
            trace = CognitiveTrace(
                user_input="Benchmark request",
                session_id="phase0-session",
            )
            trace.finalize(
                reply=presentation.append_to("Benchmark response"),
                actions=["benchmark_probe"] if verified else [],
                latency=12.0,
                goal_verified=verified,
                epistemic_presentation=presentation.to_dict(),
            )
        return db_path, trace.trace_id

    def run(self) -> Phase0Run:
        previous = self.history_store.latest()
        checks: List[Phase0Check] = []
        with tempfile.TemporaryDirectory(
            prefix="arena_phase0_evaluation_",
            ignore_cleanup_errors=True,
        ) as directory:
            root = Path(directory)

            def unknown_preservation():
                from app.cognition.epistemic_presentation import (
                    LABEL_UNKNOWN,
                    build_epistemic_presentation,
                )
                presentation = build_epistemic_presentation(
                    evidence_state="unknown",
                    confidence_score=0.99,
                    evidence_basis=["fluent model output"],
                )
                passed = presentation.confidence_label == LABEL_UNKNOWN
                return passed, "fluent output could not upgrade UNKNOWN", {
                    "label": presentation.confidence_label,
                }

            checks.append(self._run_check(
                "epistemic_unknown_preservation", "epistemic", unknown_preservation
            ))

            def evidence_label_separation():
                from app.cognition.epistemic_presentation import (
                    LABEL_HIGH,
                    LABEL_TENTATIVE,
                    presentation_for_cycle,
                )
                direct = presentation_for_cycle(
                    goal_verified=True,
                    environment_observed=True,
                    evidence_items=["fresh observation"],
                )
                inferred = presentation_for_cycle(
                    goal_verified=True,
                    environment_observed=False,
                    evidence_items=["conversation context"],
                )
                passed = (
                    direct.confidence_label == LABEL_HIGH
                    and inferred.confidence_label == LABEL_TENTATIVE
                    and direct.evidence_state != inferred.evidence_state
                )
                return passed, "direct and inferred outcomes received different labels", {
                    "direct": direct.confidence_label,
                    "inferred": inferred.confidence_label,
                }

            checks.append(self._run_check(
                "epistemic_direct_inferred_separation", "epistemic", evidence_label_separation
            ))

            def trace_roundtrip():
                db_path, trace_id = self._create_trace(root, verified=True)
                with sqlite3.connect(db_path) as conn:
                    row = conn.execute(
                        "SELECT epistemic_presentation_json, assistant_reply "
                        "FROM cognitive_traces WHERE trace_id=?",
                        (trace_id,),
                    ).fetchone()
                presentation = json.loads(row[0]) if row else {}
                passed = bool(
                    row
                    and presentation.get("confidence_label") == "Highly confident"
                    and "Epistemic status:" in row[1]
                )
                return passed, "trace and visible response retained epistemic presentation", {
                    "trace_id": trace_id,
                    "label": presentation.get("confidence_label"),
                }

            checks.append(self._run_check(
                "epistemic_trace_roundtrip", "observability", trace_roundtrip
            ))

            def introspection_uses_trace_facts():
                from app.cognition.commitment_ledger import GroundedIntrospection
                db_path, trace_id = self._create_trace(root, verified=True)
                report = GroundedIntrospection.explain_trace(db_path, trace_id)
                facts = report.get("facts", {})
                passed = (
                    report.get("success") is True
                    and facts.get("epistemic_presentation", {}).get("confidence_label")
                    == "Highly confident"
                    and "chain-of-thought" in " ".join(report.get("unknowns", []))
                )
                return passed, "introspection cites persisted facts and states the private boundary", {
                    "has_presentation": "epistemic_presentation" in facts,
                    "unknown_count": len(report.get("unknowns", [])),
                }

            checks.append(self._run_check(
                "trace_explanation_boundary", "observability", introspection_uses_trace_facts
            ))

            def correction_preserves_and_updates_locally():
                from app.cognition.correction_learning import CorrectionHandler
                from app.cognition.strategy_outcomes import StrategyOutcomeStore
                db_path, trace_id = self._create_trace(root, verified=False)

                class FakeBeliefs:
                    def __init__(self):
                        self.calls = []

                    def ingest(self, **kwargs):
                        self.calls.append(kwargs)
                        return SimpleNamespace(
                            has_belief=False,
                            hypothesis_value=kwargs["value"],
                            evidence_count=0,
                        )

                beliefs = FakeBeliefs()
                handler = CorrectionHandler(
                    db_path,
                    belief_engine=beliefs,
                    strategy_store=StrategyOutcomeStore(str(db_path)),
                )
                result = handler.handle(
                    trace_id=trace_id,
                    correction="Use the phone referent.",
                    error_type="intent",
                    subject="current_device",
                    predicate="referent",
                    corrected_value="phone",
                    action_type="answer",
                    goal_type="device_question",
                )
                passed = (
                    result["original_trace"]["trace_id"] == trace_id
                    and result["belief_update"]["applied"] is True
                    and result["belief_update"]["authoritative_belief_unchanged"] is True
                    and result["strategy_update"]["generalized"] is False
                )
                return passed, "correction preserved trace and changed only hypothesis state", {
                    "strategy_generalized": result["strategy_update"]["generalized"],
                    "belief_calls": len(beliefs.calls),
                }

            checks.append(self._run_check(
                "correction_local_update", "feedback", correction_preserves_and_updates_locally
            ))

            def repeated_correction_changes_strategy():
                from app.cognition.correction_learning import CorrectionHandler
                from app.cognition.strategy_outcomes import StrategyOutcomeStore
                db_path, trace_id = self._create_trace(root, verified=False)
                outcomes = StrategyOutcomeStore(str(db_path))
                handler = CorrectionHandler(db_path, strategy_store=outcomes)
                kwargs = {
                    "trace_id": trace_id,
                    "correction": "The interpretation was wrong.",
                    "error_type": "intent",
                    "action_type": "answer",
                    "goal_type": "device_question",
                }
                first = handler.handle(**kwargs)
                second = handler.handle(**kwargs)
                passed = (
                    first["strategy_update"]["generalized"] is False
                    and second["strategy_update"]["generalized"] is True
                    and second["strategy_update"]["adjustment_factor"] < 1.0
                )
                return passed, "one correction stayed local; repeated corrections lowered strategy utility", {
                    "first_generalized": first["strategy_update"]["generalized"],
                    "second_generalized": second["strategy_update"]["generalized"],
                    "adjustment_factor": second["strategy_update"]["adjustment_factor"],
                }

            checks.append(self._run_check(
                "repeated_correction_strategy_revision", "feedback", repeated_correction_changes_strategy
            ))

            def usefulness_is_separate():
                from app.cognition.usefulness_feedback import UsefulnessFeedbackStore
                db_path, trace_id = self._create_trace(root, verified=True)
                store = UsefulnessFeedbackStore(db_path)
                store.record_rating(trace_id=trace_id, rating=2)
                store.record(
                    trace_id=trace_id,
                    signal_type="task_completed",
                    value=1.0,
                    source="benchmark",
                )
                summary = store.summary()
                passed = (
                    summary["samples"] == 2
                    and summary["overall"]["mean_usefulness"] == 0.625
                    and "correctness" in summary["note"]
                )
                return passed, "usefulness events aggregate separately from verification", {
                    "samples": summary["samples"],
                    "mean_usefulness": summary["overall"]["mean_usefulness"],
                }

            checks.append(self._run_check(
                "usefulness_correctness_separation", "feedback", usefulness_is_separate
            ))

        previous_by_name = {check.name: check for check in previous.checks} if previous else {}
        regressions = [
            check.name for check in checks
            if not check.passed
            and check.name in previous_by_name
            and previous_by_name[check.name].passed
        ]
        run = Phase0Run(
            run_id=f"phase0_{uuid4().hex[:12]}",
            created_at=_now(),
            checks=checks,
            passed_count=sum(1 for check in checks if check.passed),
            total_count=len(checks),
            regressions=regressions,
        )
        self.history_store.save(run)
        return run
