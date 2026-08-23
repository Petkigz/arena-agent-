"""Owner review, editing, approval, and revocation for execution plans."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    EXECUTED = "executed"


@dataclass
class PlanReview:
    plan_id: str
    goal_id: str
    goal_title: str
    revision: int
    status: PlanReviewStatus
    snapshot: Dict[str, Any]
    snapshot_sha256: str
    created_at: str
    updated_at: str
    decision_note: str = ""
    decided_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


def reviewable_snapshot(plan: Any) -> Dict[str, Any]:
    """Extract only owner-reviewable execution intent, excluding runtime state."""
    steps = []
    for step in plan.steps:
        task_type = getattr(step.task_type, "value", step.task_type)
        steps.append({
            "step_id": str(step.step_id),
            "goal_id": str(step.goal_id or plan.goal_id),
            "description": str(step.description),
            "task_type": str(task_type),
            "action_type": str(getattr(step, "action_type", "") or ""),
            "payload": dict(getattr(step, "payload", {}) or {}),
            "source_sub_goal_id": getattr(step, "source_sub_goal_id", None),
            "depends_on": list(step.depends_on or []),
            "requires_evidence": list(step.requires_evidence or []),
            "produces_evidence": list(step.produces_evidence or []),
            "success_criteria": list(step.success_criteria or []),
            "failure_conditions": list(step.failure_conditions or []),
        })
    return {
        "plan_id": str(plan.plan_id),
        "goal_id": str(plan.goal_id),
        "goal_title": str(plan.goal_title),
        "steps": steps,
    }


def snapshot_digest(snapshot: Dict[str, Any]) -> str:
    encoded = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(steps, list) or not steps:
        raise ValueError("A reviewed plan must contain at least one step")
    if len(steps) > 100:
        raise ValueError("A reviewed plan cannot exceed 100 steps")

    allowed_fields = {
        "step_id", "goal_id", "description", "task_type", "action_type",
        "payload", "source_sub_goal_id", "depends_on", "requires_evidence",
        "produces_evidence", "success_criteria", "failure_conditions",
    }
    normalized = []
    ids = set()
    for raw in steps:
        if not isinstance(raw, dict):
            raise ValueError("Each plan step must be an object")
        unknown = set(raw) - allowed_fields
        if unknown:
            raise ValueError(f"Unknown plan-step field(s): {', '.join(sorted(unknown))}")
        step_id = str(raw.get("step_id", "")).strip()
        description = str(raw.get("description", "")).strip()
        if not step_id or not description:
            raise ValueError("Every plan step requires step_id and description")
        if step_id in ids:
            raise ValueError(f"Duplicate plan step_id: {step_id}")
        task_type = str(raw.get("task_type", "analysis"))
        if task_type not in {
            "information_gathering", "analysis", "optimization", "maintenance",
            "exploration", "user_assistance",
        }:
            raise ValueError(f"Unknown task_type '{task_type}' in step '{step_id}'")
        payload = raw.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError(f"Step '{step_id}' payload must be an object")
        ids.add(step_id)
        normalized.append({
            "step_id": step_id,
            "goal_id": str(raw.get("goal_id", "")),
            "description": description,
            "task_type": task_type,
            "action_type": str(raw.get("action_type", "")),
            "payload": dict(payload),
            "source_sub_goal_id": raw.get("source_sub_goal_id"),
            "depends_on": [str(v) for v in raw.get("depends_on", [])],
            "requires_evidence": [str(v) for v in raw.get("requires_evidence", [])],
            "produces_evidence": [str(v) for v in raw.get("produces_evidence", [])],
            "success_criteria": [str(v) for v in raw.get("success_criteria", [])],
            "failure_conditions": [str(v) for v in raw.get("failure_conditions", [])],
        })

    for step in normalized:
        for dependency in step["depends_on"]:
            if dependency not in ids:
                raise ValueError(f"Unknown dependency '{dependency}' in step '{step['step_id']}'")
            if dependency == step["step_id"]:
                raise ValueError(f"Step '{step['step_id']}' cannot depend on itself")

    # Deterministic cycle check.
    graph = {step["step_id"]: step["depends_on"] for step in normalized}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("Plan dependencies contain a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    return normalized


class PlanReviewStore:
    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "plan_reviews.db"))
        self._lock = threading.RLock()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plan_reviews (
                    plan_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    goal_title TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    snapshot_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    decision_note TEXT NOT NULL DEFAULT '',
                    decided_at TEXT
                )
            """)
            conn.commit()

    def _save(self, review: PlanReview) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO plan_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                review.plan_id, review.goal_id, review.goal_title, review.revision,
                review.status.value, json.dumps(review.snapshot), review.snapshot_sha256,
                review.created_at, review.updated_at, review.decision_note, review.decided_at,
            ))
            conn.commit()

    @staticmethod
    def _from_row(row: Any) -> PlanReview:
        return PlanReview(
            plan_id=row[0], goal_id=row[1], goal_title=row[2], revision=row[3],
            status=PlanReviewStatus(row[4]), snapshot=json.loads(row[5]),
            snapshot_sha256=row[6], created_at=row[7], updated_at=row[8],
            decision_note=row[9], decided_at=row[10],
        )

    def get(self, plan_id: str) -> Optional[PlanReview]:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM plan_reviews WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            return self._from_row(row) if row else None

    def list(self, status: Optional[PlanReviewStatus] = None) -> List[PlanReview]:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM plan_reviews ORDER BY updated_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM plan_reviews WHERE status = ? ORDER BY updated_at DESC",
                    (status.value,),
                ).fetchall()
            return [self._from_row(row) for row in rows]

    def submit(self, plan: Any) -> PlanReview:
        with self._lock:
            snapshot = reviewable_snapshot(plan)
            _validate_steps(snapshot["steps"])
            digest = snapshot_digest(snapshot)
            existing = self.get(plan.plan_id)
            if existing and existing.snapshot_sha256 == digest:
                return existing
            now = _now()
            review = PlanReview(
                plan_id=plan.plan_id,
                goal_id=plan.goal_id,
                goal_title=plan.goal_title,
                revision=(existing.revision + 1) if existing else 1,
                status=PlanReviewStatus.PENDING,
                snapshot=snapshot,
                snapshot_sha256=digest,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            self._save(review)
            audit_logger.warning(
                f"Plan submitted for owner review: {review.plan_id} revision={review.revision}"
            )
            return review

    def edit(self, plan_id: str, expected_revision: int, steps: List[Dict[str, Any]]) -> PlanReview:
        with self._lock:
            review = self.get(plan_id)
            if review is None:
                raise KeyError(plan_id)
            if review.revision != expected_revision:
                raise ValueError(
                    f"Plan revision conflict: expected {expected_revision}, current {review.revision}"
                )
            normalized = _validate_steps(steps)
            review.snapshot = {**review.snapshot, "steps": normalized}
            review.snapshot_sha256 = snapshot_digest(review.snapshot)
            review.revision += 1
            review.status = PlanReviewStatus.PENDING
            review.updated_at = _now()
            review.decision_note = ""
            review.decided_at = None
            self._save(review)
            audit_logger.warning(f"Owner edited plan: {plan_id} revision={review.revision}")
            return review

    def decide(
        self,
        plan_id: str,
        expected_revision: int,
        approved: bool,
        note: str = "",
    ) -> PlanReview:
        with self._lock:
            review = self.get(plan_id)
            if review is None:
                raise KeyError(plan_id)
            if review.revision != expected_revision:
                raise ValueError(
                    f"Plan revision conflict: expected {expected_revision}, current {review.revision}"
                )
            if review.status != PlanReviewStatus.PENDING:
                raise ValueError(f"Plan is already {review.status.value}")
            review.status = PlanReviewStatus.APPROVED if approved else PlanReviewStatus.REJECTED
            review.decision_note = note
            review.decided_at = _now()
            review.updated_at = review.decided_at
            self._save(review)
            audit_logger.warning(f"Owner {review.status.value} plan: {plan_id} revision={review.revision}")
            return review

    def revoke(self, plan_id: str, note: str = "") -> PlanReview:
        with self._lock:
            review = self.get(plan_id)
            if review is None:
                raise KeyError(plan_id)
            review.status = PlanReviewStatus.REVOKED
            review.decision_note = note
            review.decided_at = _now()
            review.updated_at = review.decided_at
            self._save(review)
            audit_logger.warning(f"Owner revoked plan: {plan_id}")
            return review

    def apply_to_plan(self, plan: Any) -> Any:
        review = self.get(plan.plan_id)
        if review is None:
            raise ValueError("Plan has not been submitted for owner review")
        from app.cognition.autonomous_goal_executor import ExecutionStatus, ExecutionStep
        existing = {step.step_id: step for step in plan.steps}
        applied = []
        for step_data in review.snapshot["steps"]:
            step = ExecutionStep.from_dict(step_data)
            previous = existing.get(step.step_id)
            # Resuming an approved, partially executed plan must not erase verified
            # results. Before first execution, reviewed edits remain clean/pending.
            if plan.started_at and previous and previous.status != ExecutionStatus.PENDING:
                step.status = previous.status
                step.result = previous.result
                step.error = previous.error
                step.started_at = previous.started_at
                step.completed_at = previous.completed_at
                step.confidence = previous.confidence
            applied.append(step)
        plan.goal_title = review.snapshot["goal_title"]
        plan.steps = applied
        return plan

    def is_current_approval(self, plan: Any) -> bool:
        review = self.get(plan.plan_id)
        return bool(
            review
            and review.status == PlanReviewStatus.APPROVED
            and review.snapshot_sha256 == snapshot_digest(reviewable_snapshot(plan))
        )

    def mark_executed(self, plan_id: str) -> None:
        with self._lock:
            review = self.get(plan_id)
            if review and review.status == PlanReviewStatus.APPROVED:
                review.status = PlanReviewStatus.EXECUTED
                review.updated_at = _now()
                self._save(review)


plan_review_store = PlanReviewStore()
