"""Closed observe -> reason -> investigate -> observe cognitive loop."""
from __future__ import annotations
import time as _time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ReasoningBudget:
    """A multi-dimensional reasoning budget (P0 bottleneck #13).

    A step count is a fake budget: the real resources are wall-clock time,
    tool calls, and accumulated risk. 'One more investigation would solve
    it' must be a BUDGET decision, not an arbitrary max_steps=3 stop.

    Dimensions:
      time_s          wall-clock budget for the whole loop
      max_tool_calls  investigation (tool-call) budget — the loop's real cost
      max_risk        cumulative risk budget: each autonomous probe costs its
                      safety level (Level-0 probes are free, Level-1 cost 1)
      max_steps       absolute iteration ceiling — a safety net, NOT the
                      governing bound
      max_tokens      token budget: enforced where LLM calls happen (the
                      pipeline/LLM layer), not invented here — the loop
                      itself is deterministic plus tool calls. Carried so
                      callers can thread one budget object everywhere.
    """
    time_s: float = 30.0
    max_tool_calls: int = 8
    max_risk: float = 6.0
    max_steps: int = 20
    max_tokens: Optional[int] = None

    @classmethod
    def for_complexity(cls, complexity: str) -> "ReasoningBudget":
        """Budget scales with the requested reasoning depth: quick chat
        questions stay tight; deep goals get room to actually investigate."""
        c = str(complexity or "fast").strip().lower()
        if c == "fast":
            return cls(time_s=10.0, max_tool_calls=3, max_risk=2.0, max_steps=6,
                       max_tokens=2048)
        if c in ("main", "standard"):
            return cls(time_s=30.0, max_tool_calls=8, max_risk=6.0, max_steps=20,
                       max_tokens=8192)
        # deep / reasoning-heavy routes
        return cls(time_s=90.0, max_tool_calls=16, max_risk=12.0, max_steps=40,
                   max_tokens=32768)
from .action_selection import ActionSelector, InvestigationExecutor, InvestigationPlan, ActionResult
from .belief_engine import BeliefEngine
from .cognitive_state import CognitiveState
from .event_bus import EventBus
from .events import CognitiveEvent
from .information_gain import InformationNeed
from .reasoning_cycle import ReasoningAction, ReasoningCycle, ReasoningDecision
from .world_ingest import WorldIngestor
from .source_types import SourceType

@dataclass
class CycleTrace:
    decisions: list[ReasoningDecision] = field(default_factory=list)
    plans: list[InvestigationPlan] = field(default_factory=list)
    results: list[ActionResult] = field(default_factory=list)
    finished: bool = False
    reason: str = ""
    # Honest budget accounting for this cycle (P0 #13): what was spent and
    # against which limits.
    budget_used: Dict[str, Any] = field(default_factory=dict)

class CognitiveReasoningLoop:
    """Runs a bounded cognitive loop without allowing the reasoning model to execute arbitrary tools."""
    def __init__(self, engine: Optional[BeliefEngine] = None, action_selector: Optional[ActionSelector] = None,
                 executor: Optional[InvestigationExecutor] = None, world_ingestor: Optional[WorldIngestor] = None,
                 event_bus: Optional[EventBus] = None, cognitive_state: Optional[CognitiveState] = None,
                 max_steps: int = 20) -> None:
        self.engine = engine or BeliefEngine()
        self.cycle = ReasoningCycle(self.engine)
        self.action_selector = action_selector or ActionSelector()
        self.executor = executor or InvestigationExecutor()
        self.world_ingestor = world_ingestor
        self.event_bus = event_bus
        self.cognitive_state = cognitive_state
        # max_steps is the ABSOLUTE safety ceiling; the governing bound is
        # the per-run ReasoningBudget (time / tool calls / risk).
        self.max_steps = max(1, min(max_steps, 50))

    def run(self, subject: str, predicate: str, *, value: Any = None, source: Optional[str] = None,
            confidence: float = 1.0, observation_type: str = "self_reported",
            information_needs: Optional[list[InformationNeed]] = None,
            task_id: Optional[str] = None, action_available: bool = True,
            proposed_action: Optional[Any] = None,
            available_capabilities: Optional[dict[str, bool]] = None,
            budget: Optional[ReasoningBudget] = None) -> CycleTrace:
        # P0 #13: a per-RUN budget (fresh each cycle), bounded by the
        # constructor's step ceiling. Default = the main-tier budget.
        budget = budget or ReasoningBudget()
        max_iterations = max(1, min(self.max_steps, budget.max_steps))
        deadline = _time.monotonic() + float(budget.time_s)
        tool_calls_used = 0
        risk_used = 0.0
        started = _time.monotonic()

        def _finish(trace: CycleTrace, reason: str) -> CycleTrace:
            trace.finished = True
            trace.reason = reason
            trace.budget_used = {
                "steps_taken": len(trace.decisions),
                "tool_calls": tool_calls_used,
                "risk_used": round(risk_used, 2),
                "elapsed_s": round(_time.monotonic() - started, 2),
                "limits": {"time_s": budget.time_s, "max_tool_calls": budget.max_tool_calls,
                           "max_risk": budget.max_risk, "max_steps": max_iterations,
                           "max_tokens": budget.max_tokens},
            }
            return trace

        trace = CycleTrace()
        if self.cognitive_state is not None:
            self.cognitive_state.attention.focus = f"{subject}.{predicate}"
            self.cognitive_state.task.current_step = "reasoning"
            self.cognitive_state.reasoning["status"] = "observing"
            self.cognitive_state.touch()
        if source is not None:
            self.engine.ingest(subject, predicate, value, source=source,
                             observation_type=observation_type,
                             confidence=confidence, task_id=task_id)
        needs = list(information_needs or [])
        synthesized_need_used = False
        for _ in range(max_iterations):
            decision = self.cycle.decide(
                subject,
                predicate,
                information_needs=needs,
                action_available=action_available,
                proposed_action=proposed_action,
                available_capabilities=available_capabilities
            )
            trace.decisions.append(decision)
            if self.cognitive_state is not None:
                self.cognitive_state.reasoning["confidence"] = decision.confidence
                self.cognitive_state.reasoning["hypotheses"] = list(decision.belief.alternatives) if decision.belief else []
                self.cognitive_state.reasoning["status"] = decision.action.value
                self.cognitive_state.touch()
            self._emit("reasoning_decision", {"subject": subject, "predicate": predicate, "action": decision.action.value, "confidence": decision.confidence})
            if decision.action in (ReasoningAction.ANSWER, ReasoningAction.DEFER, ReasoningAction.ACT):
                return _finish(trace, decision.reason)
            if decision.action is ReasoningAction.INVESTIGATE and decision.information_need is None and not needs and not synthesized_need_used:
                # P0 bottleneck #5: an INVESTIGATE decision with no explicit
                # information need used to dead-end the loop BEFORE the
                # registry was ever consulted ("why couldn't you just
                # check?"). The user's question IS the information need:
                # synthesize one (once, bounded) so the manifest-backed
                # investigation path can actually gather evidence.
                synthesized_need_used = True
                decision = replace(decision, information_need=InformationNeed(
                    question=str(value or subject),
                    target=subject,
                    reason="Synthesized from the user's question (no explicit information need supplied).",
                    priority=0.6,
                ))
                needs.append(decision.information_need)
            if decision.action is not ReasoningAction.INVESTIGATE or decision.information_need is None:
                return _finish(trace, decision.reason)
            # Budget gates BEFORE each investigation: stopping is a RESOURCE
            # decision, honestly named — never an arbitrary step count.
            if _time.monotonic() > deadline:
                return _finish(trace, f"Reasoning time budget exhausted "
                                      f"({budget.time_s:.0f}s) after {tool_calls_used} investigation(s).")
            if tool_calls_used >= budget.max_tool_calls:
                return _finish(trace, f"Reasoning tool-call budget exhausted "
                                      f"({budget.max_tool_calls}) — remaining information needs: "
                                      f"{len(needs)}.")
            plan = self.action_selector.select(decision.information_need)
            probe_risk = self._probe_risk_cost(plan.tool if plan is not None else None)
            if risk_used + probe_risk > budget.max_risk:
                return _finish(trace, f"Reasoning risk budget exhausted "
                                      f"({risk_used:.0f}/{budget.max_risk:.0f}) — the next probe "
                                      f"requires escalation.")
            if plan is None:
                return _finish(trace, f"No safe investigation tool matched the need "
                                      f"'{str(decision.information_need.question)[:60]}'.")
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
                return _finish(trace, result.error or "Investigation failed.")
            # Latent bug surfaced by P0 #5: this path never executed while
            # the registry was empty, and InformationNeed has no 'predicate'
            # field (question/target/reason/priority).
            evidence_predicate = plan.predicate or getattr(decision.information_need, "predicate", None) or predicate
            self.engine.ingest(subject, evidence_predicate, result.output,
                             source=SourceType.TOOL_OUTPUT,
                             observation_type="inferred", task_id=task_id)
            if self.world_ingestor is not None:
                self.world_ingestor.ingest(subject, evidence_predicate, result.output, source=SourceType.TOOL_OUTPUT, task_id=task_id, observation_type="inferred")
            if self.cognitive_state is not None:
                self.cognitive_state.execution.last_action = plan.tool
                self.cognitive_state.execution.last_result = result.output
                self.cognitive_state.execution.pending_action = None
                self.cognitive_state.touch()
            needs = [n for n in needs if n is not decision.information_need]
            tool_calls_used += 1
            risk_used += probe_risk
        return _finish(trace, f"Reasoning budget exhausted: {tool_calls_used} investigation(s), "
                              f"{_time.monotonic() - started:.1f}s, risk {risk_used:.0f}.")

    @staticmethod
    def _probe_risk_cost(tool_name: Optional[str]) -> float:
        """Risk cost of the planned investigation: the tool's manifest safety
        level (Level-0 read-only probes are free, Level-1 cost 1; autonomous
        probes are capped at Level 1 by the investigation executor)."""
        if not tool_name:
            return 0.0
        try:
            from app.tools.manifest import get_tool_manifest
            entry = get_tool_manifest().get(tool_name) or {}
            return float(entry.get("safety_level", 0) or 0)
        except Exception:
            return 0.0

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(CognitiveEvent(event_type=event_type, data=data, source="cognitive_reasoning_loop"))
