"""P0 bottleneck #5: the investigation path is bridged to the actual tool
ecosystem. Previously InvestigationRegistry had zero registered probes and
InvestigationExecutor an empty _tools dict — 'No registered investigation'
was the only possible outcome while 170+ tools sat unused. Now:
registry -> semantic discovery over the manifest (safety-filtered, honest
argument filling), executor -> manifest handlers with an autonomous-safety
ceiling, and the reasoning loop synthesizes the information need from the
user's question instead of dead-ending."""
from app.cognition.action_selection import (
    ActionSelector, InvestigationExecutor, InvestigationRegistry, InvestigationPlan,
)
from app.cognition.belief_engine import BeliefEngine
from app.cognition.information_gain import InformationNeed
from app.cognition.reasoning_loop import CognitiveReasoningLoop
from app.tools.manifest import get_tool_manifest


def _need(question, target="subject"):
    return InformationNeed(question=question, target=target, reason="test")


def test_registry_discovers_manifest_tools():
    """A need with no pre-registered probe is planned from the manifest."""
    plan = InvestigationRegistry().plan(_need("list all your capabilities"))
    assert plan is not None
    assert plan.tool == "list_capabilities"
    assert get_tool_manifest()[plan.tool]["safety_level"] <= 1
    assert "payload" in plan.arguments


def test_registry_still_refuses_vague_needs():
    """Genuinely vague needs match nothing — no guessing (the old contract's
    intent, preserved)."""
    assert InvestigationRegistry().plan(_need("what is this", target="mystery")) is None


def test_preregistered_probe_wins_over_manifest():
    registry = InvestigationRegistry()
    registry.register("chrome", lambda n: InvestigationPlan(
        tool="process_inspector", arguments={"name": "chrome.exe"},
        target=n.target, reason=n.reason, priority=n.priority))
    plan = registry.plan(_need("is chrome responsive", target="chrome"))
    assert plan.tool == "process_inspector"


def test_registry_never_proposes_gated_tools():
    """Autonomous investigation discovery is capped at safety level 1."""
    plan = InvestigationRegistry().plan(_need("move the mouse and click the button"))
    if plan is not None:  # anything it proposes must be a safe probe
        assert get_tool_manifest()[plan.tool]["safety_level"] <= 1


def test_executor_runs_manifest_tools():
    """A manifest tool with no local registration executes for real."""
    executor = InvestigationExecutor()
    plan = InvestigationPlan(tool="list_capabilities", arguments={"payload": {}},
                             target="subject", reason="test", priority=0.5)
    result = executor.execute(plan)
    assert result.success is True
    assert result.output.get("tool_count", 0) >= 100


def test_executor_refuses_gated_tools_honestly():
    executor = InvestigationExecutor()
    plan = InvestigationPlan(tool="mouse_click", arguments={"payload": {}},
                             target="subject", reason="test", priority=0.5)
    result = executor.execute(plan)
    assert result.success is False
    assert "gated" in result.error


def test_executor_unknown_name_still_honest():
    result = InvestigationExecutor().execute(InvestigationPlan(
        tool="quantum_teleportation", arguments={}, target="x", reason="r", priority=0.5))
    assert result.success is False
    assert "not registered" in result.error


def test_executor_local_registration_takes_precedence():
    executor = InvestigationExecutor()
    executor.register("list_capabilities", lambda **kw: "local-wins")
    result = executor.execute(InvestigationPlan(
        tool="list_capabilities", arguments={}, target="x", reason="r", priority=0.5))
    assert result.success is True and result.output == "local-wins"


def test_loop_investigates_from_the_manifest_end_to_end():
    """INVESTIGATE with no explicit need used to dead-end before the
    registry; now the question itself becomes the need and a real, safe
    manifest tool actually runs."""
    loop = CognitiveReasoningLoop(engine=BeliefEngine(), max_steps=3)
    trace = loop.run(subject="capabilities", predicate="information_need",
                     value="list all your capabilities")
    assert trace.plans and trace.plans[0].tool == "list_capabilities"
    assert trace.results and trace.results[0].success is True
    assert trace.results[0].output.get("tool_count", 0) >= 100


def test_loop_need_synthesis_is_bounded():
    """The synthesized need fires once — no endless re-synthesis."""
    loop = CognitiveReasoningLoop(engine=BeliefEngine(), max_steps=5)
    trace = loop.run(subject="capabilities", predicate="information_need",
                     value="list all your capabilities")
    assert len(trace.plans) == 1


def test_single_word_synonyms_match_on_word_boundaries():
    """Regression: bare substring matching made synonym 'text' fire inside
    'context', so phone_sms scored 2.0 on nearly every English sentence."""
    from app.cognition.tool_matcher import rank_tools, match_control_tool
    hits = rank_tools("what is this unknown insufficient context", limit=5)
    assert "phone_sms" not in [h.action_type for h in hits]
    # The real act path (a dialable number present) still matches.
    m = match_control_tool("text 0771234567 that i will be late")
    assert m is not None and m.action_type == "phone_sms"
