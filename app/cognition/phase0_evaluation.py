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

            def owner_correction_preserves_trace_link():
                from app.cognition.strategy_outcomes import StrategyOutcomeStore
                from app.cognition.training_examples import TrainingExampleStatus, TrainingExampleStore

                db_path, trace_id = self._create_trace(root, verified=False)
                store = TrainingExampleStore(
                    root / "training_examples.db",
                    trace_db_path=db_path,
                )
                candidate = store.propose_owner_correction(
                    prompt="",
                    response="Use the phone referent.",
                    skill_name="answer",
                    note="The device referent was wrong.",
                    source_trace_id=trace_id,
                    source_session_id="phase0-session",
                    action_type="answer",
                    goal_type="device_question",
                    strategy_store=StrategyOutcomeStore(str(root / "strategy.db")),
                )
                passed = (
                    candidate is not None
                    and candidate.status == TrainingExampleStatus.PENDING
                    and candidate.source_trace_id == trace_id
                    and candidate.source_session_id == "phase0-session"
                    and candidate.action_type == "answer"
                    and candidate.source_type == "owner_correction"
                    and f"source_trace:{trace_id}" in candidate.evidence
                )
                return passed, "owner correction is pending review and linked to the original durable trace", {
                    "candidate_id": candidate.candidate_id if candidate else None,
                    "source_trace_id": candidate.source_trace_id if candidate else "",
                    "status": candidate.status.value if candidate else "missing",
                }

            checks.append(self._run_check(
                "owner_correction_trace_link", "feedback", owner_correction_preserves_trace_link
            ))

            def repeated_correction_changes_strategy():
                from app.cognition.strategy_outcomes import StrategyOutcomeStore
                from app.cognition.training_examples import TrainingExampleStore

                db_path, trace_id = self._create_trace(root, verified=False)
                outcomes = StrategyOutcomeStore(str(root / "repeated_strategy.db"))
                store = TrainingExampleStore(
                    root / "repeated_candidates.db",
                    trace_db_path=db_path,
                )
                kwargs = {
                    "prompt": "Benchmark request",
                    "response": "The corrected interpretation.",
                    "skill_name": "answer",
                    "note": "The interpretation was wrong.",
                    "source_trace_id": trace_id,
                    "action_type": "answer",
                    "goal_type": "device_question",
                    "strategy_store": outcomes,
                }
                first = store.propose_owner_correction(**kwargs)
                second = store.propose_owner_correction(**kwargs)
                passed = (
                    first is not None
                    and second is not None
                    and first.strategy_update["generalized"] is False
                    and second.strategy_update["generalized"] is True
                    and second.strategy_update["adjustment_factor"] < 1.0
                )
                return passed, "one correction stayed local; repeated reviewed corrections lowered strategy utility", {
                    "first_generalized": first.strategy_update.get("generalized") if first else None,
                    "second_generalized": second.strategy_update.get("generalized") if second else None,
                    "adjustment_factor": second.strategy_update.get("adjustment_factor") if second else None,
                }

            checks.append(self._run_check(
                "repeated_correction_strategy_revision", "feedback", repeated_correction_changes_strategy
            ))

            def owner_review_gate_is_separate_from_proposal():
                from app.cognition.training_examples import TrainingExampleStatus, TrainingExampleStore

                store = TrainingExampleStore(root / "review_gate.db", trace_db_path=root / "missing-traces.db")
                candidate = store.propose_owner_correction(
                    prompt="Review this candidate",
                    response="Keep it pending until the owner decides",
                    skill_name="answer",
                )
                insufficient = store.export_approved("answer")
                rejected = store.decide(candidate.candidate_id, approved=False, note="Rejected during benchmark")
                passed = (
                    candidate is not None
                    and candidate.status == TrainingExampleStatus.PENDING
                    and insufficient.get("success") is False
                    and rejected.status == TrainingExampleStatus.REJECTED
                )
                return passed, "a candidate remains pending and export is blocked without owner approval", {
                    "candidate_status": candidate.status.value if candidate else "missing",
                    "export_success": insufficient.get("success"),
                    "final_status": rejected.status.value,
                }

            checks.append(self._run_check(
                "owner_review_export_gate", "feedback", owner_review_gate_is_separate_from_proposal
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
