"""Bounded Phase 7 preference and novelty evaluations.

This module provides deterministic, inspectable behavioral analogues for
curiosity, simplicity/elegance preference, and novelty.  It does not execute
work, grant authority, infer subjective experience, or treat novelty as
quality.  Recommendations are hypotheses/advice and must be routed through
existing owner, evidence, and execution controls.

The measures intentionally use transparent proxies rather than pretending to
be human taste or calibrated general intelligence:

* curiosity combines information gain, measured learning progress,
  owner-approved exploration, and evidence-backed anomaly investigation;
* simplicity/elegance combines complexity, maintainability, reversibility, and
  description-length proxies, with utility comparison before selection;
* novelty compares lexical token overlap with retrieved material, baseline
  strategies, and prior outputs, and reports reference coverage as uncertainty.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    if not math.isfinite(numeric):
        numeric = default
    return round(max(0.0, min(1.0, numeric)), 6)


def _require_trace(trace_id: str) -> str:
    value = str(trace_id or "").strip()
    if not value:
        raise Phase7PreferenceError("phase 7 evaluations require a trace_id")
    return value


def _evidence_ids(evidence_ids: Iterable[Any]) -> List[str]:
    values = [
        str(item).strip()
        for item in (evidence_ids or [])
        if str(item).strip()
    ]
    if not values:
        raise Phase7PreferenceError("phase 7 evaluations require evidence_ids")
    return list(dict.fromkeys(values))


def _ratio(value: Any, denominator: float) -> float:
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        numeric = 0.0
    return _clamp(numeric / denominator if denominator else 0.0)


def _tokens(text: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _reference_text(item: Any) -> Tuple[str, str, Optional[str]]:
    if isinstance(item, Mapping):
        content = item.get("content", item.get("text", item.get("description", "")))
        kind = str(item.get("source_type", item.get("kind", "reference")))
        evidence = item.get("evidence_id", item.get("id"))
        return str(content or ""), kind, str(evidence) if evidence else None
    return str(item or ""), "reference", None


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class Phase7PreferenceError(ValueError):
    """Invalid, incomplete, or unverifiable Phase 7 evaluation input."""


@dataclass(frozen=True)
class CuriosityAssessment:
    information_gain: float
    learning_progress: float
    owner_approved_exploration: float
    anomaly_investigation: float
    curiosity_score: float
    recommended_targets: List[Dict[str, Any]] = field(default_factory=list)
    activity_cap: int = 0
    owner_authorization_id: Optional[str] = None
    bounded: bool = True
    advisory_only: bool = True
    authority: str = "none"
    result_type: str = "generated_hypothesis"
    trace_id: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TasteAssessment:
    solution_id: str
    utility: float
    complexity: float
    maintainability: float
    reversibility: float
    description_length_proxy: float
    simplicity_score: float
    preference_score: float
    utility_comparable: bool = False
    selected: bool = False
    assumptions: List[str] = field(default_factory=list)
    result_type: str = "generated_hypothesis"
    trace_id: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NoveltyAssessment:
    novelty_score: float
    surprise_score: float
    uncertainty: float
    novelty_flagged: bool
    quality_not_inferred: bool
    comparison_count: int
    reference_coverage: float
    max_similarity: float
    similarity_by_source: Dict[str, float] = field(default_factory=dict)
    calibration_status: str = "insufficient_reference_evidence"
    result_type: str = "generated_hypothesis"
    trace_id: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Phase7AssessmentStore:
    """Small versioned audit store for Phase 7 assessments.

    This is an observability store only.  Rows contain recommendations and
    comparisons; they are not an action queue, an owner grant, or a second
    execution authority.
    """

    STORAGE_SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS phase7_meta (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    storage_schema_version INTEGER NOT NULL
                )
                """
            )
            row = conn.execute(
                "SELECT storage_schema_version FROM phase7_meta WHERE singleton=1"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO phase7_meta VALUES (1, ?)",
                    (self.STORAGE_SCHEMA_VERSION,),
                )
            elif int(row[0]) != self.STORAGE_SCHEMA_VERSION:
                raise Phase7PreferenceError(
                    f"unsupported phase 7 schema_version={row[0]}; "
                    f"supported version is {self.STORAGE_SCHEMA_VERSION}"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS phase7_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    assessment_type TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    result_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def record(
        self,
        assessment_type: str,
        payload: Mapping[str, Any],
        *,
        trace_id: str,
        evidence_ids: Iterable[Any],
        result_type: str,
    ) -> Dict[str, Any]:
        trace = _require_trace(trace_id)
        evidence = _evidence_ids(evidence_ids)
        if not str(assessment_type).strip():
            raise Phase7PreferenceError("assessment_type is required")
        if not str(result_type).strip():
            raise Phase7PreferenceError("result_type is required")
        record = {
            "assessment_id": f"phase7_{uuid4().hex[:16]}",
            "assessment_type": str(assessment_type),
            "trace_id": trace,
            "result_type": str(result_type),
            "payload": dict(payload),
            "evidence_ids": evidence,
            "created_at": _now(),
        }
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO phase7_assessments VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record["assessment_id"],
                    record["assessment_type"],
                    record["trace_id"],
                    record["result_type"],
                    json.dumps(record["payload"], sort_keys=True, default=str),
                    json.dumps(evidence),
                    record["created_at"],
                ),
            )
            conn.commit()
        return record

    def history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT assessment_id, assessment_type, trace_id, result_type,
                       payload_json, evidence_json, created_at
                FROM phase7_assessments
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [
            {
                "assessment_id": row[0],
                "assessment_type": row[1],
                "trace_id": row[2],
                "result_type": row[3],
                "payload": json.loads(row[4]),
                "evidence_ids": json.loads(row[5]),
                "created_at": row[6],
            }
            for row in rows
        ]


class Phase7PreferenceEngine:
    """Deterministic evaluators with no action or authorization capability."""

    UTILITY_TOLERANCE = 0.10

    def __init__(self, db_path: str | Path) -> None:
        self.store = Phase7AssessmentStore(db_path)

    @staticmethod
    def _mapping_value(item: Any, name: str, default: Any = None) -> Any:
        if isinstance(item, Mapping):
            return item.get(name, default)
        return getattr(item, name, default)

    def assess_curiosity(
        self,
        *,
        information_needs: Sequence[Any] = (),
        learning_targets: Sequence[Any] = (),
        anomalies: Sequence[Any] = (),
        owner_approved_exploration: bool = False,
        owner_authorization_id: Optional[str] = None,
        trace_id: str,
        evidence_ids: Iterable[Any],
    ) -> CuriosityAssessment:
        trace = _require_trace(trace_id)
        evidence = _evidence_ids(evidence_ids)
        authorization_id = str(owner_authorization_id or "").strip() or None
        if owner_approved_exploration and not authorization_id:
            raise Phase7PreferenceError(
                "owner-approved exploration requires owner_authorization_id"
            )

        needs = []
        for item in information_needs:
            priority = _clamp(self._mapping_value(item, "priority", 0.0))
            question = str(self._mapping_value(item, "question", "")).strip()
            target = str(self._mapping_value(item, "target", "")).strip()
            if priority > 0 and (question or target):
                needs.append({
                    "category": "information_gain",
                    "target": target,
                    "question": question,
                    "score": priority,
                    "result_type": "generated_hypothesis",
                })

        progress = []
        for item in learning_targets:
            value = _clamp(self._mapping_value(item, "learning_value", 0.0))
            status = str(self._mapping_value(item, "status", "unknown"))
            if value > 0 and status in {"improving", "weak"}:
                progress.append({
                    "category": "learning_progress",
                    "target": str(self._mapping_value(item, "action_type", "")),
                    "score": value,
                    "status": status,
                    "result_type": "generated_hypothesis",
                })

        anomaly_rows = []
        for item in anomalies:
            score = _clamp(self._mapping_value(item, "score", self._mapping_value(item, "surprisal", 0.0)))
            item_evidence = [
                str(value).strip()
                for value in (self._mapping_value(item, "evidence_ids", []) or [])
                if str(value).strip()
            ]
            # An anomaly without provenance is not promoted to a curiosity
            # target.  It may still be shown to an owner by the caller.
            if score > 0 and item_evidence:
                anomaly_rows.append({
                    "category": "unresolved_anomaly",
                    "target": str(self._mapping_value(item, "target", "")),
                    "score": score,
                    "evidence_ids": item_evidence,
                    "result_type": "generated_hypothesis",
                })

        info_score = max((row["score"] for row in needs), default=0.0)
        progress_score = max((row["score"] for row in progress), default=0.0)
        anomaly_score = max((row["score"] for row in anomaly_rows), default=0.0)
        owner_score = 1.0 if bool(owner_approved_exploration) else 0.0
        score = _clamp(
            0.40 * info_score
            + 0.25 * progress_score
            + 0.20 * owner_score
            + 0.15 * anomaly_score
        )
        targets = sorted(needs + progress + anomaly_rows, key=lambda row: -row["score"])[:5]
        assessment = CuriosityAssessment(
            information_gain=info_score,
            learning_progress=progress_score,
            owner_approved_exploration=owner_score,
            anomaly_investigation=anomaly_score,
            curiosity_score=score,
            recommended_targets=targets,
            # One bounded recommendation per call. This is a cap, not an
            # authorization to enqueue or execute anything.
            activity_cap=1 if targets else 0,
            owner_authorization_id=authorization_id,
            trace_id=trace,
            evidence_ids=evidence,
            created_at=_now(),
        )
        self.store.record(
            "curiosity",
            assessment.to_dict(),
            trace_id=trace,
            evidence_ids=evidence,
            result_type=assessment.result_type,
        )
        return assessment

    @staticmethod
    def _solution_components(solution: Mapping[str, Any]) -> Tuple[float, float, float, float, List[str]]:
        assumptions: List[str] = []
        explicit_complexity = solution.get("complexity")
        if explicit_complexity is None:
            steps = _ratio(solution.get("step_count", 0), 20.0)
            dependencies = _ratio(solution.get("dependency_count", 0), 10.0)
            branches = _ratio(solution.get("branch_count", 0), 10.0)
            complexity = _clamp(0.50 * steps + 0.30 * dependencies + 0.20 * branches)
            assumptions.append("complexity_from_step_dependency_branch_counts")
        else:
            complexity = _clamp(explicit_complexity)

        maintainability = solution.get("maintainability")
        if maintainability is None:
            maintainability = 1.0 - complexity
            assumptions.append("maintainability_proxy_from_complexity")
        else:
            maintainability = _clamp(maintainability)

        reversibility = solution.get("reversibility")
        if reversibility is None:
            reversibility = 0.5
            assumptions.append("reversibility_unknown_baseline")
        else:
            reversibility = _clamp(reversibility)

        description = solution.get("description", solution.get("summary", ""))
        token_count = len(_tokens(description))
        description_length = _clamp(token_count / 160.0)
        if not description:
            assumptions.append("description_length_missing")
        return complexity, maintainability, reversibility, description_length, assumptions

    def score_solution(
        self,
        solution: Mapping[str, Any],
        *,
        trace_id: str,
        evidence_ids: Iterable[Any],
        utility_comparable: bool = False,
        selected: bool = False,
    ) -> TasteAssessment:
        trace = _require_trace(trace_id)
        evidence = _evidence_ids(evidence_ids)
        solution_id = str(solution.get("solution_id", solution.get("id", ""))).strip()
        if not solution_id:
            raise Phase7PreferenceError("solution_id is required")
        utility = _clamp(solution.get("utility"), default=0.0)
        complexity, maintainability, reversibility, description_length, assumptions = self._solution_components(solution)
        simplicity = _clamp(
            0.35 * (1.0 - complexity)
            + 0.25 * maintainability
            + 0.20 * reversibility
            + 0.20 * (1.0 - description_length)
        )
        # Preference is deliberately secondary to utility. It is not a quality
        # or safety score and cannot select an action by itself.
        preference = _clamp(0.65 * utility + 0.35 * simplicity)
        assessment = TasteAssessment(
            solution_id=solution_id,
            utility=utility,
            complexity=complexity,
            maintainability=maintainability,
            reversibility=reversibility,
            description_length_proxy=description_length,
            simplicity_score=simplicity,
            preference_score=preference,
            utility_comparable=bool(utility_comparable),
            selected=bool(selected),
            assumptions=assumptions,
            trace_id=trace,
            evidence_ids=evidence,
            created_at=_now(),
        )
        self.store.record(
            "simplicity_elegance",
            assessment.to_dict(),
            trace_id=trace,
            evidence_ids=evidence,
            result_type=assessment.result_type,
        )
        return assessment

    def choose_solution(
        self,
        solutions: Sequence[Mapping[str, Any]],
        *,
        trace_id: str,
        evidence_ids: Iterable[Any],
        utility_tolerance: float = UTILITY_TOLERANCE,
    ) -> Dict[str, Any]:
        trace = _require_trace(trace_id)
        evidence = _evidence_ids(evidence_ids)
        if not solutions:
            raise Phase7PreferenceError("at least one solution is required")
        tolerance = _clamp(utility_tolerance)
        raw_utilities = [_clamp(solution.get("utility"), default=0.0) for solution in solutions]
        max_utility = max(raw_utilities)
        comparable = [
            solution for solution, utility in zip(solutions, raw_utilities)
            if utility >= max_utility - tolerance
        ]
        # Utility remains the first filter. Simplicity breaks only a declared
        # comparable-utility tie; it never turns a low-utility option into a
        # preferred action.
        scored = [
            self.score_solution(
                solution,
                trace_id=trace,
                evidence_ids=evidence,
                utility_comparable=True,
                selected=False,
            )
            for solution in comparable
        ]
        winner = max(scored, key=lambda item: (item.simplicity_score, item.utility, item.preference_score))
        selected_id = winner.solution_id
        result = {
            "selected_solution_id": selected_id,
            "utility_floor": round(max_utility - tolerance, 6),
            "utility_tolerance": tolerance,
            "utility_comparable": len(comparable) > 1,
            "simplicity_preference_applied": len(comparable) > 1,
            "selection_is_advisory": True,
            "authority": "none",
            "result_type": "generated_hypothesis",
            "trace_id": trace,
            "evidence_ids": evidence,
            "candidates": [item.to_dict() for item in scored],
            "rationale": (
                "selected the simplest candidate within the declared utility tolerance"
                if len(comparable) > 1
                else "selected the utility-leading candidate; simplicity did not override utility"
            ),
        }
        self.store.record(
            "solution_selection",
            result,
            trace_id=trace,
            evidence_ids=evidence,
            result_type=result["result_type"],
        )
        return result

    def detect_novelty(
        self,
        output: str,
        *,
        retrieved_material: Sequence[Any] = (),
        baseline_strategies: Sequence[Any] = (),
        prior_outputs: Sequence[Any] = (),
        trace_id: str,
        evidence_ids: Iterable[Any],
    ) -> NoveltyAssessment:
        trace = _require_trace(trace_id)
        evidence = _evidence_ids(evidence_ids)
        output_tokens = _tokens(output)
        references: List[Tuple[str, str, Optional[str]]] = []
        references.extend(_reference_text(item) for item in retrieved_material)
        references.extend(_reference_text(item) for item in baseline_strategies)
        references.extend(_reference_text(item) for item in prior_outputs)
        references = [row for row in references if row[0].strip()]

        similarity_by_source: Dict[str, float] = {}
        max_similarity = 0.0
        if output_tokens and references:
            grouped: Dict[str, List[float]] = {}
            for text, source_type, _ in references:
                similarity = _jaccard(output_tokens, _tokens(text))
                grouped.setdefault(source_type, []).append(similarity)
                max_similarity = max(max_similarity, similarity)
            similarity_by_source = {
                source_type: round(max(values), 6)
                for source_type, values in grouped.items()
            }

        comparison_count = len(references)
        coverage = _clamp(comparison_count / 3.0)
        if not output_tokens or not references:
            novelty = 0.0
            surprise = 0.0
            uncertainty = 1.0
            status = "insufficient_reference_evidence"
            flagged = False
        else:
            novelty = _clamp(1.0 - max_similarity)
            surprise = novelty
            # This is a transparent coverage-based uncertainty proxy, not a
            # claim of statistical calibration.
            uncertainty = _clamp(1.0 - 0.65 * coverage + 0.25 * novelty)
            status = "calibrated_proxy" if comparison_count >= 3 else "limited_reference_evidence"
            flagged = novelty >= 0.65

        assessment = NoveltyAssessment(
            novelty_score=novelty,
            surprise_score=surprise,
            uncertainty=uncertainty,
            novelty_flagged=flagged,
            quality_not_inferred=True,
            comparison_count=comparison_count,
            reference_coverage=coverage,
            max_similarity=round(max_similarity, 6),
            similarity_by_source=similarity_by_source,
            calibration_status=status,
            trace_id=trace,
            evidence_ids=evidence,
            created_at=_now(),
        )
        self.store.record(
            "novelty",
            assessment.to_dict(),
            trace_id=trace,
            evidence_ids=evidence,
            result_type=assessment.result_type,
        )
        return assessment

    def history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.store.history(limit)