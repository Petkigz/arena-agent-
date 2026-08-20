"""Phase 3: evidence-backed beliefs and belief revision.

Phase 1A additions:
- Evidence-weighted confidence recalculation with time decay
- Provenance weighting (direct probes > environmental > self-reported)
- Staleness detection for beliefs with aging evidence
- Periodic decay maintenance

Phase 1 (provenance hardening):
- Uses canonical SourceType enum for provenance weights
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from .source_types import SourceType, PROVENANCE_WEIGHTS, DEFAULT_PROVENANCE_WEIGHT


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Time decay half-life in hours (evidence loses half its weight after this period)
DECAY_HALF_LIFE_HOURS = 24.0


@dataclass
class Evidence:
    """
    Raw evidence from any source.
    
    This is the base class for all evidence. Raw Evidence objects can be
    created from any source (admissible or inadmissible). Only AdmissibleEvidence
    (a subclass) can enter BeliefStore.
    
    Phase 1: source is a canonical SourceType enum value
    Phase 2: observation_type is required (no default)
    """
    source: str
    value: Any
    confidence: float = 1.0
    observed_at: str = field(default_factory=_now)
    evidence_id: str = field(default_factory=lambda: uuid4().hex)
    observation_id: Optional[str] = None  # Links back to WorldModel Observation
    observation_type: Optional[str] = None  # Phase 2: explicit classification (required for new code)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def age_hours(self, now: Optional[datetime] = None) -> float:
        """Hours since this evidence was observed."""
        reference = now or datetime.now(timezone.utc)
        try:
            observed = datetime.fromisoformat(self.observed_at)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            return max(0.0, (reference - observed).total_seconds() / 3600.0)
        except (ValueError, TypeError):
            return 0.0

    def time_weight(self, now: Optional[datetime] = None, half_life: float = DECAY_HALF_LIFE_HOURS) -> float:
        """Time decay weight: 1.0 for fresh evidence, decaying toward 0.1."""
        age = self.age_hours(now)
        return max(0.1, 1.0 / (1.0 + age / half_life))

    def provenance_weight(self) -> float:
        """Source reliability weight using canonical SourceType enum.
        
        Phase 1: Uses exact enum matching instead of substring matching.
        Falls back to DEFAULT_PROVENANCE_WEIGHT for unknown sources.
        """
        source_type = SourceType.from_string(self.source)
        return PROVENANCE_WEIGHTS.get(source_type, DEFAULT_PROVENANCE_WEIGHT)

    def weighted_score(self, now: Optional[datetime] = None) -> float:
        """Combined confidence × time_decay × provenance_weight."""
        return self.confidence * self.time_weight(now) * self.provenance_weight()


@dataclass
class AdmissibleEvidence(Evidence):
    """
    Evidence that has passed the admissibility gate and can enter BeliefStore.
    
    This is a marker subclass that indicates the evidence has been validated
    as admissible (direct/environmental observation from an authoritative source).
    
    Phase 3: Only AdmissibleEvidence can be passed to BeliefStore.observe().
    This provides structural enforcement — it's impossible at the type level
    for inadmissible evidence to enter the belief system.
    
    Construction:
        Use AdmissibleEvidence.from_evidence() to create from a validated Evidence object.
        This is called by BeliefEngine.ingest() after checking admissibility.
    """
    
    @classmethod
    def from_evidence(cls, evidence: Evidence) -> 'AdmissibleEvidence':
        """
        Create AdmissibleEvidence from a validated Evidence object.
        
        This should only be called after the evidence has passed the admissibility
        gate (checked by BeliefEngine.is_admissible()).
        """
        return cls(
            source=evidence.source,
            value=evidence.value,
            confidence=evidence.confidence,
            observed_at=evidence.observed_at,
            evidence_id=evidence.evidence_id,
            observation_id=evidence.observation_id,
            observation_type=evidence.observation_type,
        )


@dataclass
class Belief:
    subject: str
    predicate: str
    value: Any
    confidence: float
    evidence: List[Evidence] = field(default_factory=list)
    belief_id: str = field(default_factory=lambda: uuid4().hex)
    updated_at: str = field(default_factory=_now)


class BeliefStore:
    """Belief layer with optional SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._beliefs: Dict[tuple[str, str], Belief] = {}
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS persistent_beliefs (
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (subject, predicate)
            )
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT subject, predicate, value, confidence, evidence, updated_at FROM persistent_beliefs")
        rows = cursor.fetchall()
        for s, p, v, conf, ev_json, updated in rows:
            try:
                val = json.loads(v)
            except Exception:
                val = v

            ev_list = []
            if ev_json:
                try:
                    ev_items = json.loads(ev_json)
                    for item in ev_items:
                        ev_list.append(Evidence(
                            source=item.get("source", "system"),
                            value=item.get("value"),
                            confidence=item.get("confidence", 1.0),
                            observed_at=item.get("observed_at", updated),
                            evidence_id=item.get("evidence_id", uuid4().hex),
                            observation_id=item.get("observation_id"),
                        ))
                except Exception:
                    pass

            b = Belief(s, p, val, conf, evidence=ev_list, updated_at=updated)
            self._beliefs[(s, p)] = b
        conn.close()

    def _save_to_db(self, belief: Belief) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        val_str = json.dumps(belief.value) if not isinstance(belief.value, str) else belief.value
        ev_json = json.dumps([
            {
                "source": e.source,
                "value": e.value,
                "confidence": e.confidence,
                "observed_at": e.observed_at,
                "evidence_id": e.evidence_id,
                "observation_id": e.observation_id,
            } for e in belief.evidence
        ])
        cursor.execute("""
            INSERT OR REPLACE INTO persistent_beliefs (subject, predicate, value, confidence, evidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (belief.subject, belief.predicate, val_str, belief.confidence, ev_json, belief.updated_at))
        conn.commit()
        conn.close()

    def observe(self, subject: str, predicate: str, evidence: AdmissibleEvidence) -> Belief:
        """
        Add admissible evidence to a belief.
        
        Phase 3: Only accepts AdmissibleEvidence (not raw Evidence).
        This provides structural enforcement — inadmissible evidence cannot
        enter the belief system at the type level.
        
        observe() is a thin wrapper that:
        1. Appends the admissible evidence to the belief
        2. Calls revise() to recompute value and confidence from all evidence
        
        This ensures observe() and revise() always produce the same result.
        
        Args:
            subject: The entity being observed
            predicate: The property being observed
            evidence: AdmissibleEvidence that has passed the admissibility gate
        
        Returns:
            The updated Belief object
        """
        key = (subject, predicate)
        current = self._beliefs.get(key)
        
        if current is None:
            # First evidence: create belief with initial value
            belief = Belief(subject, predicate, evidence.value, evidence.confidence, [evidence])
            self._beliefs[key] = belief
            self._save_to_db(belief)
            return belief
        
        # Append admissible evidence
        current.evidence.append(evidence)
        current.updated_at = _now()
        
        # Recompute belief via revise() — authoritative calculation
        revised = self.revise(subject, predicate)
        return revised if revised else current

    def get(self, subject: str, predicate: str) -> Optional[Belief]:
        return self._beliefs.get((subject, predicate))

    def list(self, subject: Optional[str] = None) -> List[Belief]:
        values = list(self._beliefs.values())
        if subject is not None:
            values = [belief for belief in values if belief.subject == subject]
        return values

    def contradictions(self, subject: Optional[str] = None) -> List[Dict[str, Any]]:
        result = []
        for belief in self.list(subject):
            values = {repr(item.value) for item in belief.evidence}
            if len(values) > 1:
                result.append({"belief": belief, "values": values})
        return result

    # ── Phase 1A: Evidence-Weighted Belief Revision ────────────────────

    def revise(self, subject: str, predicate: str, now: Optional[datetime] = None) -> Optional[Belief]:
        """
        Recalculate belief value and confidence from ALL evidence with
        time decay and provenance weighting.

        Deduplicates by source: for each (value, source) pair, only the
        most recent observation counts. This prevents repeated observations
        from the same source from artificially inflating certainty.

        Unlike observe() (which does incremental updates), this recomputes
        from scratch — ensuring stale evidence doesn't dominate fresh evidence.
        """
        key = (subject, predicate)
        belief = self._beliefs.get(key)
        if not belief or not belief.evidence:
            return belief

        reference = now or datetime.now(timezone.utc)

        # Deduplicate by source: each source gets ONE vote — its most recent
        # observation regardless of value. This ensures each independent source
        # contributes equally, preventing repeated samples from inflating certainty.
        latest_by_source: Dict[str, Evidence] = {}
        for ev in belief.evidence:
            existing = latest_by_source.get(ev.source)
            if existing is None or ev.observed_at >= existing.observed_at:
                latest_by_source[ev.source] = ev

        # Score each distinct value by weighted independent evidence
        value_scores: Dict[Any, float] = {}
        for ev in latest_by_source.values():
            ws = ev.weighted_score(reference)
            found_key = None
            for existing_val in value_scores:
                if existing_val == ev.value:
                    found_key = existing_val
                    break
            if found_key is not None:
                value_scores[found_key] += ws
            else:
                value_scores[ev.value] = ws

        if not value_scores:
            return belief

        # Select value with highest total weighted independent evidence.
        # Tie-break: prefer the value with the most recent observation.
        best_val = None
        best_score = -1.0
        best_recency = ""
        for val, score in value_scores.items():
            # Find most recent observation for this value
            val_recency = max(
                (ev.observed_at for ev in latest_by_source.values() if ev.value == val),
                default=""
            )
            if score > best_score or (score == best_score and val_recency > best_recency):
                best_val = val
                best_score = score
                best_recency = val_recency
        total_score = sum(value_scores.values())

        # Confidence = proportion of weighted independent evidence supporting this value
        belief.value = best_val
        belief.confidence = round(best_score / total_score, 4) if total_score > 0 else 0.0
        belief.updated_at = _now()
        self._save_to_db(belief)
        return belief

    def is_stale(self, subject: str, predicate: str,
                 max_age_hours: float = DECAY_HALF_LIFE_HOURS * 2,
                 now: Optional[datetime] = None) -> bool:
        """
        Check if a belief's most recent evidence is older than max_age_hours.
        Stale beliefs should be re-verified through fresh observation.
        """
        key = (subject, predicate)
        belief = self._beliefs.get(key)
        if not belief or not belief.evidence:
            return True

        reference = now or datetime.now(timezone.utc)
        newest_age = min(ev.age_hours(reference) for ev in belief.evidence)
        return newest_age > max_age_hours

    def stale_beliefs(self, max_age_hours: float = DECAY_HALF_LIFE_HOURS * 2,
                      subject: Optional[str] = None,
                      now: Optional[datetime] = None) -> List[Belief]:
        """List all beliefs whose most recent evidence is older than max_age_hours."""
        result = []
        for belief in self.list(subject):
            if self.is_stale(belief.subject, belief.predicate, max_age_hours, now):
                result.append(belief)
        return result

    def decay_all(self, now: Optional[datetime] = None) -> int:
        """
        Recalculate all beliefs with current time decay.
        Returns the number of beliefs whose value or confidence changed.
        """
        changed = 0
        reference = now or datetime.now(timezone.utc)
        for key in list(self._beliefs.keys()):
            belief = self._beliefs[key]
            old_val, old_conf = belief.value, belief.confidence
            self.revise(belief.subject, belief.predicate, now=reference)
            if belief.value != old_val or abs(belief.confidence - old_conf) > 0.001:
                changed += 1
        return changed

    def evidence_summary(self, subject: str, predicate: str) -> Optional[Dict[str, Any]]:
        """
        Return a structured summary of all evidence for a belief,
        including weighted scores, staleness indicators, and observation links.
        """
        key = (subject, predicate)
        belief = self._beliefs.get(key)
        if not belief:
            return None

        now = datetime.now(timezone.utc)
        evidence_details = []
        for ev in belief.evidence:
            evidence_details.append({
                "source": ev.source,
                "value": ev.value,
                "confidence": ev.confidence,
                "observed_at": ev.observed_at,
                "evidence_id": ev.evidence_id,
                "observation_id": ev.observation_id,
                "age_hours": round(ev.age_hours(now), 2),
                "time_weight": round(ev.time_weight(now), 3),
                "provenance_weight": ev.provenance_weight(),
                "weighted_score": round(ev.weighted_score(now), 4),
            })

        return {
            "subject": subject,
            "predicate": predicate,
            "current_value": belief.value,
            "current_confidence": belief.confidence,
            "evidence_count": len(belief.evidence),
            "is_stale": self.is_stale(subject, predicate, now=now),
            "evidence": evidence_details,
        }

    def trace_provenance(self, subject: str, predicate: str) -> Optional[List[Dict[str, Any]]]:
        """
        Return the full provenance chain for a belief: each piece of evidence
        with its observation_id link back to WorldModel.

        Returns None if the belief doesn't exist.
        Returns a list of evidence records sorted by observed_at (newest first),
        each containing the observation_id for WorldModel lookup.
        """
        key = (subject, predicate)
        belief = self._beliefs.get(key)
        if not belief:
            return None

        chain = []
        for ev in sorted(belief.evidence, key=lambda e: e.observed_at, reverse=True):
            chain.append({
                "evidence_id": ev.evidence_id,
                "observation_id": ev.observation_id,
                "source": ev.source,
                "value": ev.value,
                "confidence": ev.confidence,
                "observed_at": ev.observed_at,
            })
        return chain
