"""Skill induction: compress repeated successful action sequences into skills.

Skills previously existed only when the owner taught them (teach_skill). This
module adds the human ability to learn procedures from OWN EXPERIENCE: mine
completed execution plans for action sequences that repeatedly succeed,
abstract their payloads into templates, and propose them as named skills.

Owner-sovereignty boundary (consistent with every other learning surface):
  * Induced skills are PROPOSALS. Nothing enters the taught-skills library —
    and nothing executes — until the owner accepts it. Rejection is final for
    that candidate revision.
  * Evidence is counted, not vibes: a candidate needs MIN_OCCURRENCES
    distinct-plan occurrences and a ≥ SUCCESS_RATE context success rate, and
    carries its evidence (plan ids, occurrence count) in the proposal.
  * Payload templating abstracts only what actually varies across occurrences
    (value → {{param}}); constant fields stay concrete. Nothing is invented.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger, audit_logger

MIN_OCCURRENCES = 3
SUCCESS_RATE = 0.8
MIN_SEQUENCE_LENGTH = 2
MAX_SEQUENCE_LENGTH = 5

_SKILL_NAME_RE = re.compile(r"[^a-z0-9_]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(sequence: List[str]) -> str:
    joined = "_then_".join(a.lower() for a in sequence)
    slug = _SKILL_NAME_RE.sub("_", joined)[:80].strip("_")
    return f"induced_{slug}" if slug else "induced_skill"


@dataclass
class InducedSkill:
    candidate_id: str
    skill_name: str
    action_sequence: List[str]
    occurrences: int
    context_success_rate: float  # completed / all plans containing the sequence
    payload_template: List[Dict[str, Any]]
    evidence_plan_ids: List[str]
    status: str  # pending | accepted | rejected
    created_at: str = field(default_factory=_now)
    decided_at: Optional[str] = None
    taught_skill_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SkillInductionEngine:
    """Mine successful plan histories and propose reusable skills."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path or (settings.DATA_DIR / "induced_skills.db"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS induced_skills (
                candidate_id TEXT PRIMARY KEY,
                skill_name TEXT NOT NULL,
                action_sequence_json TEXT NOT NULL,
                occurrences INTEGER NOT NULL,
                context_success_rate REAL NOT NULL,
                payload_template_json TEXT NOT NULL,
                evidence_plan_ids_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                taught_skill_name TEXT
            )""")
            conn.commit()

    def _row(self, row: sqlite3.Row) -> InducedSkill:
        return InducedSkill(
            candidate_id=row[0], skill_name=row[1],
            action_sequence=json.loads(row[2]), occurrences=int(row[3]),
            context_success_rate=float(row[4]), payload_template=json.loads(row[5]),
            evidence_plan_ids=json.loads(row[6]), status=row[7],
            created_at=row[8], decided_at=row[9], taught_skill_name=row[10],
        )

    # ── mining ──────────────────────────────────────────────────────────────
    @staticmethod
    def _load_plans(plans_db: str | Path) -> List[Tuple[str, str, List[Dict[str, Any]]]]:
        """All plans as (plan_id, status, steps); completion is measured, not assumed."""
        plans: List[Tuple[str, str, List[Dict[str, Any]]]] = []
        try:
            with sqlite3.connect(str(plans_db)) as conn:
                rows = conn.execute(
                    "SELECT plan_id, status, steps FROM execution_plans"
                ).fetchall()
        except Exception as exc:
            app_logger.warning(f"Skill induction could not read plan history: {exc}")
            return []
        for plan_id, status, steps_json in rows:
            try:
                plans.append((plan_id, str(status or ""), json.loads(steps_json)))
            except Exception:
                continue
        return plans

    @staticmethod
    def _template_payloads(sequence: List[str], occurrences: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Abstract varying payload values into {{params}}; constants stay concrete."""
        template: List[Dict[str, Any]] = []
        for step_index, action_type in enumerate(sequence):
            merged: Dict[str, Any] = {}
            keys: Dict[str, List[Any]] = {}
            for occurrence in occurrences:
                payload = (occurrence[step_index] or {}).get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}
                for key, value in payload.items():
                    keys.setdefault(key, []).append(value)
            for key, values in keys.items():
                distinct = {json.dumps(v, sort_keys=True, default=str) for v in values}
                merged[key] = f"{{{{{key}}}}}" if len(distinct) > 1 else values[0]
            merged["action_type"] = action_type
            template.append(merged)
        return template

    def scan(self, plans_db: str | Path) -> Dict[str, Any]:
        """Mine the plan history; new candidates are recorded (idempotent by sequence).

        A sequence qualifies when it appears as contiguous COMPLETED steps in
        at least MIN_OCCURRENCES distinct plans AND at least SUCCESS_RATE of
        ALL plans containing it completed — failed contexts count against it.
        """
        plans = self._load_plans(plans_db)
        total_completed = 0
        # n-gram -> evidence across plans (completed occurrences drive induction;
        # every containing plan counts toward the success denominator).
        ngram_completed_plans: Dict[Tuple[str, ...], List[str]] = {}
        ngram_all_plans: Dict[Tuple[str, ...], set] = {}
        ngram_occurrences: Dict[Tuple[str, ...], List[List[Dict[str, Any]]]] = {}
        for plan_id, status, steps in plans:
            actions: List[str] = []
            payloads: List[Dict[str, Any]] = []
            for step in steps:
                if str(step.get("status", "")).lower() == "completed" and step.get("action_type"):
                    actions.append(str(step["action_type"]))
                    payloads.append(step)
            total_completed += len(actions)
            for length in range(MIN_SEQUENCE_LENGTH, MAX_SEQUENCE_LENGTH + 1):
                for start in range(0, len(actions) - length + 1):
                    ngram = tuple(actions[start:start + length])
                    ngram_all_plans.setdefault(ngram, set()).add(plan_id)
                    if status.lower() == "completed":
                        if plan_id not in ngram_completed_plans.setdefault(ngram, []):
                            ngram_completed_plans[ngram].append(plan_id)
                        ngram_occurrences.setdefault(ngram, []).append(payloads[start:start + length])

        candidates: List[Tuple[Tuple[str, ...], List[str], List[List[Dict]]]] = []
        for ngram in sorted(ngram_all_plans, key=len, reverse=True):
            completed_in = ngram_completed_plans.get(ngram, [])
            containing = ngram_all_plans[ngram]
            if len(completed_in) < MIN_OCCURRENCES:
                continue
            success_rate = len(completed_in) / len(containing) if containing else 0.0
            if success_rate < SUCCESS_RATE:
                continue  # failed contexts veto the pattern
            if any(set(completed_in) <= set(existing[1]) and len(ngram) < len(existing[0])
                   for existing in candidates):
                continue  # sub-sequence of an already-kept longer candidate
            candidates.append((ngram, completed_in, ngram_occurrences[ngram]))

        created, existing_count = 0, 0
        for ngram, plan_ids, occurrences in candidates:
            sequence = list(ngram)
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT candidate_id FROM induced_skills WHERE action_sequence_json=? AND status='pending'",
                    (json.dumps(sequence),),
                ).fetchone()
            if row:
                existing_count += 1
                continue
            candidate = InducedSkill(
                candidate_id=f"isk_{uuid4().hex[:14]}",
                skill_name=_safe_name(sequence),
                action_sequence=sequence,
                occurrences=len(plan_ids),
                context_success_rate=round(len(plan_ids) / len(ngram_all_plans[ngram]), 4),
                payload_template=self._template_payloads(sequence, occurrences[:20]),
                evidence_plan_ids=plan_ids[:50],
                status="pending",
            )
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO induced_skills VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        candidate.candidate_id, candidate.skill_name,
                        json.dumps(candidate.action_sequence), candidate.occurrences,
                        candidate.context_success_rate, json.dumps(candidate.payload_template, default=str),
                        json.dumps(candidate.evidence_plan_ids), candidate.status,
                        candidate.created_at, None, None,
                    ),
                )
                conn.commit()
            audit_logger.info(
                "Skill induction candidate: %s (%d completed-plan occurrences)",
                candidate.skill_name, candidate.occurrences,
            )
            created += 1
        return {
            "success": True, "plans_scanned": len(plans), "completed_steps": total_completed,
            "candidates_created": created, "candidates_already_pending": existing_count,
            "note": "Proposals only: nothing is taught or executed until the owner accepts.",
        }

    # ── owner decisions ─────────────────────────────────────────────────────
    def list(self, status: Optional[str] = "pending") -> List[InducedSkill]:
        q = "SELECT * FROM induced_skills"
        params: List[Any] = []
        if status:
            q += " WHERE status=?"
            params.append(status)
        q += " ORDER BY occurrences DESC, created_at DESC"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(q, params).fetchall()
        return [self._row(r) for r in rows]

    def get(self, candidate_id: str) -> Optional[InducedSkill]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM induced_skills WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        return self._row(row) if row else None

    def accept(self, candidate_id: str) -> Dict[str, Any]:
        candidate = self.get(candidate_id)
        if candidate is None:
            return {"success": False, "error": "Candidate not found"}
        if candidate.status != "pending":
            return {"success": False, "error": f"Candidate already {candidate.status}"}
        from app.tools.skill_teaching_engine import SkillTeachingEngine
        instructions = "Auto-induced procedure (owner-accepted). Steps:\n" + "\n".join(
            f"{i + 1}. {step.get('action_type')}: {json.dumps({k: v for k, v in step.items() if k != 'action_type'}, default=str)}"
            for i, step in enumerate(candidate.payload_template)
        )
        taught = SkillTeachingEngine.teach_skill(
            skill_name=candidate.skill_name,
            category="induced",
            trigger_keywords=[a.lower() for a in candidate.action_sequence],
            instructions=instructions,
            safety_rules="Induced from verified completions; each execution still passes all gates.",
        )
        if not taught.get("success"):
            return {"success": False, "error": taught.get("error", "teach_skill failed")}
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE induced_skills SET status='accepted', decided_at=?, taught_skill_name=? WHERE candidate_id=?",
                (_now(), candidate.skill_name, candidate_id),
            )
            conn.commit()
        audit_logger.warning("Owner ACCEPTED induced skill: %s", candidate.skill_name)
        return {"success": True, "taught_skill_name": candidate.skill_name,
                "note": "Skill is now in the taught-skills library; executing it still passes all gates."}

    def reject(self, candidate_id: str) -> Dict[str, Any]:
        candidate = self.get(candidate_id)
        if candidate is None:
            return {"success": False, "error": "Candidate not found"}
        if candidate.status != "pending":
            return {"success": False, "error": f"Candidate already {candidate.status}"}
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE induced_skills SET status='rejected', decided_at=? WHERE candidate_id=?",
                (_now(), candidate_id),
            )
            conn.commit()
        return {"success": True, "rejected": candidate_id}


# Module-level singleton, mirroring the other stores.
skill_induction_engine = SkillInductionEngine()
