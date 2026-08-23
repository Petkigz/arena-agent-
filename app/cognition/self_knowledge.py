"""Evidence-linked self-knowledge and agency attribution.

This is functional introspection, not consciousness. A self-claim is accepted
only with provenance, revision history, confidence, and freshness. Temporal
coincidence alone can never establish that Arena caused an observed change.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


ALLOWED_SOURCES = {
    "capability_probe", "hardware_probe", "owner_policy", "verified_outcome",
    "execution_record", "environment_observation", "inference",
}


@dataclass(frozen=True)
class SelfClaim:
    claim_id: str
    predicate: str
    value: Any
    source_type: str
    evidence: List[str]
    confidence: float
    status: str
    created_at: str
    valid_until: Optional[str]
    supersedes_claim_id: Optional[str]

    @property
    def fresh(self) -> bool:
        if self.status != "current":
            return False
        if not self.valid_until:
            return True
        try:
            return datetime.now(timezone.utc) < datetime.fromisoformat(self.valid_until)
        except ValueError:
            return False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self) | {"fresh": self.fresh}


@dataclass(frozen=True)
class BeliefRevision:
    revision_id: str
    predicate: str
    old_claim_id: str
    new_claim_id: str
    change_type: str
    old_value: Any
    new_value: Any
    confidence_delta: float
    old_evidence: List[str]
    new_evidence: List[str]
    created_at: str
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgencyAttribution:
    attribution_id: str
    change_summary: str
    cause_type: str
    confidence: float
    evidence: List[str]
    execution_id: Optional[str]
    created_at: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SelfKnowledgeLedger:
    """Revisioned SQLite ledger for evidence-backed claims about this system."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS self_claims (
                claim_id TEXT PRIMARY KEY,
                predicate TEXT NOT NULL,
                value_json TEXT NOT NULL,
                source_type TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                valid_until TEXT,
                supersedes_claim_id TEXT
            )""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_self_claim_predicate ON self_claims(predicate, status, created_at)"
            )
            conn.execute("""CREATE TABLE IF NOT EXISTS belief_revisions (
                revision_id TEXT PRIMARY KEY,
                predicate TEXT NOT NULL,
                old_claim_id TEXT NOT NULL,
                new_claim_id TEXT NOT NULL,
                change_type TEXT NOT NULL,
                old_value_json TEXT NOT NULL,
                new_value_json TEXT NOT NULL,
                confidence_delta REAL NOT NULL,
                old_evidence_json TEXT NOT NULL,
                new_evidence_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                explanation TEXT NOT NULL
            )""")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_revision_predicate ON belief_revisions(predicate, created_at)"
            )
            conn.execute("""CREATE TABLE IF NOT EXISTS agency_attributions (
                attribution_id TEXT PRIMARY KEY,
                change_summary TEXT NOT NULL,
                cause_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                execution_id TEXT,
                created_at TEXT NOT NULL,
                reason TEXT NOT NULL
            )""")
            conn.commit()

    @staticmethod
    def _claim(row) -> SelfClaim:
        return SelfClaim(
            claim_id=row[0], predicate=row[1], value=json.loads(row[2]),
            source_type=row[3], evidence=json.loads(row[4]), confidence=float(row[5]),
            status=row[6], created_at=row[7], valid_until=row[8],
            supersedes_claim_id=row[9],
        )

    def assert_claim(
        self,
        predicate: str,
        value: Any,
        *,
        source_type: str,
        evidence: List[str],
        confidence: float,
        ttl_seconds: Optional[int] = None,
    ) -> SelfClaim:
        predicate = (predicate or "").strip().lower()
        source_type = (source_type or "").strip().lower()
        evidence = [str(item).strip() for item in evidence if str(item).strip()]
        if not predicate:
            raise ValueError("Self-claim predicate is required")
        if source_type not in ALLOWED_SOURCES:
            raise ValueError(f"Unsupported self-claim source: {source_type}")
        if not evidence:
            raise ValueError("A self-claim requires evidence provenance")
        confidence = max(0.0, min(1.0, float(confidence)))
        if source_type == "inference":
            confidence = min(confidence, 0.7)
        value_json = _canonical(value)
        valid_until = None
        if ttl_seconds is not None:
            valid_until = (
                datetime.now(timezone.utc) + timedelta(seconds=max(1, int(ttl_seconds)))
            ).isoformat()

        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM self_claims WHERE predicate=? AND status='current' "
                "ORDER BY created_at DESC LIMIT 1", (predicate,),
            ).fetchone()
            previous = self._claim(row) if row else None
            if previous and _canonical(previous.value) == value_json and previous.fresh:
                return previous
            supersedes = previous.claim_id if previous else None
            if previous:
                conn.execute(
                    "UPDATE self_claims SET status='superseded' WHERE claim_id=?",
                    (previous.claim_id,),
                )
            claim = SelfClaim(
                claim_id=f"self_{uuid4().hex[:16]}", predicate=predicate, value=value,
                source_type=source_type, evidence=evidence, confidence=confidence,
                status="current", created_at=_now(), valid_until=valid_until,
                supersedes_claim_id=supersedes,
            )
            conn.execute(
                "INSERT INTO self_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    claim.claim_id, claim.predicate, value_json, claim.source_type,
                    json.dumps(evidence), claim.confidence, claim.status,
                    claim.created_at, claim.valid_until, claim.supersedes_claim_id,
                ),
            )
            if previous:
                changed = _canonical(previous.value) != value_json
                change_type = "contradiction" if changed else "refresh"
                explanation = (
                    f"Evidence changed the value of '{predicate}' from the prior claim."
                    if changed else
                    f"Expired evidence for '{predicate}' was refreshed without changing its value."
                )
                conn.execute(
                    "INSERT INTO belief_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"revision_{uuid4().hex[:16]}", predicate, previous.claim_id,
                        claim.claim_id, change_type, _canonical(previous.value), value_json,
                        round(claim.confidence - previous.confidence, 6),
                        json.dumps(previous.evidence), json.dumps(claim.evidence),
                        claim.created_at, explanation,
                    ),
                )
            conn.commit()
            return claim

    def current_claims(self, include_stale: bool = True) -> List[SelfClaim]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM self_claims WHERE status='current' ORDER BY predicate"
            ).fetchall()
        claims = [self._claim(row) for row in rows]
        return claims if include_stale else [claim for claim in claims if claim.fresh]

    def history(self, predicate: Optional[str] = None, limit: int = 200) -> List[SelfClaim]:
        with sqlite3.connect(self.db_path) as conn:
            if predicate:
                rows = conn.execute(
                    "SELECT * FROM self_claims WHERE predicate=? ORDER BY created_at DESC LIMIT ?",
                    (predicate.lower().strip(), max(1, min(limit, 1000))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM self_claims ORDER BY created_at DESC LIMIT ?",
                    (max(1, min(limit, 1000)),),
                ).fetchall()
        return [self._claim(row) for row in rows]

    def recent_revisions(
        self, predicate: Optional[str] = None, limit: int = 100
    ) -> List[BeliefRevision]:
        bounded = max(1, min(limit, 1000))
        with sqlite3.connect(self.db_path) as conn:
            if predicate:
                rows = conn.execute(
                    "SELECT * FROM belief_revisions WHERE predicate=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (predicate.lower().strip(), bounded),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM belief_revisions ORDER BY created_at DESC LIMIT ?",
                    (bounded,),
                ).fetchall()
        return [
            BeliefRevision(
                revision_id=row[0], predicate=row[1], old_claim_id=row[2],
                new_claim_id=row[3], change_type=row[4],
                old_value=json.loads(row[5]), new_value=json.loads(row[6]),
                confidence_delta=float(row[7]), old_evidence=json.loads(row[8]),
                new_evidence=json.loads(row[9]), created_at=row[10],
                explanation=row[11],
            )
            for row in rows
        ]

    def attribute_change(
        self,
        change_summary: str,
        *,
        execution_id: Optional[str] = None,
        execution_attempted: bool = False,
        environment_observed: bool = False,
        goal_verified: Optional[bool] = None,
        owner_event: bool = False,
        external_source: Optional[str] = None,
        evidence: Optional[List[str]] = None,
    ) -> AgencyAttribution:
        """Attribute a change conservatively from explicit intervention evidence."""
        evidence = [str(item).strip() for item in (evidence or []) if str(item).strip()]
        if owner_event and evidence:
            cause_type, confidence = "owner_caused", 0.95
            reason = "An explicit owner event with provenance caused the change."
        elif external_source and evidence:
            cause_type, confidence = "external", 0.9
            reason = f"An identified external source caused the change: {external_source}."
        elif (
            execution_id and execution_attempted and environment_observed
            and goal_verified is True and evidence
        ):
            cause_type, confidence = "self_caused", 0.9
            reason = "A controlled execution was followed by observed, goal-verifying evidence."
        elif execution_id and execution_attempted:
            cause_type, confidence = "unknown", 0.35
            reason = "Arena acted, but observation and verification do not establish causation."
        else:
            cause_type, confidence = "unknown", 0.1
            reason = "Temporal proximity alone is not causal evidence."
        attribution = AgencyAttribution(
            attribution_id=f"agency_{uuid4().hex[:16]}",
            change_summary=str(change_summary), cause_type=cause_type,
            confidence=confidence, evidence=evidence, execution_id=execution_id,
            created_at=_now(), reason=reason,
        )
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO agency_attributions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    attribution.attribution_id, attribution.change_summary,
                    attribution.cause_type, attribution.confidence,
                    json.dumps(attribution.evidence), attribution.execution_id,
                    attribution.created_at, attribution.reason,
                ),
            )
            conn.commit()
        return attribution

    def recent_attributions(self, limit: int = 100) -> List[AgencyAttribution]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM agency_attributions ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [
            AgencyAttribution(
                attribution_id=row[0], change_summary=row[1], cause_type=row[2],
                confidence=float(row[3]), evidence=json.loads(row[4]),
                execution_id=row[5], created_at=row[6], reason=row[7],
            )
            for row in rows
        ]

    def snapshot(self) -> Dict[str, Any]:
        claims = self.current_claims(include_stale=True)
        return {
            "claims": [claim.to_dict() for claim in claims],
            "fresh_claims": sum(claim.fresh for claim in claims),
            "stale_claims": sum(not claim.fresh for claim in claims),
            "belief_revisions": [item.to_dict() for item in self.recent_revisions(limit=20)],
            "agency_attributions": [item.to_dict() for item in self.recent_attributions(20)],
            "note": "Evidence-linked functional self-knowledge; not consciousness or subjective experience.",
        }
