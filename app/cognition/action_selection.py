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

    def select_action_for_query(self, query_text: str) -> str:
        """
        Cognitive Action Selector that inspects semantic goal intent and maps it to fine-grained action type.
        """
        text_lower = query_text.lower().strip()

        if any(k in text_lower for k in ["phone", "mobile", "battery", "charged", "sms", "call ", "text "]):
            return "phone_command"
        elif any(k in text_lower for k in ["youtube", "google", "search web", "look up", "browser"]):
            return "web_search"
        elif any(k in text_lower for k in ["open ", "launch ", "start ", "run "]):
            return "open_application"
        elif any(k in text_lower for k in ["find file", "song", "ordinary", "search my pc", "document", "folder"]):
            return "search_files"
        elif any(k in text_lower for k in ["screenshot", "capture screen", "what is on my screen"]):
            return "screen_capture"
        elif any(k in text_lower for k in ["opsec", "footprint", "breach", "remove my data"]):
            return "opsec_audit"
        elif any(k in text_lower for k in ["daily briefing", "morning report"]):
            return "daily_briefing"
        elif any(k in text_lower for k in ["what is", "calculate", "tell me", "explain", "who is", "how do"]):
            return "formulate_answer"
        else:
            return "user_task"
