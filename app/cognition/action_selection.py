"""Turn information needs into bounded, inspectable tool requests."""
from __future__ import annotations
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional
from .information_gain import InformationNeed
from app.cognition.action_proposal import ActionProposal
from app.utils.logger import app_logger

# Autonomous investigations may run read-only/Level-0-1 probes from the
# manifest; anything higher needs the gated ACT path (owner confirmation),
# never a quiet background execution.
INVESTIGATION_MAX_SAFETY_LEVEL = 1


def _investigation_breadth(need: InformationNeed) -> int:
    """Adaptive candidate window for manifest-discovered investigations (P0 #7).

    The old hard limit=8 starved complex, cross-domain investigations: the
    first eight ranked candidates can ALL be gated or unfillable while a
    safe, fillable probe sits at rank 9-25. The initial window now scales
    with two honest signals, reusing the goal interpreter's established
    breadth discipline (P0 review #3) rather than a second, divergent scale:

      * the need's PRIORITY tier — deep (>= 0.66) -> 20, main (>= 0.33) ->
        10, fast -> 5. Priority is the need's own urgency: a high-priority
        unknown deserves a wide first look, not a peephole.
      * the need's own TEXT breadth — distinct action verbs in the question
        widen the funnel (a five-step question needs several capabilities
        no matter how it was routed), up to the shared cap of 24.

    8 is the floor, so simple needs never scan NARROWER than before. When
    even the widened window finds nothing safe+fillable, _plan_from_manifest
    expands iteratively — this breadth is the first window, not the ceiling.
    """
    from app.cognition.goal_interpreter import candidate_breadth
    try:
        priority = float(need.priority or 0.5)
    except (TypeError, ValueError):
        priority = 0.5
    tier = "deep" if priority >= 0.66 else "main" if priority >= 0.33 else "fast"
    text = f"{need.question} {need.target} {need.reason}"
    return max(8, candidate_breadth(text, tier))


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

        # P0 #7 — adaptive breadth + iterative expansion, not a hard limit=8.
        # rank_tools scores EVERY manifest tool and sorts; its limit is pure
        # truncation of an already-complete ranking, and the 1.5 noise floor
        # already removes junk. So discovery ranks ONCE over the whole
        # manifest, and the scan walks that ranking in EXPANDING windows:
        # an adaptive initial breadth (see _investigation_breadth), doubling
        # whenever a whole window contained nothing safe+fillable, until the
        # ranking is exhausted. The old ceiling could return 'no registered
        # investigation' while a safe, fillable probe sat at rank 9+ — for a
        # cross-domain investigation (filesystem, process, network, logs,
        # browser, database, vision, system state) the first eight ranked
        # candidates can easily ALL be gated or unfillable. 'No plannable
        # investigation' is only honest after the WHOLE ranking was scanned.
        # The scan order never changes: rank order. Expansion never relaxes
        # the safety ceiling or argument fillability — it only widens WHICH
        # tools are considered, never what is allowed.
        ranked = rank_tools(text, limit=max(1, len(manifest)))
        window = _investigation_breadth(need)
        start = 0
        while start < len(ranked):
            for offset, match in enumerate(ranked[start:start + window]):
                # No-guessing under embeddings (owner-machine finding): a
                # candidate with ZERO lexical evidence (empty matched_terms)
                # rests on embedding similarity alone — on a configured
                # machine that saturates the noise floor at exactly 1.5
                # (2.5 × calibrated 0.6) and let 'what is this' autonomously
                # plan a directory listing. Discovery may PROPOSE
                # conceptual-only candidates (they surface as suggestions);
                # an AUTONOMOUS plan needs lexical anchoring or clearly
                # strong semantic confidence, not a calibrated-threshold
                # near-miss.
                if not match.matched_terms and (match.semantic_score or 0.0) < 0.75:
                    continue
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
                rank = start + offset + 1
                return InvestigationPlan(
                    tool=match.action_type,
                    arguments=arguments,
                    target=need.target,
                    reason=(f"Manifest-discovered investigation ({match.action_type}, "
                            f"rank {rank}/{len(ranked)}) for: {str(need.question)[:80]}"),
                    priority=need.priority,
                )
            start += window
            remaining = len(ranked) - start
            if remaining > 0:
                app_logger.info(
                    f"Investigation discovery: no safe+fillable tool in the first "
                    f"{start} ranked candidates; expanding window by {min(2 * window, remaining)} "
                    f"more ({remaining} remaining) for: {str(need.question)[:60]}"
                )
                window *= 2
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
