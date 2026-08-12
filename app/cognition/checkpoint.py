"""Crash-safe cognitive checkpoints.

Phase 1 keeps checkpoints deliberately small: the active cognitive state,
working-memory snapshot, and schema metadata. Persistence is file-based so it
works without adding another service or database dependency.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional

from .cognitive_state import CognitiveState
from .blackboard import Blackboard


class CognitiveCheckpointStore:
    """Atomically persist and restore the active cognitive context."""

    SCHEMA_VERSION = 1

    def __init__(self, directory: str | Path = "data/checkpoints") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, state: CognitiveState, blackboard: Blackboard, name: str = "active") -> Path:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "state": asdict(state),
            "blackboard": blackboard.snapshot(),
        }
        target = self.directory / f"{name}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        temporary.replace(target)
        return target

    def load(self, name: str = "active") -> Optional[dict]:
        target = self.directory / f"{name}.json"
        if not target.exists():
            return None
        with target.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("Unsupported cognitive checkpoint schema")
        return payload
