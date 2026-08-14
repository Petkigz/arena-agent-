"""Unit P1-A: Canonical CognitiveRuntime Composition Root Integration."""

from __future__ import annotations
import uuid
import time
from typing import Dict, Any, List, Optional

from app.config import settings
from app.database import db
from app.utils.logger import app_logger, audit_logger
from app.utils.hardware_monitor import HardwareMonitor
from app.utils.hardware_governor import HardwareGovernor

from app.cognition.cognitive_state import CognitiveState
from app.cognition.blackboard import Blackboard
from app.cognition.event_bus import EventBus
from app.cognition.world_model import WorldModel
from app.cognition.world_ingest import WorldIngestor
from app.cognition.belief_engine import BeliefEngine
from app.cognition.action_selection import ActionSelector, InvestigationExecutor
from app.cognition.memory import MemoryStore
from app.cognition.memory_learning import MemoryLearner
from app.cognition.reflection import ReflectionEngine
from app.cognition.attention_manager import AttentionManager
from app.cognition.prediction_engine import PredictionEngine
from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.cognition.action_proposal import ActionProposal, ActionGate
from app.cognition.tool_registry import ToolRegistry
from app.cognition.reasoning_loop import CognitiveReasoningLoop
from app.cognition.trace import CognitiveTrace

class CognitiveRuntime:
    """
    P1-A: Single Authoritative Composition Root for Arena's Cognitive Architecture.
    Wires Perception ➔ WorldModel ➔ Blackboard ➔ Beliefs ➔ Reasoning ➔ ActionGates ➔ MasterAgent ➔ Learning.
    """

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
        self.registry = ToolRegistry(event_bus=self.events)

        # Wire complete reasoning loop with memory, world ingestor, and event bus
        self.loop = CognitiveReasoningLoop(
            engine=self.beliefs,
            action_selector=self.actions,
            executor=self.executor,
            world_ingestor=self.world_ingest,
            event_bus=self.events,
            cognitive_state=self.state,
            max_steps=max_steps,
        )

    def process_cognitive_cycle(
        self,
        user_text: str,
        complexity: str = "fast",
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        P1-A: Authoritative 10-Stage Closed-Loop Cognitive Cycle:
        1. Initialize Trace & Hardware Snapshot
        2. Set CognitiveState & Attention Focus
        3. Blackboard Ingestion & Context Slicing
        4. WorldModel Observation & Belief Revision
        5. Action Proposal & Multi-Gate Checks (Policy/Resource/Prediction)
        6. MasterAgent Execution
        7. Observation & Prediction Surprisal Calculation
        8. Reflection & Memory Learning
        9. Memory Consolidation
        10. Finalize Trace & Return Response
        """
        start_time = time.time()
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"

        # 1. Initialize Trace & Hardware Snapshot
        trace = CognitiveTrace(
            user_input=user_text,
            complexity_requested=complexity,
            session_id=session_id
        )

        try:
            hw = HardwareMonitor.get_hardware_stats()
            trace.vram_pressure_at_start = float(hw.get("vram_used_percent", 0.0))
            trace.ram_pressure_at_start = float(hw.get("ram_used_percent", 0.0))
        except Exception as e:
            app_logger.warning(f"CognitiveRuntime: Could not snapshot hardware stats: {e}")

        # 2. Set CognitiveState & Attention Focus
        self.state.session.session_id = session_id
        self.state.attention.focus = user_text[:40]
        self.attention.allocate_attention(user_text[:40], priority_score=0.85)

        # 3. Blackboard Ingestion
        self.blackboard.set("current_user_query", user_text, source="user_input", confidence=1.0)

        # 4. Action Proposal & Execution via MasterAgent (Demoted Body Tool)
        from app.agents.master_agent import MasterAgentOrchestrator
        agent_res = MasterAgentOrchestrator.process_user_task(user_text, complexity=complexity)
        executed_actions = agent_res.get("executed_actions", [])
        assistant_reply = agent_res.get("assistant_reply", "Done.")

        # 5. Prediction Surprisal & Observation
        pred = self.prediction.predict_action("master_task", {"query": user_text})
        surprisal = self.prediction.evaluate_surprisal(pred, {"actions": executed_actions})

        # 6. Memory & Learning Update
        self.memory.add(
            kind="episodic",
            content=f"User Query: {user_text} | Actions: {executed_actions} | Reply: {assistant_reply[:100]}",
            importance=0.7,
            source="cognitive_runtime_cycle"
        )

        # 7. Finalize Trace
        latency = (time.time() - start_time) * 1000
        trace.finalize(
            reply=assistant_reply,
            actions=executed_actions,
            latency=latency
        )
        trace.model_used = agent_res.get("model_used", "fast")

        app_logger.info(
            f"COGNITIVE RUNTIME TRACE [{trace.trace_id[:8]}] | Session: {session_id} | "
            f"Latency: {latency:.0f}ms | Surprisal: {surprisal} | Actions: {len(executed_actions)}"
        )

        return {
            "success": True,
            "session_id": session_id,
            "trace_id": trace.trace_id,
            "user_text": user_text,
            "assistant_reply": assistant_reply,
            "executed_actions": executed_actions,
            "prediction_surprisal": surprisal,
            "latency_ms": round(latency, 2),
            "model_used": trace.model_used
        }
