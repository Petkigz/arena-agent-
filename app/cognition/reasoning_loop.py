"""Closed observe -> reason -> investigate -> observe cognitive loop."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

from .action_selection import ActionSelector, InvestigationExecutor, InvestigationPlan, ActionResult
from .belief_engine import BeliefEngine
from .event_bus import EventBus
from .events import CognitiveEvent
from .information_gain import InformationNeed
from .reasoning_cycle import ReasoningAction, ReasoningCycle, ReasoningDecision
from .world_ingest import WorldIngestor

@dataclass
class CycleTrace:
    decisions: list[ReasoningDecision] = field(default_factory=list)
    plans: list[InvestigationPlan] = field(default_factory=list)
    results: list[ActionResult] = field(default_factory=list)
    finished: bool = False
    reason: str = ""

class CognitiveReasoningLoop:
    """Runs a bounded cognitive loop without allowing the reasoning model to execute arbitrary tools."""
    def __init__(self, engine: Optional[BeliefEngine] = None, action_selector: Optional[ActionSelector] = None,
                 executor: Optional[InvestigationExecutor] = None, world_ingestor: Optional[WorldIngestor] = None,
                 event_bus: Optional[EventBus] = None, max_steps: int = 3) -> None:
        self.engine = engine or BeliefEngine()
        self.cycle = ReasoningCycle(self.engine)
        self.action_selector = action_selector or ActionSelector()
        self.executor = executor or InvestigationExecutor()
        self.world_ingestor = world_ingestor
        self.event_bus = event_bus
        self.max_steps = max(1, min(max_steps, 20))

    def run(self, subject: str, predicate: str, *, value: Any = None, source: Optional[str] = None,
            confidence: float = 1.0, information_needs: Optional[list[InformationNeed]] = None,
            task_id: Optional[str] = None) -> CycleTrace:
        trace = CycleTrace()
        if source is not None:
            self.engine.ingest(subject, predicate, value, source=source, confidence=confidence, task_id=task_id)
        needs = information_needs or []
        for _ in range(self.max_steps):
            decision = self.cycle.decide(subject, predicate, information_needs=needs, action_available=False)
            trace.decisions.append(decision)
            self._emit("reasoning_decision", {"subject": subject, "predicate": predicate, "action": decision.action.value, "confidence": decision.confidence})
            if decision.action in (ReasoningAction.ANSWER, ReasoningAction.DEFER):
                trace.finished = True; trace.reason = decision.reason; return trace
            if decision.action is not ReasoningAction.INVESTIGATE or decision.information_need is None:
                trace.finished = True; trace.reason = decision.reason; return trace
            plan = self.action_selector.select(decision.information_need)
            if plan is None:
                trace.finished = True; trace.reason = "No registered investigation is available."; return trace
            trace.plans.append(plan)
            result = self.executor.execute(plan)
            trace.results.append(result)
            self._emit("investigation_completed", {"tool": plan.tool, "success": result.success, "target": plan.target})
            if not result.success:
                trace.finished = True; trace.reason = result.error or "Investigation failed."; return trace
            if self.world_ingestor is not None and plan.predicate is not None:
                self.world_ingestor.ingest(subject, plan.predicate, result.output, source=f"tool:{plan.tool}", task_id=task_id)
            else:
                self.engine.ingest(subject, predicate, result.output, source=f"tool:{plan.tool}", task_id=task_id)
            needs = [n for n in needs if n is not decision.information_need]
        trace.finished = True
        trace.reason = "Maximum cognitive investigation steps reached."
        return trace

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(CognitiveEvent(event_type=event_type, data=data, source="cognitive_reasoning_loop"))
