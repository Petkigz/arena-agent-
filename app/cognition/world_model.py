"""Phase 2: lightweight persistent world model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import sqlite3
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.cognition.source_types import ObservationType


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
    observation_type: str = "direct"  # 'direct', 'environmental', 'self_reported', 'inferred'


@dataclass
class WorldChange:
    subject: str
    predicate: str
    previous_value: Any
    current_value: Any
    observed_at: str
    source: str
    confidence: float
    observation_id: str


class WorldModel:
    """Persistent, queryable representation of Arena's external context.

    Invariant: Entity attributes hold identity/descriptor data only (file_path,
    aliases, etc.). Environmental state (status, source, observation_type) is
    represented exclusively through Observations with provenance. This prevents
    un-provenanced state from leaking into downstream consumers (BeliefEngine,
    MemoryLearner, ReflectionEngine, etc.) through entity attributes.
    """

    # Keys that represent environmental state and must NOT appear in entity attributes.
    # These belong exclusively in Observations where provenance is enforced.
    ENTITY_STATE_KEYS = frozenset({"status", "source", "observation_type"})

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or str(settings.DB_PATH)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS world_entities (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, entity_type TEXT NOT NULL,
                    attributes TEXT NOT NULL, confidence REAL NOT NULL,
                    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_world_entities_name ON world_entities(name);
                CREATE TABLE IF NOT EXISTS world_relationships (
                    id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, predicate TEXT NOT NULL,
                    object_id TEXT NOT NULL, confidence REAL NOT NULL, attributes TEXT NOT NULL,
                    created_at TEXT NOT NULL, last_confirmed TEXT NOT NULL,
                    UNIQUE(subject_id, predicate, object_id)
                );
                CREATE INDEX IF NOT EXISTS idx_world_rel_subject ON world_relationships(subject_id, predicate);
                CREATE TABLE IF NOT EXISTS world_observations (
                    id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL,
                    value TEXT NOT NULL, source TEXT NOT NULL, confidence REAL NOT NULL,
                    observed_at TEXT NOT NULL, task_id TEXT, observation_type TEXT NOT NULL DEFAULT 'direct'
                );
                CREATE INDEX IF NOT EXISTS idx_world_obs_subject ON world_observations(subject, observed_at DESC);
            """)
            try:
                conn.execute("ALTER TABLE world_observations ADD COLUMN observation_type TEXT NOT NULL DEFAULT 'direct'")
            except Exception:
                pass

    @staticmethod
    def _check_confidence(value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @staticmethod
    def _entity(row: sqlite3.Row) -> Entity:
        return Entity(row["id"], row["name"], row["entity_type"], json.loads(row["attributes"]),
                      row["confidence"], row["first_seen"], row["last_seen"])

    @staticmethod
    def _observation(row: sqlite3.Row) -> Observation:
        obs_type = row["observation_type"] if "observation_type" in row.keys() else "direct"
        return Observation(
            id=row["id"],
            subject=row["subject"],
            predicate=row["predicate"],
            value=json.loads(row["value"]),
            source=row["source"],
            confidence=row["confidence"],
            observed_at=row["observed_at"],
            task_id=row["task_id"],
            observation_type=obs_type
        )

    @classmethod
    def _strip_state_keys(cls, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Remove state keys from entity attributes. State belongs in Observations."""
        return {k: v for k, v in attributes.items() if k not in cls.ENTITY_STATE_KEYS}

    def upsert_entity(self, name: str, entity_type: str = "unknown",
                      attributes: Optional[Dict[str, Any]] = None,
                      confidence: float = 1.0, entity_id: Optional[str] = None) -> Entity:
        self._check_confidence(confidence)
        now = _now()
        # Strip state keys — environmental state belongs in Observations, not entity attributes
        attributes = self._strip_state_keys(attributes or {})
        with self._connect() as conn:
            row = None
            if entity_id:
                row = conn.execute("SELECT * FROM world_entities WHERE id = ?", (entity_id,)).fetchone()
            if row is None:
                row = conn.execute("SELECT * FROM world_entities WHERE name = ? AND entity_type = ?",
                                   (name, entity_type)).fetchone()
            if row:
                merged = json.loads(row["attributes"]); merged.update(attributes)
                merged = self._strip_state_keys(merged)
                conn.execute("UPDATE world_entities SET attributes=?, confidence=?, last_seen=? WHERE id=?",
                             (json.dumps(merged), confidence, now, row["id"]))
                entity_id, first_seen, attributes = row["id"], row["first_seen"], merged
            else:
                entity_id, first_seen = entity_id or uuid4().hex, now
                conn.execute("INSERT INTO world_entities VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (entity_id, name, entity_type, json.dumps(attributes), confidence, first_seen, now))
        return Entity(entity_id, name, entity_type, attributes, confidence, first_seen, now)

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM world_entities WHERE id = ?", (entity_id,)).fetchone()
        return self._entity(row) if row else None

    def get_entity_state(self, entity_name: str,
                          predicate: str = "status") -> Optional[Dict[str, Any]]:
        """
        Derive entity state from the latest Observation, not from entity attributes.

        This is the authoritative way to read environmental state for an entity.
        Returns None if no observation exists (state is unknown).

        Returns dict with: value, source, confidence, observation_type, observed_at
        """
        obs = self.latest_observation(entity_name, predicate)
        if obs is None:
            return None
        return {
            "value": obs.value,
            "source": obs.source,
            "confidence": obs.confidence,
            "observation_type": obs.observation_type,
            "observed_at": obs.observed_at,
        }

    def find_entities(self, name: Optional[str] = None, entity_type: Optional[str] = None) -> List[Entity]:
        query, params = "SELECT * FROM world_entities WHERE 1=1", []
        if name is not None:
            query += " AND name = ?"; params.append(name)
        if entity_type is not None:
            query += " AND entity_type = ?"; params.append(entity_type)
        query += " ORDER BY last_seen DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._entity(row) for row in rows]

    def resolve_entity(self, name: str, entity_type: Optional[str] = None) -> Optional[Entity]:
        """Resolve exact names first; aliases can be supplied as an entity attribute."""
        exact = self.find_entities(name, entity_type)
        if exact:
            return exact[0]
        candidates = self.find_entities(entity_type=entity_type)
        needle = name.casefold().strip()
        for entity in candidates:
            aliases = entity.attributes.get("aliases", [])
            if any(str(alias).casefold().strip() == needle for alias in aliases):
                return entity
        return None

    def observe(self, observation: Observation) -> Observation:
        self._check_confidence(observation.confidence)
        obs_type = getattr(observation, "observation_type", "direct")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO world_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (observation.id, observation.subject, observation.predicate,
                 json.dumps(observation.value), observation.source, observation.confidence,
                 observation.observed_at, observation.task_id, obs_type)
            )
        return observation

    def recent_observations(self, subject: Optional[str] = None, limit: int = 50) -> List[Observation]:
        limit = max(1, min(limit, 1000))
        query, params = "SELECT * FROM world_observations", []
        if subject:
            query += " WHERE subject = ?"; params.append(subject)
        query += " ORDER BY observed_at DESC LIMIT ?"; params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._observation(row) for row in rows]

    def latest_observation(self, subject: str, predicate: str) -> Optional[Observation]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM world_observations WHERE subject=? AND predicate=? ORDER BY observed_at DESC LIMIT 1",
                               (subject, predicate)).fetchone()
        return self._observation(row) if row else None

    def changes_for(self, subject: Optional[str] = None, predicate: Optional[str] = None,
                    limit: int = 50) -> List[WorldChange]:
        observations = list(reversed(self.recent_observations(subject, max(limit * 3, 10))))
        grouped: Dict[tuple[str, str], List[Observation]] = {}
        for obs in observations:
            if predicate is not None and obs.predicate != predicate:
                continue
            grouped.setdefault((obs.subject, obs.predicate), []).append(obs)
        changes: List[WorldChange] = []
        for (obs_subject, obs_predicate), history in grouped.items():
            for previous, current in zip(history, history[1:]):
                if previous.value != current.value:
                    changes.append(WorldChange(obs_subject, obs_predicate, previous.value, current.value,
                                               current.observed_at, current.source, current.confidence, current.id))
        changes.sort(key=lambda item: item.observed_at, reverse=True)
        return changes[:limit]

    def relate(self, subject_id: str, predicate: str, object_id: str,
               confidence: float = 1.0, attributes: Optional[Dict[str, Any]] = None) -> Relationship:
        self._check_confidence(confidence)
        now, attributes = _now(), (attributes or {})
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM world_relationships WHERE subject_id=? AND predicate=? AND object_id=?",
                               (subject_id, predicate, object_id)).fetchone()
            if row:
                relationship_id, created_at = row["id"], row["created_at"]
                merged = json.loads(row["attributes"]); merged.update(attributes); attributes = merged
                conn.execute("UPDATE world_relationships SET confidence=?, attributes=?, last_confirmed=? WHERE id=?",
                             (confidence, json.dumps(attributes), now, relationship_id))
            else:
                relationship_id, created_at = uuid4().hex, now
                conn.execute("INSERT INTO world_relationships VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (relationship_id, subject_id, predicate, object_id, confidence,
                              json.dumps(attributes), created_at, now))
        return Relationship(relationship_id, subject_id, predicate, object_id, confidence, attributes, created_at, now)

    def related(self, subject_id: str, predicate: Optional[str] = None) -> List[Relationship]:
        query, params = "SELECT * FROM world_relationships WHERE subject_id = ?", [subject_id]
        if predicate:
            query += " AND predicate = ?"; params.append(predicate)
        query += " ORDER BY last_confirmed DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Relationship(r["id"], r["subject_id"], r["predicate"], r["object_id"], r["confidence"],
                             json.loads(r["attributes"]), r["created_at"], r["last_confirmed"]) for r in rows]

    def related_to(self, object_id: str, predicate: Optional[str] = None) -> List[Relationship]:
        """Reverse traversal: find all entities that relate TO this entity.
        Answers 'what depends on Chrome?' or 'what contains this file?'."""
        query, params = "SELECT * FROM world_relationships WHERE object_id = ?", [object_id]
        if predicate:
            query += " AND predicate = ?"; params.append(predicate)
        query += " ORDER BY last_confirmed DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Relationship(r["id"], r["subject_id"], r["predicate"], r["object_id"], r["confidence"],
                             json.loads(r["attributes"]), r["created_at"], r["last_confirmed"]) for r in rows]

    def traverse(self, entity_id: str, predicate: Optional[str] = None,
                 max_depth: int = 3, direction: str = "outbound") -> List[Dict[str, Any]]:
        """
        Multi-hop graph traversal from an entity.
        direction: 'outbound' (follow subject→object), 'inbound' (follow object→subject), 'both'
        Returns list of {entity, relationship, depth} dicts.
        """
        max_depth = max(1, min(max_depth, 10))
        visited: set = set()
        results: List[Dict[str, Any]] = []
        queue: List[tuple] = [(entity_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth >= max_depth:
                continue
            visited.add(current_id)

            # Follow outbound edges
            if direction in ("outbound", "both"):
                for rel in self.related(current_id, predicate):
                    if rel.object_id not in visited:
                        target = self.get_entity(rel.object_id)
                        if target:
                            results.append({"entity": target, "relationship": rel, "depth": depth + 1, "direction": "outbound"})
                            queue.append((rel.object_id, depth + 1))

            # Follow inbound edges
            if direction in ("inbound", "both"):
                for rel in self.related_to(current_id, predicate):
                    if rel.subject_id not in visited:
                        source = self.get_entity(rel.subject_id)
                        if source:
                            results.append({"entity": source, "relationship": rel, "depth": depth + 1, "direction": "inbound"})
                            queue.append((rel.subject_id, depth + 1))

        return results

    def changes_since(self, since: str, subject: Optional[str] = None,
                      predicate: Optional[str] = None, limit: int = 100) -> List[WorldChange]:
        """Time-windowed change query: 'what changed since timestamp T?'"""
        query = "SELECT * FROM world_observations WHERE observed_at >= ?"
        params: list = [since]
        if subject:
            query += " AND subject = ?"; params.append(subject)
        if predicate:
            query += " AND predicate = ?"; params.append(predicate)
        query += " ORDER BY observed_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        observations = [self._observation(row) for row in rows]
        grouped: Dict[tuple, List[Observation]] = {}
        for obs in observations:
            grouped.setdefault((obs.subject, obs.predicate), []).append(obs)

        changes: List[WorldChange] = []
        for (subj, pred), history in grouped.items():
            for prev, curr in zip(history, history[1:]):
                if prev.value != curr.value:
                    changes.append(WorldChange(subj, pred, prev.value, curr.value,
                                               curr.observed_at, curr.source, curr.confidence, curr.id))
        return changes[:limit]

    def stale_observations(self, max_age_hours: float = 48.0,
                           subject: Optional[str] = None) -> List[Observation]:
        """Find observations whose latest value is older than max_age_hours."""
        now = datetime.now(timezone.utc)
        cutoff = (now - __import__("datetime").timedelta(hours=max_age_hours)).isoformat()

        query = "SELECT * FROM world_observations"
        params: list = []
        if subject:
            query += " WHERE subject = ?"; params.append(subject)
        query += " ORDER BY observed_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        # Group by (subject, predicate), keep latest
        latest: Dict[tuple, Observation] = {}
        for row in rows:
            obs = self._observation(row)
            key = (obs.subject, obs.predicate)
            if key not in latest:
                latest[key] = obs

        return [obs for obs in latest.values() if obs.observed_at < cutoff]

    def detect_contradictions(self, subject: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Phase 2D: Detect contradictory entity states.
        Returns pairs of observations that conflict with each other.
        """
        query = "SELECT * FROM world_observations"
        params: list = []
        if subject:
            query += " WHERE subject = ?"; params.append(subject)
        query += " ORDER BY observed_at DESC LIMIT 500"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        observations = [self._observation(row) for row in rows]

        # Group by (subject, predicate)
        grouped: Dict[tuple, List[Observation]] = {}
        for obs in observations:
            grouped.setdefault((obs.subject, obs.predicate), []).append(obs)

        contradictions: List[Dict[str, Any]] = []
        for (subj, pred), obs_list in grouped.items():
            if len(obs_list) < 2:
                continue
            # Check latest two observations for contradiction
            latest = obs_list[0]
            for other in obs_list[1:]:
                if latest.value != other.value and latest.source != other.source:
                    # Different values from different sources = potential contradiction
                    contradictions.append({
                        "subject": subj,
                        "predicate": pred,
                        "observation_a": {"value": latest.value, "source": latest.source,
                                          "confidence": latest.confidence, "observed_at": latest.observed_at},
                        "observation_b": {"value": other.value, "source": other.source,
                                          "confidence": other.confidence, "observed_at": other.observed_at},
                    })
                    break  # One contradiction per (subject, predicate) is enough
        return contradictions

    def query(self, *, entity_type: Optional[str] = None, name: Optional[str] = None,
              subject: Optional[str] = None, predicate: Optional[str] = None,
              limit: int = 50) -> Dict[str, Any]:
        """Compact world query for cognitive components; returns bounded results."""
        entities = self.find_entities(name=name, entity_type=entity_type)[:limit]
        observations = self.recent_observations(subject, limit)
        if predicate:
            observations = [o for o in observations if o.predicate == predicate][:limit]
        return {
            "entities": entities,
            "observations": observations,
            "changes": self.changes_for(subject, predicate, limit),
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._connect() as conn:
            counts = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("world_entities", "world_relationships", "world_observations")]
        return {"entities": counts[0], "relationships": counts[1], "observations": counts[2], "updated_at": _now()}

    # ── Phase 2A: Relationship Inference ──────────────────────────────

    # Standard relationship types
    REL_CONTAINS = "contains"
    REL_LOCATED_AT = "located_at"
    REL_DEPENDS_ON = "depends_on"
    REL_PRODUCES = "produces"
    REL_PARENT_OF = "parent_of"
    REL_LAUNCHED_BY = "launched_by"
    REL_OWNS = "owns"

    def infer_relationships_from_entity(self, entity: Entity) -> List[Relationship]:
        """
        Automatically infer relationships from entity attributes.
        Called when entities are created/updated by environmental probes.
        """
        inferred: List[Relationship] = []

        # File entities: infer located_at from file_path attribute
        if entity.entity_type == "file" and "file_path" in entity.attributes:
            file_path = entity.attributes["file_path"]
            if isinstance(file_path, str) and "/" in file_path:
                # Extract directory from path
                directory = "/".join(file_path.split("/")[:-1])
                if directory:
                    # Find or create directory entity
                    dir_entities = self.find_entities(name=directory, entity_type="directory")
                    if dir_entities:
                        dir_entity = dir_entities[0]
                        rel = self.relate(
                            entity.id, self.REL_LOCATED_AT, dir_entity.id,
                            confidence=1.0, attributes={"inferred_from": "file_path"}
                        )
                        inferred.append(rel)
                        # Also create reverse: directory contains file
                        rel2 = self.relate(
                            dir_entity.id, self.REL_CONTAINS, entity.id,
                            confidence=1.0, attributes={"inferred_from": "file_path"}
                        )
                        inferred.append(rel2)

        # Process entities: infer located_at from observation provenance
        if entity.entity_type == "process":
            # Check the latest observation for provenance, not entity attributes
            state = self.get_entity_state(entity.name, "status")
            if state and "os_process_probe" in str(state.get("source", "")):
                host_entities = self.find_entities(entity_type="host_environment")
                if host_entities:
                    rel = self.relate(
                        entity.id, self.REL_LOCATED_AT, host_entities[0].id,
                        confidence=0.9, attributes={"inferred_from": "process_probe"}
                    )
                    inferred.append(rel)

        return inferred

    def infer_relationships_from_observation(self, observation: Observation) -> List[Relationship]:
        """
        Infer relationships from observation content.
        E.g., a search result set observation creates 'produces' relationships.
        """
        inferred: List[Relationship] = []

        # Search result sets: filesystem produces files
        if observation.predicate == "search_result_set" and isinstance(observation.value, dict):
            result_set = observation.value
            items = result_set.get("items", [])
            for item in items:
                if isinstance(item, dict) and item.get("file_path"):
                    file_entities = self.find_entities(name=item.get("file_name", ""))
                    if file_entities:
                        # Find filesystem entity or use subject
                        fs_entities = self.find_entities(name=observation.subject)
                        if fs_entities:
                            rel = self.relate(
                                fs_entities[0].id, self.REL_PRODUCES, file_entities[0].id,
                                confidence=observation.confidence,
                                attributes={"inferred_from": "search_result_set"}
                            )
                            inferred.append(rel)

        return inferred

    def relationship_summary(self, entity_id: str) -> Dict[str, Any]:
        """Complete relationship summary for an entity (both directions)."""
        outbound = self.related(entity_id)
        inbound = self.related_to(entity_id)

        outbound_details = []
        for rel in outbound:
            target = self.get_entity(rel.object_id)
            outbound_details.append({
                "predicate": rel.predicate,
                "target_name": target.name if target else rel.object_id,
                "target_type": target.entity_type if target else "unknown",
                "confidence": rel.confidence,
            })

        inbound_details = []
        for rel in inbound:
            source = self.get_entity(rel.subject_id)
            inbound_details.append({
                "predicate": rel.predicate,
                "source_name": source.name if source else rel.subject_id,
                "source_type": source.entity_type if source else "unknown",
                "confidence": rel.confidence,
            })

        return {
            "entity_id": entity_id,
            "outbound_count": len(outbound),
            "inbound_count": len(inbound),
            "outbound": outbound_details,
            "inbound": inbound_details,
        }
