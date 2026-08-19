"""Phase 4: Verified Reflection System.

Tracks verification quality of beliefs and calculates confidence
based on verification methods used. Ensures reflections are backed
by verified evidence with explicit provenance chains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class VerificationMethod(str, Enum):
    """Methods used to verify a belief or reflection."""
    
    # Direct verification methods (highest confidence)
    DIRECT_OBSERVATION = "direct_observation"  # Direct system probe
    EXECUTION_RESULT = "execution_result"  # Tool execution output
    FILE_CONTENTS = "file_contents"  # Read file contents
    
    # Indirect verification methods (medium confidence)
    ENVIRONMENTAL_PROBE = "environmental_probe"  # Environmental sensor
    PROCESS_INSPECTION = "process_inspection"  # Process list inspection
    SYSTEM_CALL = "system_call"  # System API call
    
    # Inferred verification methods (lower confidence)
    INFERENCE = "inference"  # Logical inference from other beliefs
    PATTERN_MATCH = "pattern_match"  # Pattern matching
    HEURISTIC = "heuristic"  # Heuristic-based
    
    # Unverified (lowest confidence)
    SELF_REPORTED = "self_reported"  # User or LLM claim
    UNVERIFIED = "unverified"  # No verification


# Confidence weights for each verification method
VERIFICATION_WEIGHTS: Dict[VerificationMethod, float] = {
    VerificationMethod.DIRECT_OBSERVATION: 1.0,
    VerificationMethod.EXECUTION_RESULT: 0.95,
    VerificationMethod.FILE_CONTENTS: 0.95,
    VerificationMethod.ENVIRONMENTAL_PROBE: 0.85,
    VerificationMethod.PROCESS_INSPECTION: 0.85,
    VerificationMethod.SYSTEM_CALL: 0.80,
    VerificationMethod.INFERENCE: 0.65,
    VerificationMethod.PATTERN_MATCH: 0.60,
    VerificationMethod.HEURISTIC: 0.55,
    VerificationMethod.SELF_REPORTED: 0.30,
    VerificationMethod.UNVERIFIED: 0.10,
}


@dataclass
class VerificationRecord:
    """Record of a single verification event."""
    
    method: VerificationMethod
    evidence_id: Optional[str] = None  # Links to Evidence.evidence_id
    verified_at: str = field(default_factory=_now)
    details: Optional[str] = None
    confidence: float = 1.0
    
    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
    
    def weighted_confidence(self) -> float:
        """Calculate confidence weighted by verification method."""
        method_weight = VERIFICATION_WEIGHTS.get(self.method, 0.1)
        return self.confidence * method_weight


@dataclass
class VerifiedReflection:
    """
    A reflection or belief with explicit verification provenance.
    
    Tracks all verification methods used to establish confidence in
    this reflection. Confidence is calculated from the verification
    chain, not assigned arbitrarily.
    
    Phase 4: Part of provenance hardening system.
    """
    
    content: str
    reflection_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    verifications: List[VerificationRecord] = field(default_factory=list)
    source_belief_ids: List[str] = field(default_factory=list)  # Links to Belief.belief_id
    tags: List[str] = field(default_factory=list)
    
    def add_verification(
        self,
        method: VerificationMethod,
        evidence_id: Optional[str] = None,
        details: Optional[str] = None,
        confidence: float = 1.0,
    ) -> VerificationRecord:
        """Add a verification record to this reflection."""
        record = VerificationRecord(
            method=method,
            evidence_id=evidence_id,
            details=details,
            confidence=confidence,
        )
        self.verifications.append(record)
        self.updated_at = _now()
        return record
    
    def verification_quality(self) -> float:
        """
        Calculate overall verification quality (0.0 to 1.0).
        
        Uses the highest-weighted verification method, with a small
        bonus for multiple independent verifications.
        """
        if not self.verifications:
            return 0.0
        
        # Get the best single verification
        best_weighted = max(v.weighted_confidence() for v in self.verifications)
        
        # Bonus for multiple independent verifications (up to 0.1)
        unique_methods = len(set(v.method for v in self.verifications))
        diversity_bonus = min(0.1, unique_methods * 0.02)
        
        return min(1.0, best_weighted + diversity_bonus)
    
    def confidence(self) -> float:
        """
        Calculate confidence based on verification quality.
        
        This is the authoritative confidence calculation - not
        assigned arbitrarily but derived from verification provenance.
        """
        return self.verification_quality()
    
    def is_verified(self, threshold: float = 0.5) -> bool:
        """Check if this reflection meets the verification threshold."""
        return self.verification_quality() >= threshold
    
    def primary_verification_method(self) -> Optional[VerificationMethod]:
        """Get the highest-weighted verification method used."""
        if not self.verifications:
            return None
        
        best = max(self.verifications, key=lambda v: v.weighted_confidence())
        return best.method
    
    def verification_summary(self) -> Dict[str, Any]:
        """Get a summary of verification provenance."""
        if not self.verifications:
            return {
                "verified": False,
                "quality": 0.0,
                "confidence": 0.0,
                "methods": [],
                "count": 0,
            }
        
        methods = [v.method.value for v in self.verifications]
        return {
            "verified": self.is_verified(),
            "quality": self.verification_quality(),
            "confidence": self.confidence(),
            "primary_method": self.primary_verification_method().value if self.primary_verification_method() else None,
            "methods": list(set(methods)),
            "count": len(self.verifications),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "reflection_id": self.reflection_id,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "verifications": [
                {
                    "method": v.method.value,
                    "evidence_id": v.evidence_id,
                    "verified_at": v.verified_at,
                    "details": v.details,
                    "confidence": v.confidence,
                }
                for v in self.verifications
            ],
            "source_belief_ids": self.source_belief_ids,
            "tags": self.tags,
            "verification_summary": self.verification_summary(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VerifiedReflection:
        """Deserialize from dictionary."""
        verifications = [
            VerificationRecord(
                method=VerificationMethod(v["method"]),
                evidence_id=v.get("evidence_id"),
                verified_at=v["verified_at"],
                details=v.get("details"),
                confidence=v["confidence"],
            )
            for v in data.get("verifications", [])
        ]
        
        return cls(
            content=data["content"],
            reflection_id=data["reflection_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            verifications=verifications,
            source_belief_ids=data.get("source_belief_ids", []),
            tags=data.get("tags", []),
        )


class VerifiedReflectionStore:
    """
    Storage and retrieval for verified reflections.
    
    Provides persistent storage and querying of reflections with
    their verification provenance chains.
    """
    
    def __init__(self, db_path: str = ":memory:"):
        """Initialize the reflection store."""
        import sqlite3
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()
    
    def _create_tables(self) -> None:
        """Create the reflections table if it doesn't exist."""
        import json
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS verified_reflections (
                reflection_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                verifications TEXT NOT NULL,
                source_belief_ids TEXT NOT NULL,
                tags TEXT NOT NULL,
                verification_quality REAL NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reflections_quality 
            ON verified_reflections(verification_quality)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reflections_created 
            ON verified_reflections(created_at)
        """)
        self.conn.commit()
    
    def store(self, reflection: VerifiedReflection) -> None:
        """Store a verified reflection."""
        import json
        
        self.conn.execute(
            """
            INSERT OR REPLACE INTO verified_reflections 
            (reflection_id, content, created_at, updated_at, verifications, 
             source_belief_ids, tags, verification_quality)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reflection.reflection_id,
                reflection.content,
                reflection.created_at,
                reflection.updated_at,
                json.dumps([
                    {
                        "method": v.method.value,
                        "evidence_id": v.evidence_id,
                        "verified_at": v.verified_at,
                        "details": v.details,
                        "confidence": v.confidence,
                    }
                    for v in reflection.verifications
                ]),
                json.dumps(reflection.source_belief_ids),
                json.dumps(reflection.tags),
                reflection.verification_quality(),
            )
        )
        self.conn.commit()
    
    def get(self, reflection_id: str) -> Optional[VerifiedReflection]:
        """Retrieve a reflection by ID."""
        import json
        
        cursor = self.conn.execute(
            "SELECT * FROM verified_reflections WHERE reflection_id = ?",
            (reflection_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_reflection(row)
    
    def query(
        self,
        min_quality: float = 0.0,
        tags: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[VerifiedReflection]:
        """Query reflections with filters."""
        import json
        
        query = "SELECT * FROM verified_reflections WHERE verification_quality >= ?"
        params: List[Any] = [min_quality]
        
        if tags:
            # Query for reflections that have any of the specified tags
            tag_conditions = " OR ".join(["tags LIKE ?" for _ in tags])
            query += f" AND ({tag_conditions})"
            params.extend([f'%"{tag}"%' for tag in tags])
        
        query += " ORDER BY verification_quality DESC, updated_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = self.conn.execute(query, params)
        return [self._row_to_reflection(row) for row in cursor.fetchall()]
    
    def _row_to_reflection(self, row: tuple) -> VerifiedReflection:
        """Convert a database row to a VerifiedReflection object."""
        import json
        
        verifications_data = json.loads(row[4])
        verifications = [
            VerificationRecord(
                method=VerificationMethod(v["method"]),
                evidence_id=v.get("evidence_id"),
                verified_at=v["verified_at"],
                details=v.get("details"),
                confidence=v["confidence"],
            )
            for v in verifications_data
        ]
        
        return VerifiedReflection(
            content=row[1],
            reflection_id=row[0],
            created_at=row[2],
            updated_at=row[3],
            verifications=verifications,
            source_belief_ids=json.loads(row[5]),
            tags=json.loads(row[6]),
        )
    
    def count(self, min_quality: float = 0.0) -> int:
        """Count reflections meeting quality threshold."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM verified_reflections WHERE verification_quality >= ?",
            (min_quality,)
        )
        return cursor.fetchone()[0]
    
    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
