"""Phase 2: lightweight persistent world model.

The world model stores what Arena currently knows about entities, their
relationships, and observations. It deliberately avoids an in-memory graph or
external database so the system remains suitable for a 16 GB RAM / 8 GB VRAM
machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Entity:
    id: str
    name: str
    entity_type: str = "unknown"
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    first_seen: str = field(default_factory=_now)
    last_seen: str = field(default_factory=_now)


@dataclass
class Relationship:
    id: str
    subject_id: str
    predicate: str
    object_id: str
    confidence: float = 1.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    last_confirmed: str = field(default_factory=_now)


@dataclass
class Observation:
    id: str
    subject: str
    predicate: str
    value: Any
    source: str = "unknown"
    confidence: float = 1.0
    observed_at: str = field(default_factory=_now)
    task_id: Optional[str] = None


class WorldModel:
    """Persistent, queryable representation of Arena's external context."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or str(settings.DB_PATH)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS world_entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    attributes TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_world_entities_name
                    ON world_entities(name);
                CREATE TABLE IF NOT EXISTS world_relationships (
                    id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    attributes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_confirmed TEXT NOT NULL,
                    UNIQUE(subject_id, predicate, object_id)
                );
                CREATE INDEX IF NOT EXISTS idx_world_rel_subject
                    ON world_relationships(subject_id, predicate);
                CREATE TABLE IF NOT EXISTS world_observations (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    observed_at TEXT NOT NULL,
                    task_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_world_obs_subject
                    ON world_observations(subject, observed_at DESC);
                """
            )

    @staticmethod
    def _check_confidence(value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    def upsert_entity(
        self,
        name: str,
        entity_type: str = "unknown",
        attributes: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        entity_id: Optional[str] = None,
    ) -> Entity:
        self._check_confidence(confidence)
        now = _now()
        attributes = attributes or {}
        with self._connect() as conn:
            row = None
            if entity_id:
                row = conn.execute("SELECT * FROM world_entities WHERE id = ?", (entity_id,)).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM world_entities WHERE name = ? AND entity_type = ?",
                    (name, entity_type),
                ).fetchone()

            if row:
                merged = json.loads(row["attributes"])
                merged.update(attributes)
                conn.execute(
                    """UPDATE world_entities
                       SET attributes = ?, confidence = ?, last_seen = ?
                       WHERE id = ?""",
                    (json.dumps(merged), confidence, now, row["id"]),
                )
                entity_id = row["id"]
                first_seen = row["first_seen"]
                attributes = merged
            else:
                entity_id = entity_id or uuid4().hex
                first_seen = now
                conn.execute(
                    """INSERT INTO world_entities
                       (id, name, entity_type, attributes, confidence, first_seen, last_seen)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (entity_id, name, entity_type, json.dumps(attributes), confidence, first_seen, now),
                )
            return Entity(entity_id, name, entity_type, attributes, confidence, first_seen, now)

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM world_entities WHERE id = ?", (entity_id,)).fetchone()
        if not row:
            return None
        return Entity(row["id"], row["name"], row["entity_type"], json.loads(row["attributes"]),
                      row["confidence"], row["first_seen"], row["last_seen"])

    def find_entities(self, name: Optional[str] = None, entity_type: Optional[str] = None) -> List[Entity]:
        query = "SELECT * FROM world_entities WHERE 1=1"
        params: List[Any] = []
        if name is not None:
            query += " AND name = ?"
            params.append(name)
        if entity_type is not None:
            query += " AND entity_type = ?"
            params.append(entity_type)
        query += " ORDER BY last_seen DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Entity(r["id"], r["name"], r["entity_type"], json.loads(r["attributes"]),
                       r["confidence"], r["first_seen"], r["last_seen"]) for r in rows]

    def observe(self, observation: Observation) -> Observation:
        self._check_confidence(observation.confidence)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO world_observations
                   (id, subject, predicate, value, source, confidence, observed_at, task_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (observation.id, observation.subject, observation.predicate,
                 json.dumps(observation.value), observation.source,
                 observation.confidence, observation.observed_at, observation.task_id),
            )
        return observation

    def recent_observations(self, subject: Optional[str] = None, limit: int = 50) -> List[Observation]:
        query = "SELECT * FROM world_observations"
        params: List[Any] = []
        if subject:
            query += " WHERE subject = ?"
            params.append(subject)
        query += " ORDER BY observed_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Observation(r["id"], r["subject"], r["predicate"], json.loads(r["value"]),
                            r["source"], r["confidence"], r["observed_at"], r["task_id"])
                for r in rows]

    def relate(
        self,
        subject_id: str,
        predicate: str,
        object_id: str,
        confidence: float = 1.0,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Relationship:
        self._check_confidence(confidence)
        now = _now()
        attributes = attributes or {}
        relationship_id = uuid4().hex
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM world_relationships WHERE subject_id = ? AND predicate = ? AND object_id = ?",
                (subject_id, predicate, object_id),
            ).fetchone()
            if row:
                relationship_id = row["id"]
                merged = json.loads(row["attributes"])
                merged.update(attributes)
                conn.execute(
                    """UPDATE world_relationships
                       SET confidence = ?, attributes = ?, last_confirmed = ?
                       WHERE id = ?""",
                    (confidence, json.dumps(merged), now, relationship_id),
                )
                attributes = merged
                created_at = row["created_at"]
            else:
                created_at = now
                conn.execute(
                    """INSERT INTO world_relationships
                       (id, subject_id, predicate, object_id, confidence, attributes, created_at, last_confirmed)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (relationship_id, subject_id, predicate, object_id, confidence,
                     json.dumps(attributes), created_at, now),
                )
        return Relationship(relationship_id, subject_id, predicate, object_id, confidence,
                            attributes, created_at, now)

    def related(self, subject_id: str, predicate: Optional[str] = None) -> List[Relationship]:
        query = "SELECT * FROM world_relationships WHERE subject_id = ?"
        params: List[Any] = [subject_id]
        if predicate:
            query += " AND predicate = ?"
            params.append(predicate)
        query += " ORDER BY last_confirmed DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Relationship(r["id"], r["subject_id"], r["predicate"], r["object_id"],
                             r["confidence"], json.loads(r["attributes"]),
                             r["created_at"], r["last_confirmed"]) for r in rows]

    def snapshot(self) -> Dict[str, Any]:
        with self._connect() as conn:
            entities = conn.execute("SELECT COUNT(*) FROM world_entities").fetchone()[0]
            relationships = conn.execute("SELECT COUNT(*) FROM world_relationships").fetchone()[0]
            observations = conn.execute("SELECT COUNT(*) FROM world_observations").fetchone()[0]
        return {"entities": entities, "relationships": relationships,
                "observations": observations, "updated_at": _now()}
