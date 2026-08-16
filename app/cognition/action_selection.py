"""Turn information needs into bounded, inspectable tool requests."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional
from .information_gain import InformationNeed
from app.cognition.action_proposal import ActionProposal

@dataclass(frozen=True)
class InvestigationPlan:
    tool: str
    arguments: dict[str, Any]
    target: str
    reason: str
    priority: float
    predicate: Optional[str] = None

class InvestigationRegistry:
    """Maps semantic information needs to safe, pre-registered probes."""
    def __init__(self) -> None:
        self._probes: dict[str, Callable[[InformationNeed], InvestigationPlan]] = {}
    def register(self, target: str, planner: Callable[[InformationNeed], InvestigationPlan]) -> None:
        self._probes[target] = planner
    def plan(self, need: InformationNeed) -> Optional[InvestigationPlan]:
        planner = self._probes.get(need.target)
        return planner(need) if planner else None

@dataclass(frozen=True)
class ActionResult:
    success: bool
    tool: str
    output: Any = None
    error: Optional[str] = None

class InvestigationExecutor:
    """Executes only explicitly registered tools; never evaluates arbitrary names."""
    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
    def register(self, name: str, tool: Callable[..., Any]) -> None:
        self._tools[name] = tool
    def execute(self, plan: InvestigationPlan) -> ActionResult:
        tool = self._tools.get(plan.tool)
        if tool is None:
            return ActionResult(False, plan.tool, error="Tool is not registered")
        try:
            output = tool(**plan.arguments)
            return ActionResult(True, plan.tool, output=output)
        except Exception as exc:
            return ActionResult(False, plan.tool, error=f"{type(exc).__name__}: {exc}")

class ActionSelector:
    """Separates deciding *what is needed* from executing a tool."""
    def __init__(self, registry: InvestigationRegistry | None = None) -> None:
        self.registry = registry or InvestigationRegistry()

    def select(self, need: InformationNeed) -> Optional[InvestigationPlan]:
        return self.registry.plan(need)

    def select_action_for_query(self, query_text: str, complexity: str = "fast") -> ActionProposal:
        """
        Cognitive Action Selector that uses ActionPlanner & CounterfactualSimulator
        to evaluate candidate action branches and output the optimal ActionProposal.
        """
        from app.cognition.action_planner import ActionPlanner
        return ActionPlanner.plan_and_evaluate_action(query_text, complexity=complexity)
