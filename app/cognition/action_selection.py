"""Turn information needs into bounded, inspectable tool requests."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional
from .information_gain import InformationNeed

@dataclass(frozen=True)
class InvestigationPlan:
    tool: str
    arguments: dict[str, Any]
    target: str
    reason: str
    priority: float

class InvestigationRegistry:
    """Maps semantic information needs to safe, pre-registered probes."""
    def __init__(self) -> None:
        self._probes: dict[str, Callable[[InformationNeed], InvestigationPlan]] = {}

    def register(self, target: str, planner: Callable[[InformationNeed], InvestigationPlan]) -> None:
        self._probes[target] = planner

    def plan(self, need: InformationNeed) -> Optional[InvestigationPlan]:
        planner = self._probes.get(need.target)
        return planner(need) if planner else None

class ActionSelector:
    """Separates deciding *what is needed* from executing a tool."""
    def __init__(self, registry: InvestigationRegistry | None = None) -> None:
        self.registry = registry or InvestigationRegistry()

    def select(self, need: InformationNeed) -> Optional[InvestigationPlan]:
        return self.registry.plan(need)
