"""Closed observe -> reason -> investigate -> observe cognitive loop."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from .action_selection import ActionSelector, InvestigationExecutor, InvestigationPlan, ActionResult
from .belief_engine import BeliefEngine
from .cognitive_state import CognitiveState
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
                 event_bus: Optional[EventBus] = None, cognitive_state: Optional[CognitiveState] = None,
                 max_steps: int = 3) -> None:
        self.engine = engine or BeliefEngine()
        self.cycle = ReasoningCycle(self.engine)
        self.action_selector = action_selector or ActionSelector()
        self.executor = executor or InvestigationExecutor()
        self.world_ingestor = world_ingestor
        self.event_bus = event_bus
        self.cognitive_state = cognitive_state
        self.max_steps = max(1, min(max_steps, 20))

    def run(self, subject: str, predicate: str, *, value: Any = None, source: Optional[str] = None,
            confidence: float = 1.0, information_needs: Optional[list[InformationNeed]] = None,
            task_id: Optional[str] = None, action_available: bool = True,
            proposed_action: Optional[Any] = None) -> CycleTrace:
        trace = CycleTrace()
        if self.cognitive_state is not None:
            self.cognitive_state.attention.focus = f"{subject}.{predicate}"
            self.cognitive_state.task.current_step = "reasoning"
            self.cognitive_state.reasoning["status"] = "observing"
            self.cognitive_state.touch()
        if source is not None:
            self.engine.ingest(subject, predicate, value, source=source, confidence=confidence, task_id=task_id)
        needs = list(information_needs or [])
        for _ in range(self.max_steps):
            decision = self.cycle.decide(
                subject,
                predicate,
                information_needs=needs,
                action_available=action_available,
                proposed_action=proposed_action
            )
            trace.decisions.append(decision)
            if self.cognitive_state is not None:
                self.cognitive_state.reasoning["confidence"] = decision.confidence
                self.cognitive_state.reasoning["hypotheses"] = list(decision.belief.alternatives) if decision.belief else []
                self.cognitive_state.reasoning["status"] = decision.action.value
                self.cognitive_state.touch()
            self._emit("reasoning_decision", {"subject": subject, "predicate": predicate, "action": decision.action.value, "confidence": decision.confidence})
            if decision.action in (ReasoningAction.ANSWER, ReasoningAction.DEFER, ReasoningAction.ACT):
                trace.finished = True; trace.reason = decision.reason; return trace
            if decision.action is not ReasoningAction.INVESTIGATE or decision.information_need is None:
                trace.finished = True; trace.reason = decision.reason; return trace
            plan = self.action_selector.select(decision.information_need)
            if plan is None:
                trace.finished = True; trace.reason = "No registered investigation is available."; return trace
            trace.plans.append(plan)
            if self.cognitive_state is not None:
                self.cognitive_state.execution.pending_action = plan.tool
                self.cognitive_state.touch()
            result = self.executor.execute(plan)
            trace.results.append(result)
            self._emit("investigation_completed", {"tool": plan.tool, "success": result.success, "target": plan.target})
            if not result.success:
                if self.cognitive_state is not None:
                    self.cognitive_state.execution.last_result = result.error
                    self.cognitive_state.execution.pending_action = None
                    self.cognitive_state.touch()
                trace.finished = True; trace.reason = result.error or "Investigation failed."; return trace
            evidence_predicate = plan.predicate or decision.information_need.predicate or predicate
            self.engine.ingest(subject, evidence_predicate, result.output, source=f"tool:{plan.tool}", task_id=task_id)
            if self.world_ingestor is not None:
                self.world_ingestor.ingest(subject, evidence_predicate, result.output, source=f"tool:{plan.tool}", task_id=task_id)
            if self.cognitive_state is not None:
                self.cognitive_state.execution.last_action = plan.tool
                self.cognitive_state.execution.last_result = result.output
                self.cognitive_state.execution.pending_action = None
                self.cognitive_state.touch()
            needs = [n for n in needs if n is not decision.information_need]
        trace.finished = True; trace.reason = "Maximum cognitive investigation steps reached."
        return trace

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(CognitiveEvent(event_type=event_type, data=data, source="cognitive_reasoning_loop"))
