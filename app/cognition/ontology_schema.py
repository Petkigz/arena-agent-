"""Owner-controlled ontology/schema revisions with append-only history.

Ontology revisions are deliberately separate from ordinary belief updates.
Beliefs may change as evidence arrives; an ontology change alters the schema
used to describe that evidence and therefore requires an explicit version,
owner authorization, and a reversible migration event.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.cognition.owner_decisions import (
    DECISION_ONTOLOGY_SCHEMA_CHANGE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_schema(schema: Dict[str, Any]) -> str:
    return json.dumps(schema, sort_keys=True, separators=(",", ":"), default=str)


def _digest(schema: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_schema(schema).encode("utf-8")).hexdigest()


class OntologySchemaError(ValueError):
    """The ontology store or proposed schema is unsupported or ambiguous."""


@dataclass(frozen=True)
class OntologyRevision:
    revision: int
    parent_revision: Optional[int]
    schema: Dict[str, Any]
    digest: str
    status: str
    note: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "revision": self.revision,
            "parent_revision": self.parent_revision,
            "schema": dict(self.schema),
            "digest": self.digest,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at,
        }


class OntologySchemaStore:
    """Persist immutable ontology revisions and owner-authorized transitions."""

    STORAGE_SCHEMA_VERSION = 1
    SUPPORTED_ONTOLOGY_SCHEMA_VERSIONS = frozenset({1})
    DEFAULT_SCHEMA = {
        "ontology_schema_version": 1,
        "entities": {},
        "relations": {},
        "epistemic_fields": {
            "source": "required",
            "observation_type": "required",
            "confidence": "bounded_0_1",
        },
    }

    def __init__(self, db_path: str | Path, *, owner_decisions: Optional[Any] = None) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.owner_decisions = owner_decisions
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ontology_store_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    storage_schema_version INTEGER NOT NULL
                )
            """)
            meta = conn.execute(
                "SELECT storage_schema_version FROM ontology_store_meta WHERE singleton=1"
            ).fetchone()
            if meta is None:
                conn.execute(
                    "INSERT INTO ontology_store_meta (singleton, storage_schema_version) VALUES (1, ?)",
                    (self.STORAGE_SCHEMA_VERSION,),
                )
            elif int(meta[0]) != self.STORAGE_SCHEMA_VERSION:
                raise OntologySchemaError(
                    f"unsupported ontology store schema_version={meta[0]}; "
                    f"supported version is {self.STORAGE_SCHEMA_VERSION}; "
                    "run the matching store migration before opening it"
                )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ontology_revisions (
                    revision INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_revision INTEGER,
                    schema_json TEXT NOT NULL,
                    digest TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ontology_current (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    revision INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ontology_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    previous_revision INTEGER,
                    decision_id TEXT,
                    created_at TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT ''
                )
            """)
            current = conn.execute(
                "SELECT revision FROM ontology_current WHERE singleton=1"
            ).fetchone()
            if current is None:
                row = conn.execute(
                    "SELECT revision FROM ontology_revisions ORDER BY revision LIMIT 1"
                ).fetchone()
                if row is None:
                    created_at = _now()
                    conn.execute("""
                        INSERT INTO ontology_revisions
                        (parent_revision, schema_json, digest, status, note, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        None,
                        _canonical_schema(self.DEFAULT_SCHEMA),
                        _digest(self.DEFAULT_SCHEMA),
                        "active",
                        "initial ontology schema",
                        created_at,
                    ))
                    revision = int(conn.execute(
                        "SELECT revision FROM ontology_revisions ORDER BY revision LIMIT 1"
                    ).fetchone()[0])
                    conn.execute(
                        "INSERT INTO ontology_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (f"ontology_event_{uuid4().hex[:12]}", "initialize", revision,
                         None, None, created_at, "initial ontology schema"),
                    )
                else:
                    revision = int(row[0])
                    conn.execute(
                        "UPDATE ontology_revisions SET status='active' WHERE revision=?",
                        (revision,),
                    )
                conn.execute(
                    "INSERT INTO ontology_current (singleton, revision) VALUES (1, ?)",
                    (revision,),
                )
            conn.commit()

    @classmethod
    def _validate_schema(cls, schema: Dict[str, Any]) -> None:
        if not isinstance(schema, dict) or not schema:
            raise OntologySchemaError("ontology schema must be a non-empty mapping")
        version = schema.get("ontology_schema_version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise OntologySchemaError(
                "ontology schema must declare an integer ontology_schema_version; "
                "a missing version is ambiguous and cannot be migrated safely"
            )
        if version not in cls.SUPPORTED_ONTOLOGY_SCHEMA_VERSIONS:
            raise OntologySchemaError(
                f"unsupported ontology_schema_version={version}; supported versions are "
                f"{sorted(cls.SUPPORTED_ONTOLOGY_SCHEMA_VERSIONS)}"
            )
        for field in ("entities", "relations", "epistemic_fields"):
            if field in schema and not isinstance(schema[field], dict):
                raise OntologySchemaError(
                    f"ontology schema field {field!r} must be a mapping; refusing ambiguous migration"
                )

    @staticmethod
    def _revision_from_row(row: sqlite3.Row | tuple) -> OntologyRevision:
        return OntologyRevision(
            revision=int(row[0]),
            parent_revision=None if row[1] is None else int(row[1]),
            schema=json.loads(row[2]),
            digest=str(row[3]),
            status=str(row[4]),
            note=str(row[5] or ""),
            created_at=str(row[6]),
        )

    def _get(self, revision: int) -> OntologyRevision:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT revision, parent_revision, schema_json, digest, status, note, created_at "
                "FROM ontology_revisions WHERE revision=?",
                (int(revision),),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown ontology revision: {revision}")
        result = self._revision_from_row(row)
        self._validate_schema(result.schema)
        if _digest(result.schema) != result.digest:
            raise OntologySchemaError(
                f"ontology revision {result.revision} has a digest mismatch; "
                "history is tampered or corrupt and cannot be activated"
            )
        return result

    def current(self) -> OntologyRevision:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT revision FROM ontology_current WHERE singleton=1"
            ).fetchone()
        if row is None:
            raise RuntimeError("ontology current revision is missing")
        return self._get(int(row[0]))

    def propose(self, schema: Dict[str, Any], *, note: str = "") -> OntologyRevision:
        """Stage an immutable revision; staging does not change active schema."""
        self._validate_schema(schema)
        parent = self.current()
        digest = _digest(schema)
        with sqlite3.connect(self.db_path) as conn:
            duplicate = conn.execute(
                "SELECT revision FROM ontology_revisions WHERE digest=?", (digest,)
            ).fetchone()
            if duplicate is not None:
                return self._get(int(duplicate[0]))
            cursor = conn.execute("""
                INSERT INTO ontology_revisions
                (parent_revision, schema_json, digest, status, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                parent.revision,
                _canonical_schema(schema),
                digest,
                "staged",
                str(note or ""),
                _now(),
            ))
            revision = int(cursor.lastrowid)
            conn.commit()
        return self._get(revision)

    def _authorize(self, decision_id: Optional[str], operation: str) -> None:
        if not decision_id:
            raise PermissionError(
                f"owner authorization is required for ontology operation: {operation}"
            )
        if self.owner_decisions is None:
            raise PermissionError("owner decision store is unavailable")
        validation = self.owner_decisions.validate(
            decision_id,
            decision_type=DECISION_ONTOLOGY_SCHEMA_CHANGE,
            claimed_change_types=[operation],
        )
        if not validation.get("valid"):
            raise PermissionError(
                f"ontology operation was not authorized: {validation.get('reasons', [])}"
            )

    def _transition(
        self,
        revision: int,
        *,
        decision_id: Optional[str],
        event_type: str,
        operation: str,
        note: str,
    ) -> OntologyRevision:
        target = self._get(revision)
        previous = self.current()
        if event_type == "migrate" and (
            target.status != "staged" or target.parent_revision != previous.revision
        ):
            raise OntologySchemaError(
                f"ontology revision {revision} is not the next staged child of current revision "
                f"{previous.revision}; activate only deterministic migrations"
            )
        if event_type == "rollback" and target.revision >= previous.revision:
            raise OntologySchemaError(
                f"ontology revision {revision} is not an older revision than current revision "
                f"{previous.revision}; use migration for forward changes"
            )
        self._authorize(decision_id, operation)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE ontology_revisions SET status='superseded' "
                "WHERE status='active' AND revision != ?",
                (target.revision,),
            )
            conn.execute(
                "UPDATE ontology_revisions SET status='active' WHERE revision=?",
                (target.revision,),
            )
            conn.execute(
                "UPDATE ontology_current SET revision=? WHERE singleton=1",
                (target.revision,),
            )
            conn.execute(
                "INSERT INTO ontology_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"ontology_event_{uuid4().hex[:12]}",
                    event_type,
                    target.revision,
                    previous.revision,
                    decision_id,
                    _now(),
                    str(note or ""),
                ),
            )
            conn.commit()
        return self._get(target.revision)

    def activate(self, revision: int, *, owner_decision_id: Optional[str], note: str = "") -> OntologyRevision:
        """Activate a staged revision through an owner-authorized migration."""
        return self._transition(
            revision,
            decision_id=owner_decision_id,
            event_type="migrate",
            operation="activate_ontology_schema",
            note=note or f"activate ontology revision {revision}",
        )

    def rollback(self, revision: int, *, owner_decision_id: Optional[str], note: str = "") -> OntologyRevision:
        """Point the active schema at an older immutable revision.

        Rollback is an append-only event and never deletes the newer revision.
        """
        return self._transition(
            revision,
            decision_id=owner_decision_id,
            event_type="rollback",
            operation="rollback_ontology_schema",
            note=note or f"rollback ontology schema to revision {revision}",
        )

    def revisions(self, limit: int = 100) -> List[OntologyRevision]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT revision, parent_revision, schema_json, digest, status, note, created_at "
                "FROM ontology_revisions ORDER BY revision ASC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [self._revision_from_row(row) for row in rows]

    def events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT event_id, event_type, revision, previous_revision, decision_id, created_at, note "
                "FROM ontology_events ORDER BY created_at ASC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [
            {
                "event_id": row[0],
                "event_type": row[1],
                "revision": row[2],
                "previous_revision": row[3],
                "decision_id": row[4],
                "created_at": row[5],
                "note": row[6],
            }
            for row in rows
        ]
