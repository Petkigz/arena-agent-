"""Turn information needs into bounded, inspectable tool requests."""
from __future__ import annotations
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional
from .information_gain import InformationNeed
from app.cognition.action_proposal import ActionProposal

# Autonomous investigations may run read-only/Level-0-1 probes from the
# manifest; anything higher needs the gated ACT path (owner confirmation),
# never a quiet background execution.
INVESTIGATION_MAX_SAFETY_LEVEL = 1


def _investigation_arguments(handler: Callable[..., Any], need: InformationNeed,
                             extracted: Optional[dict] = None) -> Optional[dict[str, Any]]:
    """Build handler-compatible arguments from an information need.

    Manifest handlers uniformly take a single ``payload`` dict (the wrapper
    filters keys to the underlying tool's parameters and drops the rest), so
    the need's question/target plus any text-extracted operands (urls, paths,
    queries) ride inside it. Returns None when a custom handler requires a
    parameter the need cannot honestly fill — that tool is skipped, not
    called with invented values."""
    try:
        params = list(inspect.signature(handler).parameters.values())
    except (TypeError, ValueError):
        return None
    named = [p for p in params if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    has_var_kw = any(p.kind is p.VAR_KEYWORD for p in params)
    names = {p.name for p in named}
    if "payload" in names or (has_var_kw and not named):
        payload = dict(extracted or {})
        payload.update({
            "query": need.question, "question": need.question,
            "text": need.question, "target": need.target,
        })
        return {"payload": payload} if "payload" in names else payload
    if has_var_kw:
        return {"query": need.question, "question": need.question, "target": need.target}
    args: dict[str, Any] = {}
    for p in named:
        if p.name in ("query", "question", "search", "text", "request", "q"):
            args[p.name] = need.question
        elif p.name in ("target", "subject", "name", "host"):
            args[p.name] = need.target
        elif p.default is inspect.Parameter.empty:
            return None  # required parameter we cannot fill honestly
    return args

@dataclass(frozen=True)
class InvestigationPlan:
    tool: str
    arguments: dict[str, Any]
    target: str
    reason: str
    priority: float
    predicate: Optional[str] = None

class InvestigationRegistry:
    """Maps semantic information needs to safe, pre-registered probes.

    P0 bottleneck #5: for needs with no pre-registered probe, planning now
    falls back to SEMANTIC DISCOVERY over the unified tool manifest — the
    agent actually has dozens of investigative tools, and 'no registered
    investigation' while they sit unused was the 'why couldn't you just
    check?' failure. Discovery is safety-filtered (Level <= 1) and only
    proposes tools whose required parameters the need can honestly fill;
    genuinely vague needs still return None (no guessing)."""
    def __init__(self, max_safety_level: int = INVESTIGATION_MAX_SAFETY_LEVEL) -> None:
        self._probes: dict[str, Callable[[InformationNeed], InvestigationPlan]] = {}
        self.max_safety_level = int(max_safety_level)

    def register(self, target: str, planner: Callable[[InformationNeed], InvestigationPlan]) -> None:
        self._probes[target] = planner

    def plan(self, need: InformationNeed) -> Optional[InvestigationPlan]:
        planner = self._probes.get(need.target)
        if planner is not None:
            plan = planner(need)
            if plan is not None:
                # Positive trust (P0 review, follow-up #4): a plan from an
                # explicitly REGISTERED internal-probe planner declares its
                # tool as an internal probe. Trust is registered at the
                # seam — never inferred from the authority not knowing the
                # name (that was the unknown-is-free hole).
                try:
                    from app.cognition.tool_registry import register_internal_probe
                    register_internal_probe(
                        plan.tool, safety_level=0,
                        source=f"investigation_planner:{need.target}")
                except Exception:
                    pass
            return plan
        return self._plan_from_manifest(need)

    def _plan_from_manifest(self, need: InformationNeed) -> Optional[InvestigationPlan]:
        try:
            from app.cognition.tool_matcher import rank_tools
            from app.tools.manifest import get_tool_manifest
            manifest = get_tool_manifest()
        except Exception:
            return None
        text = f"{need.question} {need.target} {need.reason}"
        # P0 review #12: capability entries come from the ONE authority —
        # runtime-installed investigative tools are plannable, not just
        # manifest ones. (Discovery still ranks over the manifest catalog.)
        from app.cognition.tool_registry import capability_entry
        for match in rank_tools(text, limit=8):
            entry = capability_entry(match.action_type) or manifest.get(match.action_type) or {}
            try:
                safety = int(entry.get("safety_level", 3) or 0)
            except (TypeError, ValueError):
                safety = 3
            if safety > self.max_safety_level:
                continue
            handler = entry.get("handler")
            if not callable(handler):
                continue
            arguments = _investigation_arguments(handler, need, match.payload)
            if arguments is None:
                continue
            return InvestigationPlan(
                tool=match.action_type,
                arguments=arguments,
                target=need.target,
                reason=f"Manifest-discovered investigation ({match.action_type}) for: {str(need.question)[:80]}",
                priority=need.priority,
            )
        return None

@dataclass(frozen=True)
class ActionResult:
    success: bool
    tool: str
    output: Any = None
    error: Optional[str] = None

class InvestigationExecutor:
    """Executes registered tools first; unknown names fall back to the
    unified tool manifest (P0 bottleneck #5).

    The manifest fallback never invents tools and never exceeds the
    autonomous investigation safety ceiling: gated (Level >= 2) tools return
    an honest 'requires gated execution' refusal, offline integrations
    report themselves honestly. Explicit registrations always take
    precedence, so existing behavior is unchanged."""
    def __init__(self, max_safety_level: int = INVESTIGATION_MAX_SAFETY_LEVEL) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}
        self.max_safety_level = int(max_safety_level)

    def register(self, name: str, tool: Callable[..., Any]) -> None:
        self._tools[name] = tool
        # Positive trust (P0 review, follow-up #4): an explicitly
        # registered internal-probe handler declares its name — trust is
        # registered at the seam, never inferred from absence.
        try:
            from app.cognition.tool_registry import register_internal_probe
            register_internal_probe(name, safety_level=0,
                                    source="investigation_executor")
        except Exception:
            pass

    def execute(self, plan: InvestigationPlan) -> ActionResult:
        tool = self._tools.get(plan.tool)
        if tool is not None:
            try:
                output = tool(**plan.arguments)
                return ActionResult(True, plan.tool, output=output)
            except ImportError as exc:
                # Execution observed an availability lie (follow-up review
                # #6): the cached reading must not survive this. Route
                # through the authority seam so the shared registry
                # invalidates and re-probes.
                try:
                    from app.cognition.tool_registry import note_availability_failure
                    note_availability_failure(plan.tool, str(exc))
                except Exception:
                    pass
                return ActionResult(False, plan.tool, error=f"{type(exc).__name__}: {exc}")
            except Exception as exc:
                return ActionResult(False, plan.tool, error=f"{type(exc).__name__}: {exc}")
        return self._execute_from_manifest(plan)

    def _execute_from_manifest(self, plan: InvestigationPlan) -> ActionResult:
        # P0 review #12: the capability authority decides what exists —
        # runtime-installed tools are executable investigations too, not
        # just manifest ones. Availability still flows through the ONE
        # canonical interpretation (interpret_availability).
        try:
            from app.cognition.tool_registry import capability_entry
            entry = capability_entry(plan.tool)
        except Exception as exc:
            return ActionResult(False, plan.tool, error=f"Capability registry unavailable: {exc}")
        if not entry:
            return ActionResult(False, plan.tool, error="Tool is not registered")
        try:
            safety = int(entry.get("safety_level", 3) or 0)
        except (TypeError, ValueError):
            safety = 3
        if safety > self.max_safety_level:
            return ActionResult(
                False, plan.tool,
                error=f"Requires gated execution (safety level {safety} > {self.max_safety_level}); "
                      f"autonomous investigations may only run Level <= {self.max_safety_level} probes.")
        # Canonical availability (P0 review #1): ONE interpretation — the
        # registry's interpret_availability. The old `checker() is False`
        # never fired: manifest checkers return DICTS, and
        # {"available": False, ...} is truthy, so a missing dependency was
        # 'discovered' by attempting the handler.
        try:
            from app.cognition.tool_registry import interpret_availability
            status = interpret_availability(entry.get("availability"), probe=True)
        except Exception as exc:
            return ActionResult(False, plan.tool, error=f"Availability check failed: {exc}")
        if status.get("available") is False:
            detail = (
                status.get("missing_dependency")
                or status.get("error")
                or status.get("status")
                or "dependency unavailable"
            )
            return ActionResult(
                False, plan.tool,
                error=f"Integration is currently offline or unconfigured: {detail}.")
        handler = entry.get("handler")
        if not callable(handler):
            return ActionResult(False, plan.tool, error="Tool is not registered")
        try:
            output = handler(**plan.arguments)
            return ActionResult(True, plan.tool, output=output)
        except ImportError as exc:
            # Execution observed an availability lie (follow-up review #6).
            try:
                from app.cognition.tool_registry import note_availability_failure
                note_availability_failure(plan.tool, str(exc))
            except Exception:
                pass
            return ActionResult(False, plan.tool, error=f"{type(exc).__name__}: {exc}")
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
