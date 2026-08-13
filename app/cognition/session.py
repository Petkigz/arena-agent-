"""Session isolation for Arena's cognitive context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class CognitiveSession:
    """Identity and lifecycle metadata for one independent interaction context."""

    session_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_activity: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    active: bool = True

    def touch(self) -> None:
        self.last_activity = datetime.now(timezone.utc).isoformat()

    def close(self) -> None:
        self.active = False
        self.touch()
