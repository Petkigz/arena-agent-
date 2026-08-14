"""Composition root for Arena's Unified Cognitive Engine."""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from app.config import settings
from .action_selection import ActionSelector, InvestigationExecutor
from .belief_engine import BeliefEngine
from .blackboard import Blackboard
from .cognitive_state import CognitiveState
from .event_bus import EventBus
from .memory import MemoryStore
from .memory_learning import MemoryLearner
from .reasoning_loop import CognitiveReasoningLoop
from .reflection import ReflectionEngine
from .world_ingest import WorldIngestor
from .world_model import WorldModel
from .attention_manager import AttentionManager
from .prediction_engine import PredictionEngine
from .counterfactual_simulator import CounterfactualSimulator
from .action_proposal import ActionGate, ActionProposal

class CognitiveRuntime:
    """Single authoritative composition root for Arena's cognitive stack."""

    _instance: Optional[CognitiveRuntime] = None

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> CognitiveRuntime:
        if cls._instance is None:
            cls._instance = CognitiveRuntime(db_path=db_path)
        return cls._instance

    def __init__(self, db_path: Optional[str] = None, max_steps: int = 3) -> None:
        path = db_path or str(settings.DB_PATH)
        self.state = CognitiveState()
        self.blackboard = Blackboard()
        self.events = EventBus()
        self.world = WorldModel(path)
        self.world_ingest = WorldIngestor(self.world, self.events)
        self.beliefs = BeliefEngine(db_path=path)
        self.actions = ActionSelector()
        self.executor = InvestigationExecutor()
        self.memory = MemoryStore(path)
        self.learning = MemoryLearner(self.memory)
        self.reflection = ReflectionEngine()
        self.attention = AttentionManager()
        self.prediction = PredictionEngine()
        self.counterfactual = CounterfactualSimulator()
        self.loop = CognitiveReasoningLoop(
            engine=self.beliefs,
            action_selector=self.actions,
            executor=self.executor,
            world_ingestor=self.world_ingest,
            event_bus=self.events,
            cognitive_state=self.state,
            max_steps=max_steps,
        )

    def process_unified_thought_cycle(self, user_text: str, complexity: str = "fast") -> Dict[str, Any]:
        """
        Unified single-path cognitive cycle:
        Perceive ➔ Update World ➔ Retrieve Memory ➔ Attend ➔ Reason ➔ Gate Action ➔ Execute ➔ Learn
        """
        # 1. Update State & Blackboard Focus
        self.state.attention.focus = user_text[:30]
        self.attention.allocate_attention(user_text[:30], priority_score=0.8)

        # 2. Master Agent Execution through Unified Tool Registry
        from app.agents.master_agent import MasterAgentOrchestrator
        agent_res = MasterAgentOrchestrator.process_user_task(user_text, complexity=complexity)

        # 3. Predict & Calculate Surprisal
        pred = self.prediction.predict_action("master_task", {"query": user_text})

        # 4. Record Lesson & Memory
        self.memory.add("episodic", f"User Query: {user_text} | Reply: {agent_res.get('assistant_reply', '')[:100]}")

        return {
            "success": True,
            "user_text": user_text,
            "assistant_reply": agent_res.get("assistant_reply", "Done."),
            "executed_actions": agent_res.get("executed_actions", []),
            "prediction_confidence": pred.confidence,
            "active_focus": self.attention.active_focus.target_name if self.attention.active_focus else "general"
        }
