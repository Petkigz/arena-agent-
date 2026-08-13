"""Bridge raw observations into Arena's persistent world model.

Phase 2 keeps ingestion deliberately model-free: producers provide structured
observations and this layer normalizes, validates, stores, and emits change
records. Semantic interpretation can be added later without coupling every
perception subsystem to SQLite.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from .events import CognitiveEvent
from .world_model import Observation, WorldChange, WorldModel


class WorldIngestor:
    def __init__(self, model: WorldModel, event_bus=None) -> None:
        self.model = model
        self.event_bus = event_bus

    def ingest(
        self,
        subject: str,
        predicate: str,
        value: Any,
        *,
        source: str = "unknown",
        confidence: float = 1.0,
        task_id: Optional[str] = None,
    ) -> tuple[Observation, Optional[WorldChange]]:
        recent = self.model.recent_observations(subject, limit=100)
        previous = next((item for item in recent if item.predicate == predicate), None)
        observation = Observation(
            id=uuid4().hex,
            subject=subject,
            predicate=predicate,
            value=value,
            source=source,
            confidence=confidence,
            task_id=task_id,
        )
        self.model.observe(observation)

        change = None
        if previous is not None and previous.value != value:
            change = WorldChange(
                subject=subject,
                predicate=predicate,
                previous_value=previous.value,
                current_value=value,
                observed_at=observation.observed_at,
                source=source,
                confidence=confidence,
                observation_id=observation.id,
            )
            if self.event_bus is not None:
                self.event_bus.publish(
                    CognitiveEvent(
                        event_type="world_state_changed",
                        data={
                            "subject": subject,
                            "predicate": predicate,
                            "previous": previous.value,
                            "current": value,
                            "source": source,
                            "confidence": confidence,
                            "observation_id": observation.id,
                        },
                    )
                )
        return observation, change
