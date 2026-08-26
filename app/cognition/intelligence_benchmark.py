"""Isolated longitudinal benchmarks for learning, transfer, and control integrity.

These checks measure deterministic behavior over time. They do not produce an
"AGI percentage" and never mutate the live cognitive stores.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
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
class BenchmarkCheck:
    name: str
    category: str
    passed: bool
    evidence: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass
class BenchmarkRun:
    run_id: str
    created_at: str
    checks: List[BenchmarkCheck]
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
            "regressions": self.regressions,
            "environment": self.environment,
        }


class BenchmarkHistoryStore:
    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "intelligence_benchmarks.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS intelligence_benchmark_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                report_json TEXT NOT NULL,
                passed_count INTEGER NOT NULL,
                total_count INTEGER NOT NULL
            )""")
            conn.commit()

    def save(self, run: BenchmarkRun) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO intelligence_benchmark_runs VALUES (?, ?, ?, ?, ?)",
                (
                    run.run_id,
                    run.created_at,
                    json.dumps(run.to_dict()),
                    run.passed_count,
                    run.total_count,
                ),
            )
            conn.commit()

    def latest(self) -> Optional[BenchmarkRun]:
        runs = self.history(limit=1)
        return runs[0] if runs else None

    def history(self, limit: int = 20) -> List[BenchmarkRun]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT report_json FROM intelligence_benchmark_runs "
                "ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        results = []
        for row in rows:
            data = json.loads(row[0])
            results.append(BenchmarkRun(
                run_id=data["run_id"],
                created_at=data["created_at"],
                checks=[BenchmarkCheck(**item) for item in data["checks"]],
                passed_count=data["passed_count"],
                total_count=data["total_count"],
                regressions=list(data.get("regressions", [])),
                environment=data.get("environment", "isolated_deterministic"),
            ))
        return results


class IntelligenceBenchmarkSuite:
    def __init__(self, history_store: Optional[BenchmarkHistoryStore] = None) -> None:
        self.history_store = history_store or BenchmarkHistoryStore()

    @staticmethod
    def _run_check(
        name: str,
        category: str,
        function: Callable[[], tuple[bool, str, Dict[str, Any]]],
    ) -> BenchmarkCheck:
        started = time.perf_counter()
        try:
            passed, evidence, metrics = function()
        except Exception as exc:
            passed, evidence, metrics = False, f"{type(exc).__name__}: {exc}", {}
        return BenchmarkCheck(
            name=name,
            category=category,
            passed=bool(passed),
            evidence=evidence,
            metrics=metrics,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def run(self) -> BenchmarkRun:
        previous = self.history_store.latest()
        checks: List[BenchmarkCheck] = []
        with tempfile.TemporaryDirectory(prefix="arena_intelligence_benchmark_") as directory:
            root = Path(directory)

            def memory_retrieval():
                from app.cognition.memory import MemoryStore
                store = MemoryStore(root / "memory.db")
                relevant = store.add(
                    "episodic",
                    "Chrome crashed while opening the dashboard",
                    tags=("chrome", "dashboard"),
                )
                store.add("semantic", "Water the garden each morning", importance=1.0)
                results = store.search("browser failure dashboard", limit=3)
                rank = next(
                    (index + 1 for index, item in enumerate(results) if item.memory_id == relevant.memory_id),
                    None,
                )
                return rank == 1, f"paraphrased relevant memory rank={rank}", {"rank": rank}

            checks.append(self._run_check("memory_paraphrase_retrieval", "memory", memory_retrieval))

            def associative_recall():
                from app.cognition.memory import MemoryStore
                from app.cognition.associative_memory import HashedNGramEmbedder, MemoryVectorIndex
                store = MemoryStore(root / "assoc-memory.db")
                index = MemoryVectorIndex(root / "assoc-vectors.npz", embedder=HashedNGramEmbedder())
                assert store.enable_associative(index=index) is True
                target = store.add(
                    "episodic",
                    "The budget discussion with the bank ended without agreement",
                    tags=("finance", "bank"),
                )
                for filler in (
                    "Water the garden each morning",
                    "Compress the weekly backups on Friday",
                    "Chrome crashed while opening the dashboard",
                ):
                    store.add("semantic", filler, importance=1.0)
                # Zero shared tokens with the query: pure associative recall.
                results = store.search("money meeting at the funds office", limit=3)
                rank = next(
                    (i + 1 for i, item in enumerate(results) if item.memory_id == target.memory_id),
                    None,
                )
                return rank is not None and rank <= 2, \
                    f"zero-overlap paraphrase recalled at rank={rank}", {"rank": rank}

            checks.append(self._run_check("associative_paraphrase_recall", "memory", associative_recall))

            def working_memory_attention():
                from app.cognition.working_memory import WorkingMemory
                wm = WorkingMemory(capacity=5, half_life_seconds=60)
                wm.set_goal("fix the login crash")
                # Fill to capacity with a mix of on-topic and noise.
                wm.encode("login page crash log attached", kind="observation", source="bench", salience=0.5)
                wm.encode("weather is nice today", kind="observation", source="bench", salience=0.3)
                for i in range(6):
                    wm.encode(f"unrelated memo number {i}", kind="observation", source="bench", salience=0.2)
                snapshot = wm.snapshot()
                ok_capacity = len(snapshot) <= 5
                ok_priority = snapshot and "login" in snapshot[0]["content"]
                ok_provenance = all(item["source"] for item in snapshot)
                ok_gate = wm.encode("qqq www zzz", kind="observation", source="bench", salience=0.02)["accepted"] is False
                passed = ok_capacity and ok_priority and ok_provenance and ok_gate
                return passed, \
                    f"capacity={ok_capacity} priority={ok_priority} provenance={ok_provenance} gate={ok_gate}", \
                    {"kept": len(snapshot), "top": snapshot[0]["content"][:40] if snapshot else None}

            checks.append(self._run_check("working_memory_attention", "memory", working_memory_attention))

            def learned_outcome_statistics():
                from app.cognition.action_outcomes import ActionOutcomeStore
                store = ActionOutcomeStore(root / "outcomes.db")
                for i in range(8):
                    store.record("move_file", {"i": i}, "verified_success", execution_id=f"ok{i}")
                for i in range(2):
                    store.record("move_file", {"i": i}, "verified_failure", execution_id=f"bad{i}")
                estimate = store.estimate("move_file", refresh=True)
                ok_sufficient = estimate.evidence_sufficient and estimate.n == 10
                ok_rate = abs(estimate.smoothed_success_rate - 0.8) < 1e-6
                ok_interval = 0.0 < estimate.wilson_low < 0.8 < estimate.wilson_high < 1.0
                thin = store.estimate("never_seen_action", refresh=True)
                ok_thin = (not thin.evidence_sufficient) and learned_is_none(store)
                passed = ok_sufficient and ok_rate and ok_interval and ok_thin
                return passed, \
                    f"sufficient={ok_sufficient} rate={ok_rate} interval={ok_interval} thin_honest={ok_thin}", \
                    {"smoothed": estimate.smoothed_success_rate, "wilson": [estimate.wilson_low, estimate.wilson_high]}

            def learned_is_none(store):
                return store.estimate("never_seen_action", refresh=True).evidence_sufficient is False

            checks.append(self._run_check("learned_outcome_statistics", "learning", learned_outcome_statistics))

            def skill_induction_from_experience():
                import sqlite3 as _sql
                from app.cognition.skill_induction import SkillInductionEngine
                plans_db = root / "induction_plans.db"
                with _sql.connect(plans_db) as conn:
                    conn.execute("""CREATE TABLE IF NOT EXISTS execution_plans (
                        plan_id TEXT PRIMARY KEY, goal_id TEXT, goal_title TEXT, steps TEXT,
                        status TEXT, progress REAL, started_at TEXT, completed_at TEXT,
                        outcome_summary TEXT, lessons_learned TEXT)""")
                    import json as _json
                    for i in range(3):
                        recipe = [
                            {"action_type": "copy_file_verified", "payload": {"source": f"s{i}", "destination": "/d"}, "status": "completed"},
                            {"action_type": "compress_files", "payload": {"archive": "/a.zip"}, "status": "completed"},
                        ]
                        conn.execute("INSERT INTO execution_plans VALUES (?,?,?,?,?,?,?,?,?,?)",
                                     (f"bp{i}", "g", "g", _json.dumps(recipe), "completed", 1.0, None, None, None, None))
                    conn.commit()
                engine = SkillInductionEngine(root / "induced.db")
                engine.scan(plans_db)
                candidates = engine.list("pending")
                ok_found = len(candidates) == 1 and candidates[0].action_sequence == ["copy_file_verified", "compress_files"]
                ok_templated = ok_found and candidates[0].payload_template[0]["source"] == "{{source}}" \
                    and candidates[0].payload_template[0]["destination"] == "/d"
                ok_evidence = ok_found and candidates[0].occurrences == 3
                passed = ok_found and ok_templated and ok_evidence
                return passed, \
                    f"found={ok_found} templated={ok_templated} evidence={ok_evidence}", \
                    {"candidate": candidates[0].skill_name if candidates else None}

            checks.append(self._run_check("skill_induction_from_experience", "learning", skill_induction_from_experience))

            def owner_charter_informs_goals():
                import app.cognition.owner_charter as oc
                store = oc.OwnerCharterStore(root / "charter")
                monkey_store = store  # local, isolated charter
                original_store = oc.owner_charter_store
                oc.owner_charter_store = monkey_store
                try:
                    store.update({"priorities": ["backup archive", "server maintenance"]})
                    aligned = oc.charter_priority_alignment("run the server maintenance and backup archive")
                    unaligned = oc.charter_priority_alignment("cook lunch")
                    ok_align = aligned is not None and aligned > 0.5 and unaligned == 0.0
                    charter = store.get()
                    ok_versioned = charter.revision == 1 and len(charter.content_digest) == 64
                    ok_history = len(store.history()) == 1
                    # Owner model counts decisions with Wilson bounds.
                    from app.cognition.owner_model import OwnerModelStore
                    model = OwnerModelStore(root / "om.db")
                    for i in range(4):
                        model.record_action_preference("create_backup", True, f"e{i}")
                    report = model.report()
                    pref = next((p for p in report["counted_preferences"]
                                 if p["action_type"] == "create_backup"), None)
                    ok_model = pref is not None and pref["n"] == 4 and pref["approval_rate"] == 1.0 \
                        and pref["wilson_low"] > 0.4
                    passed = ok_align and ok_versioned and ok_history and ok_model
                    return passed, \
                        f"align={ok_align} versioned={ok_versioned} history={ok_history} model={ok_model}", \
                        {"aligned": aligned, "wilson_low": pref["wilson_low"] if pref else None}
                finally:
                    oc.owner_charter_store = original_store

            checks.append(self._run_check("owner_charter_informs_goals", "control", owner_charter_informs_goals))

            def learning_progress_targets_growth():
                from app.cognition.action_outcomes import ActionOutcomeStore
                from app.cognition.learning_progress import LearningProgressTracker
                store = ActionOutcomeStore(root / "lp_outcomes.db")
                counter = 0
                for _ in range(4):
                    counter += 1; store.record("browser_upload", {"i": counter}, "verified_failure", execution_id=f"lp{counter}")
                for _ in range(6):
                    counter += 1; store.record("browser_upload", {"i": counter}, "verified_success", execution_id=f"lp{counter}")
                for _ in range(10):
                    counter += 1; store.record("search_files", {"i": counter}, "verified_success", execution_id=f"lp{counter}")
                tracker = LearningProgressTracker(store.db_path)
                upload = tracker.progress_for("browser_upload")
                mastered = tracker.progress_for("search_files")
                ok_improving = upload.status == "improving" and upload.learning_value > 0.2
                ok_mastered = mastered.status == "mastered" and mastered.learning_value < upload.learning_value
                ok_targets = [t.action_type for t in tracker.top_targets(2)] == ["browser_upload"]
                passed = ok_improving and ok_mastered and ok_targets
                return passed, \
                    f"improving={ok_improving} mastered={ok_mastered} targeted={ok_targets}", \
                    {"upload_value": upload.learning_value, "mastered_value": mastered.learning_value}

            checks.append(self._run_check("learning_progress_targets_growth", "adaptation", learning_progress_targets_growth))

            def failure_adaptation():
                from app.cognition.strategy_outcomes import StrategyOutcomeStore
                store = StrategyOutcomeStore(str(root / "failure_outcomes.db"))
                before = store.adjustment_factor("search", "web_search")
                for _ in range(4):
                    store.record_outcome("search", "web_search", False, surprisal=0.8)
                after = store.adjustment_factor("search", "web_search")
                return after < before, f"utility factor {before:.3f} → {after:.3f}", {
                    "before": before, "after": after,
                }

            checks.append(self._run_check("failure_lowers_future_utility", "learning", failure_adaptation))

            def success_adaptation():
                from app.cognition.strategy_outcomes import StrategyOutcomeStore
                store = StrategyOutcomeStore(str(root / "success_outcomes.db"))
                before = store.adjustment_factor("files", "search_files")
                for _ in range(4):
                    store.record_outcome("files", "search_files", True, surprisal=0.1)
                after = store.adjustment_factor("files", "search_files")
                return after > before, f"utility factor {before:.3f} → {after:.3f}", {
                    "before": before, "after": after,
                }

            checks.append(self._run_check("success_raises_future_utility", "learning", success_adaptation))

            def adaptive_thresholds():
                from app.cognition.adaptive_autonomy import AdaptiveAutonomyCalibrator
                from app.cognition.strategy_outcomes import StrategyOutcomeStore
                outcomes = StrategyOutcomeStore(str(root / "adaptive_outcomes.db"))
                for index in range(8):
                    outcomes.record_outcome(
                        "test", "diagnostic", index < 2, surprisal=0.7 + index * 0.02
                    )
                profile = AdaptiveAutonomyCalibrator(root / "adaptive.json").calibrate(outcomes)
                passed = (
                    profile.source == "verified_strategy_outcomes"
                    and profile.sample_count == 8
                    and profile.goal_auto_approve_threshold > 0.7
                    and profile.exploration_budget == 1
                )
                return passed, "low success tightened approval and reduced curiosity", profile.to_dict()

            checks.append(self._run_check("outcomes_calibrate_autonomy", "adaptation", adaptive_thresholds))

            def semantic_consolidation():
                from app.cognition.goal_lifecycle import GoalLifecycleState
                from app.cognition.memory import MemoryStore
                from app.cognition.memory_learning import MemoryLearner
                memory = MemoryStore(root / "consolidation.db")
                learner = MemoryLearner(memory)
                verification = SimpleNamespace(
                    verified_success=True,
                    final_state=GoalLifecycleState.ACHIEVED,
                    met_conditions=["found = true"],
                    failed_conditions=[],
                    verification_reason="direct probe",
                )
                for index in range(2):
                    learner.record_verified_episode(
                        goal=f"Find report {index}", action_type="search_files",
                        verification_result=verification, task_type="search_intent",
                    )
                created = learner.consolidate_verified_episodes(
                    memory.unconsolidated_episodes()
                )
                kinds = {item.kind for item in created}
                second = learner.consolidate_verified_episodes(
                    memory.unconsolidated_episodes()
                )
                passed = "semantic" in kinds and "procedural" in kinds and not second
                return passed, f"created kinds={sorted(kinds)}, second_pass={len(second)}", {
                    "created": len(created), "idempotent_second_pass": len(second),
                }

            checks.append(self._run_check("verified_memory_compounds_idempotently", "memory", semantic_consolidation))

            def authorization_replay():
                from app.cognition.execution_control import (
                    ExecutionCancelled,
                    ExecutionControlRegistry,
                )
                from app.cognition.owner_control import AuthorizationStore
                store = AuthorizationStore()
                payload = {"to": "owner@example.test", "body": "exact"}
                grant = store.issue("send_email", payload, ttl_seconds=60)
                drift = store.validate(
                    grant.authorization_id,
                    "send_email",
                    {"to": "other@example.test", "body": "exact"},
                )
                first = store.consume(grant.authorization_id, "send_email", payload)
                replay = store.consume(grant.authorization_id, "send_email", payload)
                executions = ExecutionControlRegistry(root / "benchmark_executions.db")
                controlled = executions.begin("benchmark-proposal", "diagnostic")
                executions.request_cancel(controlled.execution_id)
                cancellation_observed = False
                with executions.scope(controlled.execution_id):
                    try:
                        executions.checkpoint("benchmark")
                    except ExecutionCancelled:
                        cancellation_observed = True
                passed = (
                    first.valid and not replay.valid and not drift.valid
                    and cancellation_observed
                )
                return passed, "exact grants reject replay/drift; cooperative cancellation reaches checkpoint", {
                    "first": first.valid,
                    "replay": replay.valid,
                    "drift": drift.valid,
                    "cancellation_observed": cancellation_observed,
                }

            checks.append(self._run_check("authorization_replay_integrity", "control", authorization_replay))

            def temporal_continuity():
                from app.cognition.temporal_vision import TemporalVisionTracker
                tracker = TemporalVisionTracker(root / "vision.db")
                first = tracker.update_frame([{
                    "label": "person", "confidence": 0.9,
                    "bbox": {"x": 0, "y": 0, "width": 100, "height": 100},
                }], source="benchmark")
                second = tracker.update_frame([{
                    "label": "person", "confidence": 0.9,
                    "bbox": {"x": 10, "y": 0, "width": 100, "height": 100},
                }], source="benchmark")
                first_id = first["tracks"][0]["track_id"]
                second_id = second["tracks"][0]["track_id"]
                return first_id == second_id, "same stream/object retained track ID", {
                    "same_track": first_id == second_id,
                }

            checks.append(self._run_check("temporal_object_continuity", "perception", temporal_continuity))

            def training_review_gate():
                from app.cognition.training_examples import TrainingExampleStatus, TrainingExampleStore
                store = TrainingExampleStore(root / "training.db")
                unverified = SimpleNamespace(verified_success=False)
                verified = SimpleNamespace(
                    verified_success=True,
                    met_conditions=["artifact = true"],
                    verification_reason="direct probe",
                )
                rejected = store.propose_verified(
                    prompt="Find report", response="unverified", action_type="search_files",
                    verification_result=unverified,
                )
                candidate = store.propose_verified(
                    prompt="Find report", response="reports/q3.pdf", action_type="search_files",
                    verification_result=verified,
                )
                passed = (
                    rejected is None
                    and candidate is not None
                    and candidate.status == TrainingExampleStatus.PENDING
                    and store.export_approved("search_files").get("success") is False
                )
                return passed, "unverified excluded; verified remains pending; export gated", {
                    "pending": candidate is not None,
                }

            checks.append(self._run_check("lora_owner_review_boundary", "continual_learning", training_review_gate))

            def dependency_unlock():
                from app.cognition.goal_decomposer import GoalDecomposer, SubGoalStatus
                decomposer = GoalDecomposer(str(root / "decomposition.db"))
                decomposition = decomposer.decompose(
                    "two steps",
                    custom_steps=[
                        {"description": "first", "action_type": "diagnostic", "depends_on": []},
                        {"description": "second", "action_type": "search_files", "depends_on": [0]},
                    ],
                )
                before = [item.sub_goal_id for item in decomposition.get_ready_sub_goals()]
                decomposer.update_sub_goal(
                    decomposition.project_id,
                    decomposition.sub_goals[0].sub_goal_id,
                    SubGoalStatus.COMPLETED,
                    result={"verified_success": True},
                )
                after = [item.sub_goal_id for item in decomposition.get_ready_sub_goals()]
                passed = before == [decomposition.sub_goals[0].sub_goal_id] and after == [
                    decomposition.sub_goals[1].sub_goal_id
                ]
                return passed, "verified predecessor unlocks only dependent successor", {
                    "ready_before": before, "ready_after": after,
                }

            checks.append(self._run_check("project_dependency_unlock", "planning", dependency_unlock))

            def owner_curiosity_cap():
                from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator, GoalSource
                generator = AutonomousGoalGenerator(str(root / "goals.db"))
                goals = generator.generate_goals_from_signals(
                    {
                        "unknown_entities": ["a", "b", "c"],
                        "failed_actions": ["search_files"],
                    },
                    thresholds={"exploration_budget": 0},
                )
                curiosity = [
                    goal for goal in goals
                    if goal.source in (GoalSource.CURIOSITY, GoalSource.INFORMATION_GAP)
                ]
                optimization = [
                    goal for goal in goals if goal.source == GoalSource.SYSTEM_OPTIMIZATION
                ]
                return not curiosity and bool(optimization), (
                    "zero curiosity budget preserved deterministic optimization"
                ), {"curiosity": len(curiosity), "optimization": len(optimization)}

            checks.append(self._run_check("owner_curiosity_cap", "control", owner_curiosity_cap))

            def agency_attribution_integrity():
                from app.cognition.self_knowledge import SelfKnowledgeLedger
                ledger = SelfKnowledgeLedger(root / "self_knowledge.db")
                coincidence = ledger.attribute_change(
                    "file appeared after action", execution_id="exec-a",
                    execution_attempted=True, environment_observed=False,
                    goal_verified=None, evidence=["nearby timestamps"],
                )
                verified = ledger.attribute_change(
                    "exact note observed", execution_id="exec-b",
                    execution_attempted=True, environment_observed=True,
                    goal_verified=True, evidence=["note id and hash matched"],
                )
                passed = (
                    coincidence.cause_type == "unknown"
                    and verified.cause_type == "self_caused"
                )
                return passed, "coincidence stays unknown; verified intervention is self-caused", {
                    "coincidence": coincidence.cause_type,
                    "verified_intervention": verified.cause_type,
                }

            checks.append(self._run_check(
                "agency_attribution_integrity", "self_awareness",
                agency_attribution_integrity,
            ))

            def commitment_continuity():
                from app.cognition.commitment_ledger import CommitmentLedger
                path = root / "commitments.db"
                first = CommitmentLedger(path)
                first.upsert(
                    "Finish report", source_type="explicit_owner", source_id="owner-1",
                    status="blocked", evidence=["owner_api:owner-1"],
                    blocked_reason="Waiting for evidence",
                )
                restored = CommitmentLedger(path).get_by_source(
                    "explicit_owner", "owner-1"
                )
                completion_blocked = False
                try:
                    first.upsert(
                        "Finish report", source_type="explicit_owner", source_id="owner-1",
                        status="completed", evidence=[], completion_verified=False,
                    )
                except ValueError:
                    completion_blocked = True
                passed = bool(
                    restored and restored.status == "blocked"
                    and restored.blocked_reason == "Waiting for evidence"
                    and completion_blocked
                )
                return passed, "blocked commitment survived restart; unverified completion rejected", {
                    "restored_status": restored.status if restored else None,
                    "unverified_completion_rejected": completion_blocked,
                }

            checks.append(self._run_check(
                "commitment_continuity", "self_awareness", commitment_continuity,
            ))

            def self_belief_calibration():
                from app.cognition.confidence_calibrator import ConfidenceCalibrator
                from app.cognition.self_knowledge import SelfKnowledgeLedger
                ledger = SelfKnowledgeLedger(root / "belief_revision.db")
                ledger.assert_claim(
                    "capability.camera", True, source_type="capability_probe",
                    evidence=["camera opened"], confidence=0.8,
                )
                ledger.assert_claim(
                    "capability.camera", False, source_type="capability_probe",
                    evidence=["camera unavailable"], confidence=1.0,
                )
                revisions = ledger.recent_revisions("capability.camera")
                calibrator = ConfidenceCalibrator(str(root / "competence.db"))
                for predicted, actual in ((0.9, False), (0.9, False), (0.9, True)):
                    calibrator.record("camera_photo", predicted, actual)
                report = calibrator.longitudinal_report()
                passed = bool(
                    revisions and revisions[0].change_type == "contradiction"
                    and report["total_records"] == 3
                    and report["actions"]["camera_photo"]["evidence_sufficient"]
                )
                return passed, "contradiction retained and competence tied to outcomes", {
                    "revision_type": revisions[0].change_type if revisions else None,
                    "samples": report["total_records"],
                    "ece": report["ece"],
                }

            checks.append(self._run_check(
                "self_belief_calibration", "self_awareness", self_belief_calibration,
            ))

            def embodied_boundary_integrity():
                from app.cognition.embodied_boundary import EmbodiedBoundaryModel
                model = EmbodiedBoundaryModel(root / "boundary.db")
                model.register("cursor", "actuator", "shared", can_write=True,
                               available=True, evidence=["tool:mouse_click"])
                command = model.record_event(
                    "cursor", "mouse_click", actor="arena", execution_id="e1",
                    authorized=True, observed=False, evidence=["command sent"])
                verified = model.record_event(
                    "cursor", "mouse_click", actor="arena", execution_id="e2",
                    authorized=True, observed=True, evidence=["position observed"])
                passed = command.actor == "unknown" and verified.actor == "arena"
                return passed, "command alone is unknown; observed authorized control is Arena", {
                    "command_actor": command.actor, "verified_actor": verified.actor}
            checks.append(self._run_check(
                "embodied_boundary_integrity", "self_awareness", embodied_boundary_integrity))

        previous_by_name = {
            check.name: check for check in previous.checks
        } if previous else {}
        regressions = [
            check.name for check in checks
            if not check.passed
            and check.name in previous_by_name
            and previous_by_name[check.name].passed
        ]
        run = BenchmarkRun(
            run_id=f"bench_{uuid4().hex[:12]}",
            created_at=_now(),
            checks=checks,
            passed_count=sum(1 for check in checks if check.passed),
            total_count=len(checks),
            regressions=regressions,
        )
        self.history_store.save(run)
        return run
