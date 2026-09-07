"""Crash-safe, explicitly versioned cognitive checkpoints.

Checkpoint schema migration is an administrative operation, not a belief
update. Supported migrations preserve the original file as a content-addressed
backup and append an audit event. Rollback is only offered when that exact
backup still matches the migrated checkpoint, so the store never claims to
restore state after an unrelated overwrite.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .cognitive_state import CognitiveState
from .blackboard import Blackboard


class CheckpointSchemaError(ValueError):
    """The checkpoint is unsupported, malformed, or ambiguous."""


class CognitiveCheckpointStore:
    """Atomically persist, migrate, and restore the active cognitive context."""

    # Version 1 is retained as a supported input so existing user checkpoints
    # can be upgraded deterministically. New writes use version 2.
    SCHEMA_VERSION = 2
    SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})

    def __init__(self, directory: str | Path = "data/checkpoints") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _bytes_digest(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _target(self, name: str) -> Path:
        if not name or Path(name).name != name or Path(name).suffix not in {"", ".json"}:
            raise ValueError("checkpoint name must be a simple file name")
        return self.directory / (name if name.endswith(".json") else f"{name}.json")

    def _audit_path(self) -> Path:
        return self.directory / "migration-audit.jsonl"

    def _read_raw(self, target: Path) -> tuple[bytes, Dict[str, Any]]:
        try:
            raw = target.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CheckpointSchemaError(
                f"checkpoint {target.name} is unreadable JSON; restore a known checkpoint "
                "or remove the corrupt file after preserving it"
            ) from exc
        if not isinstance(payload, dict):
            raise CheckpointSchemaError(
                f"checkpoint {target.name} must contain a JSON object, not {type(payload).__name__}"
            )
        return raw, payload

    def _validate(self, payload: Dict[str, Any], target: Path) -> int:
        version = payload.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise CheckpointSchemaError(
                f"checkpoint {target.name} has no unambiguous integer schema_version; "
                f"supported versions are {sorted(self.SUPPORTED_SCHEMA_VERSIONS)}"
            )
        if version not in self.SUPPORTED_SCHEMA_VERSIONS:
            raise CheckpointSchemaError(
                f"unsupported checkpoint schema_version={version} in {target.name}; "
                f"supported versions are {sorted(self.SUPPORTED_SCHEMA_VERSIONS)}; "
                "do not load it as cognitive state until an explicit migration is added"
            )
        required = {"state", "blackboard", "saved_at"}
        missing = sorted(required - set(payload))
        if missing:
            raise CheckpointSchemaError(
                f"checkpoint schema_version={version} is missing required fields {missing}; "
                "migration is unsafe because the prior state is ambiguous"
            )
        if not isinstance(payload["saved_at"], str):
            raise CheckpointSchemaError(
                f"checkpoint schema_version={version} has a non-string saved_at; "
                "refusing an ambiguous migration"
            )
        if not isinstance(payload["state"], dict) or not isinstance(payload["blackboard"], dict):
            raise CheckpointSchemaError(
                f"checkpoint schema_version={version} has non-object state or blackboard; "
                "refusing an ambiguous migration"
            )
        if version == self.SCHEMA_VERSION:
            ontology_revision = payload.get("ontology_revision")
            if isinstance(ontology_revision, bool) or not isinstance(ontology_revision, int) or ontology_revision < 1:
                raise CheckpointSchemaError(
                    "current checkpoint is missing a positive integer ontology_revision; "
                    "restore from a valid checkpoint instead of guessing the schema"
                )
        return version

    def _atomic_write(self, target: Path, content: bytes, suffix: str = ".tmp") -> None:
        temporary = target.with_name(f".{target.name}{suffix}")
        temporary.write_bytes(content)
        temporary.replace(target)

    def _append_audit(self, record: Dict[str, Any]) -> None:
        audit = self._audit_path()
        with audit.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def save(
        self,
        state: CognitiveState,
        blackboard: Blackboard,
        name: str = "active",
        *,
        ontology_revision: int = 1,
    ) -> Path:
        if isinstance(ontology_revision, bool) or not isinstance(ontology_revision, int) or ontology_revision < 1:
            raise ValueError("ontology_revision must be a positive integer")
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "ontology_revision": ontology_revision,
            "saved_at": self._now(),
            "state": asdict(state),
            "blackboard": blackboard.snapshot(),
        }
        target = self._target(name)
        content = json.dumps(payload, indent=2, default=str).encode("utf-8")
        with self._lock:
            self._atomic_write(target, content)
        return target

    def load(self, name: str = "active") -> Optional[dict]:
        target = self._target(name)
        if not target.exists():
            return None
        with self._lock:
            _, payload = self._read_raw(target)
            self._validate(payload, target)
        return payload

    def migrate(self, name: str = "active") -> Optional[dict]:
        """Deterministically migrate supported schema 1 to the current schema.

        The original bytes are retained in a migration-specific backup. The
        migration event records both content digests, allowing rollback to
        refuse a checkpoint that was subsequently overwritten.
        """
        target = self._target(name)
        if not target.exists():
            return None
        with self._lock:
            original, payload = self._read_raw(target)
            version = self._validate(payload, target)
            if version == self.SCHEMA_VERSION:
                return payload
            if version != 1:  # defensive: every supported older version needs a named migration.
                raise CheckpointSchemaError(
                    f"no deterministic migration is registered for checkpoint schema_version={version}"
                )

            migration_id = f"checkpoint_migration_{uuid4().hex[:16]}"
            backup = self.directory / f"{target.stem}.{migration_id}.schema-v1.json"
            backup.write_bytes(original)
            migrated = dict(payload)
            migrated.update({
                "schema_version": self.SCHEMA_VERSION,
                "ontology_revision": 1,
                "migration": {
                    "migration_id": migration_id,
                    "from_schema_version": 1,
                    "to_schema_version": self.SCHEMA_VERSION,
                    "migrated_at": self._now(),
                },
            })
            migrated_bytes = json.dumps(migrated, indent=2, default=str).encode("utf-8")
            record = {
                "event_type": "migration",
                "migration_id": migration_id,
                "checkpoint": target.name,
                "from_schema_version": 1,
                "to_schema_version": self.SCHEMA_VERSION,
                "source_digest": self._bytes_digest(original),
                "target_digest": self._bytes_digest(migrated_bytes),
                "backup": backup.name,
                "created_at": self._now(),
            }
            try:
                self._atomic_write(target, migrated_bytes, suffix=f".{migration_id}.tmp")
                self._append_audit(record)
            except Exception:
                # Do not leave a partially applied migration while reporting
                # failure; restoration is deterministic because the source
                # bytes were retained before replacement.
                self._atomic_write(target, original, suffix=f".{migration_id}.restore")
                raise
            return migrated

    def migration_history(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        audit = self._audit_path()
        if not audit.exists():
            return []
        records: List[Dict[str, Any]] = []
        with self._lock:
            for line in audit.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise CheckpointSchemaError(
                        "migration audit contains malformed JSON; rollback is unsafe until it is repaired"
                    ) from exc
                if name is None or record.get("checkpoint") == self._target(name).name:
                    records.append(record)
        return records

    def rollback(self, name: str = "active") -> Optional[dict]:
        """Restore the latest still-active deterministic migration.

        If the checkpoint changed after migration, rollback fails closed rather
        than claiming to restore state it can no longer identify.
        """
        target = self._target(name)
        if not target.exists():
            return None
        with self._lock:
            current, current_payload = self._read_raw(target)
            self._validate(current_payload, target)
            history = self.migration_history(name)
            migration = None
            rolled_back_ids = {
                row.get("migration_id") for row in history if row.get("event_type") == "rollback"
            }
            for row in reversed(history):
                if row.get("event_type") == "migration" and row.get("migration_id") not in rolled_back_ids:
                    migration = row
                    break
            if migration is None:
                raise RuntimeError(
                    f"no deterministic migration backup is available for {target.name}; rollback not claimed"
                )
            if self._bytes_digest(current) != migration.get("target_digest"):
                raise RuntimeError(
                    f"{target.name} changed after migration; refusing ambiguous rollback because "
                    "the exact migrated state is no longer current"
                )
            backup = self.directory / str(migration.get("backup", ""))
            if not backup.exists():
                raise RuntimeError(
                    f"migration backup {backup.name} is missing; rollback cannot truthfully be completed"
                )
            previous = backup.read_bytes()
            _, previous_payload = self._read_raw(backup)
            previous_version = self._validate(previous_payload, backup)
            if previous_version != migration.get("from_schema_version"):
                raise RuntimeError(
                    "migration backup schema does not match its audit record; rollback refused"
                )
            rollback_id = f"checkpoint_rollback_{uuid4().hex[:16]}"
            rollback_backup = self.directory / f"{target.stem}.{rollback_id}.schema-v{self.SCHEMA_VERSION}.json"
            rollback_backup.write_bytes(current)
            record = {
                "event_type": "rollback",
                "migration_id": migration["migration_id"],
                "rollback_id": rollback_id,
                "checkpoint": target.name,
                "from_schema_version": self.SCHEMA_VERSION,
                "to_schema_version": previous_version,
                "source_digest": self._bytes_digest(current),
                "target_digest": self._bytes_digest(previous),
                "backup": rollback_backup.name,
                "created_at": self._now(),
            }
            try:
                self._atomic_write(target, previous, suffix=f".{rollback_id}.tmp")
                self._append_audit(record)
            except Exception:
                self._atomic_write(target, current, suffix=f".{rollback_id}.restore")
                raise
            return previous_payload
