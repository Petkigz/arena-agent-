"""Composition root for Arena's Phase 3 cognitive stack."""
from __future__ import annotations
from typing import Optional
from app.config import settings
from .action_selection import ActionSelector, InvestigationExecutor
from .belief_engine import BeliefEngine
from .cognitive_state import CognitiveState
from .event_bus import EventBus
from .reasoning_loop import CognitiveReasoningLoop
from .world_ingest import WorldIngestor
from .world_model import WorldModel

class CognitiveRuntime:
    """Owns one isolated cognitive stack and exposes explicit registration points."""
    def __init__(self, db_path: Optional[str] = None, max_steps: int = 3) -> None:
        path = db_path or str(settings.DB_PATH)
        self.state = CognitiveState()
        self.events = EventBus()
        self.world = WorldModel(path)
        self.world_ingest = WorldIngestor(self.world, self.events)
        self.beliefs = BeliefEngine(db_path=path)
        self.actions = ActionSelector()
        self.executor = InvestigationExecutor()
        self.loop = CognitiveReasoningLoop(
            engine=self.beliefs,
            action_selector=self.actions,
            executor=self.executor,
            world_ingestor=self.world_ingest,
            event_bus=self.events,
            cognitive_state=self.state,
            max_steps=max_steps,
        )

    def register_probe(self, target, planner, tool_name, tool):
        """Register a semantic probe and its concrete callable separately."""
        self.actions.registry.register(target, planner)
        self.executor.register(tool_name, tool)
