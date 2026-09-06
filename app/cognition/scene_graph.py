"""Deterministic scene state and bounded 2D physics predictions.

This module is deliberately an observation and simulation boundary. A scene
snapshot can preserve an object that is occluded or unobserved, but omission is
never treated as proof of absence. Physics results are predictions only; they
do not create execution evidence or change the real environment.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4


SCENE_SCHEMA_VERSION = 1
VISIBILITY_STATES = frozenset({"visible", "occluded", "unknown"})
RELATION_TYPES = frozenset({"supports", "supported_by", "contains", "owned_by", "touches"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class SceneGraphError(ValueError):
    """The scene graph input is invalid or cannot be interpreted safely."""


@dataclass(frozen=True)
class SceneObject:
    """A bounded 2D object hypothesis grounded by observation evidence."""

    object_id: str
    object_type: str
    x: float
    y: float
    width: float
    height: float
    mass: float = 1.0
    static: bool = False
    vx: float = 0.0
    vy: float = 0.0
    support_id: Optional[str] = None
    container_id: Optional[str] = None
    visibility: str = "visible"
    observed: bool = True
    observed_at: Optional[str] = None
    evidence_ids: Tuple[str, ...] = field(default_factory=tuple)
    properties: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.object_id or not self.object_type:
            raise SceneGraphError("scene objects require object_id and object_type")
        values = (self.x, self.y, self.width, self.height, self.mass, self.vx, self.vy)
        if not all(math.isfinite(float(value)) for value in values):
            raise SceneGraphError(f"scene object {self.object_id} contains a non-finite value")
        if self.width <= 0 or self.height <= 0:
            raise SceneGraphError(f"scene object {self.object_id} requires positive dimensions")
        if self.mass < 0:
            raise SceneGraphError(f"scene object {self.object_id} cannot have negative mass")
        if self.visibility not in VISIBILITY_STATES:
            raise SceneGraphError(f"unknown visibility state: {self.visibility}")

    @property
    def left(self) -> float:
        return self.x - self.width / 2.0

    @property
    def right(self) -> float:
        return self.x + self.width / 2.0

    @property
    def bottom(self) -> float:
        return self.y - self.height / 2.0

    @property
    def top(self) -> float:
        return self.y + self.height / 2.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "object_type": self.object_type,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "mass": self.mass,
            "static": self.static,
            "vx": self.vx,
            "vy": self.vy,
            "support_id": self.support_id,
            "container_id": self.container_id,
            "visibility": self.visibility,
            "observed": self.observed,
            "observed_at": self.observed_at,
            "evidence_ids": list(self.evidence_ids),
            "properties": dict(self.properties),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneObject":
        try:
            return cls(
                object_id=str(data["object_id"]),
                object_type=str(data["object_type"]),
                x=float(data["x"]),
                y=float(data["y"]),
                width=float(data["width"]),
                height=float(data["height"]),
                mass=float(data.get("mass", 1.0)),
                static=bool(data.get("static", False)),
                vx=float(data.get("vx", 0.0)),
                vy=float(data.get("vy", 0.0)),
                support_id=data.get("support_id"),
                container_id=data.get("container_id"),
                visibility=str(data.get("visibility", "unknown")),
                observed=bool(data.get("observed", False)),
                observed_at=data.get("observed_at"),
                evidence_ids=tuple(str(item) for item in data.get("evidence_ids", [])),
                properties=dict(data.get("properties", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SceneGraphError(f"invalid scene object: {exc}") from exc


@dataclass(frozen=True)
class SceneRelation:
    relation_type: str
    source_id: str
    target_id: str
    confidence: float = 1.0
    evidence_ids: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.relation_type not in RELATION_TYPES:
            raise SceneGraphError(f"unknown scene relation: {self.relation_type}")
        if not self.source_id or not self.target_id or self.source_id == self.target_id:
            raise SceneGraphError("scene relations require two distinct object IDs")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise SceneGraphError("scene relation confidence must be between 0 and 1")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relation_type": self.relation_type,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneRelation":
        return cls(
            relation_type=str(data["relation_type"]),
            source_id=str(data["source_id"]),
            target_id=str(data["target_id"]),
            confidence=float(data.get("confidence", 1.0)),
            evidence_ids=tuple(str(item) for item in data.get("evidence_ids", [])),
        )


class SceneGraph:
    """Deterministic, copyable scene graph with explicit observation semantics."""

    def __init__(self, *, revision: int = 0) -> None:
        self.schema_version = SCENE_SCHEMA_VERSION
        self.revision = int(revision)
        self.last_observation_id: Optional[str] = None
        self.objects: Dict[str, SceneObject] = {}
        self.relations: Dict[Tuple[str, str, str], SceneRelation] = {}

    def clone(self) -> "SceneGraph":
        return SceneGraph.from_dict(self.to_dict())

    def add_or_update(self, obj: SceneObject) -> None:
        previous = self.objects.get(obj.object_id)
        if previous and previous.support_id and previous.support_id != obj.support_id:
            self.remove_relation("supported_by", obj.object_id, previous.support_id)
        self.objects[obj.object_id] = obj
        if obj.support_id:
            self._set_relation(
                SceneRelation("supported_by", obj.object_id, obj.support_id, evidence_ids=obj.evidence_ids)
            )

    def _set_relation(self, relation: SceneRelation) -> None:
        if relation.source_id not in self.objects or relation.target_id not in self.objects:
            raise SceneGraphError("scene relation references an unknown object")
        key = (relation.relation_type, relation.source_id, relation.target_id)
        self.relations[key] = relation

    def add_relation(
        self,
        relation_type: str,
        source_id: str,
        target_id: str,
        *,
        confidence: float = 1.0,
        evidence_ids: Iterable[str] = (),
    ) -> SceneRelation:
        relation = SceneRelation(
            relation_type=relation_type,
            source_id=source_id,
            target_id=target_id,
            confidence=confidence,
            evidence_ids=tuple(str(item) for item in evidence_ids),
        )
        self._set_relation(relation)
        return relation

    def remove_relation(self, relation_type: str, source_id: str, target_id: str) -> None:
        self.relations.pop((relation_type, source_id, target_id), None)

    def apply_observation(
        self,
        observation_id: str,
        observed_objects: Sequence[SceneObject],
        *,
        occluded_ids: Iterable[str] = (),
        evidence_ids: Iterable[str] = (),
        observed_at: Optional[str] = None,
    ) -> None:
        """Reconcile a partial observation without deleting hidden objects.

        Objects explicitly observed become ``visible``. Known objects listed as
        occluded remain in the graph with their last state. Existing objects
        omitted from this partial observation become ``unknown`` rather than
        absent; omission is not evidence of nonexistence.
        """
        if not observation_id:
            raise SceneGraphError("observation_id is required")
        stamp = observed_at or _now()
        evidence = tuple(str(item) for item in evidence_ids)
        seen_ids = set()
        for item in observed_objects:
            if item.object_id in seen_ids:
                raise SceneGraphError(f"duplicate object in observation: {item.object_id}")
            seen_ids.add(item.object_id)
            merged_evidence = tuple(dict.fromkeys((*item.evidence_ids, *evidence)))
            self.add_or_update(replace(
                item,
                visibility="visible",
                observed=True,
                observed_at=stamp,
                evidence_ids=merged_evidence,
            ))

        occluded = set(str(item) for item in occluded_ids)
        unknown_occluded = sorted(occluded - set(self.objects))
        if unknown_occluded:
            raise SceneGraphError(f"cannot mark unknown objects occluded: {unknown_occluded}")
        for object_id in sorted(occluded):
            if object_id in seen_ids:
                raise SceneGraphError(f"object is both visible and occluded: {object_id}")
            current = self.objects[object_id]
            self.objects[object_id] = replace(
                current,
                visibility="occluded",
                observed=False,
                evidence_ids=tuple(dict.fromkeys((*current.evidence_ids, *evidence))),
            )

        for object_id, current in list(self.objects.items()):
            if object_id not in seen_ids and object_id not in occluded:
                self.objects[object_id] = replace(current, visibility="unknown", observed=False)
        self.last_observation_id = observation_id

    def object(self, object_id: str) -> SceneObject:
        try:
            return self.objects[object_id]
        except KeyError as exc:
            raise SceneGraphError(f"unknown scene object: {object_id}") from exc

    def to_dict(self) -> Dict[str, Any]:
        relations = [
            relation.to_dict()
            for _, relation in sorted(self.relations.items(), key=lambda item: item[0])
        ]
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "last_observation_id": self.last_observation_id,
            "objects": [
                obj.to_dict() for _, obj in sorted(self.objects.items(), key=lambda item: item[0])
            ],
            "relations": relations,
        }

    def digest(self) -> str:
        return _digest(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneGraph":
        if int(data.get("schema_version", -1)) != SCENE_SCHEMA_VERSION:
            raise SceneGraphError(
                f"unsupported scene graph schema_version={data.get('schema_version')}; "
                f"supported version is {SCENE_SCHEMA_VERSION}"
            )
        graph = cls(revision=int(data.get("revision", 0)))
        graph.last_observation_id = data.get("last_observation_id")
        for raw_object in data.get("objects", []):
            graph.add_or_update(SceneObject.from_dict(raw_object))
        for raw_relation in data.get("relations", []):
            graph._set_relation(SceneRelation.from_dict(raw_relation))
        return graph


@dataclass(frozen=True)
class PhysicsPrediction:
    scene: SceneGraph
    steps: int
    dt: float
    gravity: float
    friction: float
    weights: Dict[str, float]
    contacts: Tuple[Tuple[str, str], ...]
    collisions: Tuple[Tuple[str, str], ...]
    stable: Dict[str, bool]
    simulation_only: bool = True
    observation_required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene": self.scene.to_dict(),
            "steps": self.steps,
            "dt": self.dt,
            "gravity": self.gravity,
            "friction": self.friction,
            "weights": dict(sorted(self.weights.items())),
            "contacts": [list(item) for item in self.contacts],
            "collisions": [list(item) for item in self.collisions],
            "stable": dict(sorted(self.stable.items())),
            "simulation_only": self.simulation_only,
            "observation_required": self.observation_required,
        }


class PhysicsSimulator:
    """Small deterministic 2D gravity/contact model for supported scenes."""

    EPSILON = 1e-9

    @classmethod
    def simulate(
        cls,
        scene: SceneGraph,
        *,
        steps: int = 1,
        dt: float = 0.1,
        gravity: float = 9.81,
        friction: float = 0.1,
    ) -> PhysicsPrediction:
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0 or steps > 10000:
            raise SceneGraphError("physics steps must be an integer between 0 and 10000")
        if not math.isfinite(float(dt)) or dt <= 0 or dt > 10:
            raise SceneGraphError("physics dt must be finite and in (0, 10]")
        if not math.isfinite(float(gravity)) or gravity < 0 or gravity > 1000:
            raise SceneGraphError("physics gravity must be finite and in [0, 1000]")
        if not math.isfinite(float(friction)) or friction < 0 or friction > 1:
            raise SceneGraphError("physics friction must be finite and in [0, 1]")

        result = scene.clone()
        contacts: set[Tuple[str, str]] = set()
        collisions: set[Tuple[str, str]] = set()
        for _ in range(steps):
            for object_id in sorted(result.objects):
                obj = result.objects[object_id]
                for relation_key in list(result.relations):
                    if relation_key[0] == "supported_by" and relation_key[1] == object_id:
                        result.relations.pop(relation_key, None)
                if obj.static:
                    result.objects[object_id] = replace(obj, vx=0.0, vy=0.0, support_id=None)
                    continue
                next_vy = obj.vy - float(gravity) * float(dt)
                next_y = obj.y + next_vy * float(dt)
                support = cls._find_support(result, obj)
                if support is None:
                    support = cls._find_support(
                        result,
                        obj,
                        candidate_bottom=next_y - obj.height / 2.0,
                    )
                if support is not None:
                    support_id, support_top = support
                    updated = replace(
                        obj,
                        x=obj.x + obj.vx * float(dt),
                        y=support_top + obj.height / 2.0,
                        vx=obj.vx * (1.0 - float(friction)),
                        vy=0.0,
                        support_id=support_id,
                    )
                    result.objects[object_id] = updated
                    contacts.add((object_id, support_id))
                else:
                    if next_y - obj.height / 2.0 < 0.0:
                        next_y = obj.height / 2.0
                        next_vy = 0.0
                    result.objects[object_id] = replace(
                        obj,
                        x=obj.x + obj.vx * float(dt),
                        y=next_y,
                        vy=next_vy,
                        support_id=None,
                    )
            for left_id, right_id in cls._overlapping_pairs(result):
                collisions.add((left_id, right_id))

        stable = {
            object_id: cls._is_stable(result, object_id, contacts)
            for object_id in sorted(result.objects)
        }
        for object_id, support_id in sorted(contacts):
            if object_id in result.objects and support_id in result.objects:
                result.add_relation("supported_by", object_id, support_id)
        return PhysicsPrediction(
            scene=result,
            steps=steps,
            dt=float(dt),
            gravity=float(gravity),
            friction=float(friction),
            weights={
                object_id: round(result.objects[object_id].mass * float(gravity), 6)
                for object_id in sorted(result.objects)
            },
            contacts=tuple(sorted(contacts)),
            collisions=tuple(sorted(collisions)),
            stable=stable,
        )

    @classmethod
    def _find_support(
        cls,
        scene: SceneGraph,
        obj: SceneObject,
        *,
        candidate_bottom: Optional[float] = None,
    ) -> Optional[Tuple[str, float]]:
        candidates: List[Tuple[float, str]] = []
        current_bottom = obj.bottom
        next_bottom = current_bottom if candidate_bottom is None else candidate_bottom
        for other_id in sorted(scene.objects):
            other = scene.objects[other_id]
            if other_id == obj.object_id:
                continue
            horizontal_overlap = min(obj.right, other.right) - max(obj.left, other.left)
            if horizontal_overlap <= cls.EPSILON:
                continue
            gap = current_bottom - other.top
            crossed_support = current_bottom >= other.top - 0.05 and next_bottom <= other.top + 0.05
            if (-0.05 <= gap <= 0.05 or crossed_support) and other.top <= current_bottom + 0.05:
                candidates.append((other.top, other_id))
        if not candidates:
            return None
        support_top, support_id = max(candidates, key=lambda item: (item[0], item[1]))
        return support_id, support_top

    @classmethod
    def _overlapping_pairs(cls, scene: SceneGraph) -> Iterable[Tuple[str, str]]:
        ids = sorted(scene.objects)
        for index, left_id in enumerate(ids):
            left = scene.objects[left_id]
            for right_id in ids[index + 1:]:
                right = scene.objects[right_id]
                horizontal = min(left.right, right.right) - max(left.left, right.left)
                vertical = min(left.top, right.top) - max(left.bottom, right.bottom)
                if horizontal > cls.EPSILON and vertical > cls.EPSILON:
                    yield left_id, right_id

    @classmethod
    def _is_stable(cls, scene: SceneGraph, object_id: str, contacts: set[Tuple[str, str]]) -> bool:
        obj = scene.objects[object_id]
        if obj.static or abs(obj.bottom) <= 1e-6:
            return True
        support_id = next((right for left, right in contacts if left == object_id), obj.support_id)
        if not support_id or support_id not in scene.objects:
            return False
        support = scene.objects[support_id]
        return obj.left >= support.left - cls.EPSILON and obj.right <= support.right + cls.EPSILON


class SceneGraphStore:
    """SQLite persistence for immutable scene snapshots and event telemetry."""

    STORAGE_SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scene_store_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
                    storage_schema_version INTEGER NOT NULL,
                    current_revision INTEGER NOT NULL
                )
            """)
            row = conn.execute(
                "SELECT storage_schema_version FROM scene_store_meta WHERE singleton=1"
            ).fetchone()
            if row is None:
                conn.execute("INSERT INTO scene_store_meta VALUES (1, ?, 0)", (self.STORAGE_SCHEMA_VERSION,))
            elif int(row[0]) != self.STORAGE_SCHEMA_VERSION:
                raise SceneGraphError(
                    f"unsupported scene store schema_version={row[0]}; "
                    f"supported version is {self.STORAGE_SCHEMA_VERSION}"
                )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scene_snapshots (
                    revision INTEGER PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scene_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    observation_id TEXT,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                )
            """)
            conn.commit()

    def load_latest(self) -> SceneGraph:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT snapshot_json, digest FROM scene_snapshots ORDER BY revision DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return SceneGraph()
        stored_digest = str(row[1])
        try:
            payload = json.loads(row[0])
            if _digest(payload) != stored_digest:
                raise SceneGraphError("persisted scene snapshot digest cannot be verified")
            graph = SceneGraph.from_dict(payload)
        except SceneGraphError:
            raise
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise SceneGraphError(f"persisted scene snapshot is invalid: {exc}") from exc
        if graph.digest() != stored_digest:
            raise SceneGraphError("persisted scene snapshot digest cannot be verified")
        return graph

    def save(
        self,
        scene: SceneGraph,
        *,
        event_type: str = "observation",
        observation_id: Optional[str] = None,
        evidence_ids: Iterable[str] = (),
    ) -> SceneGraph:
        if not event_type:
            raise SceneGraphError("scene event_type is required")
        with self._lock, sqlite3.connect(self.db_path) as conn:
            current = int(conn.execute(
                "SELECT current_revision FROM scene_store_meta WHERE singleton=1"
            ).fetchone()[0])
            next_revision = current + 1
            persisted = scene.clone()
            persisted.revision = next_revision
            payload = persisted.to_dict()
            serialized = _canonical(payload)
            digest = _digest(payload)
            created_at = _now()
            conn.execute(
                "INSERT INTO scene_snapshots VALUES (?, ?, ?, ?, ?)",
                (next_revision, SCENE_SCHEMA_VERSION, serialized, digest, created_at),
            )
            conn.execute(
                "INSERT INTO scene_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"scene_event_{uuid4().hex[:16]}", event_type, next_revision,
                    observation_id, digest, created_at, _canonical(list(evidence_ids)),
                ),
            )
            conn.execute(
                "UPDATE scene_store_meta SET current_revision=? WHERE singleton=1",
                (next_revision,),
            )
            conn.commit()
        scene.revision = next_revision
        return persisted

    def history(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT event_id, event_type, revision, observation_id, digest, created_at, evidence_json "
                "FROM scene_events ORDER BY revision ASC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [
            {
                "event_id": row[0], "event_type": row[1], "revision": row[2],
                "observation_id": row[3], "digest": row[4], "created_at": row[5],
                "evidence_ids": json.loads(row[6]),
            }
            for row in rows
        ]
