"""P0 #7: investigation discovery breadth is adaptive and expandable —
no hard candidate ceiling.

The investigation planner's manifest discovery used a fixed rank_tools
limit=8: for a complex, cross-domain investigation (filesystem + process +
network + logs + browser + database + vision + system state) the first
eight ranked candidates can ALL be gated or unfillable while a safe,
fillable probe sits at rank 9+. The planner returned 'no registered
investigation' anyway — a truncation artifact presented as a capability
fact.

Now the initial window is adaptive (priority tier + need-text verb breadth,
floor 8, reusing the goal interpreter's established candidate_breadth
discipline) and the scan expands iteratively until the whole ranking is
exhausted. 'No plannable investigation' is only honest after every ranked
candidate was considered. Expansion NEVER relaxes the safety ceiling or
argument fillability — it widens which tools are considered, never what is
allowed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import patch

from app.cognition.action_selection import (
    InvestigationPlan,
    InvestigationRegistry,
    _investigation_breadth,
)
from app.cognition.information_gain import InformationNeed


def _need(question: str, target: str = "subject", priority: float = 0.5) -> InformationNeed:
    return InformationNeed(question=question, target=target, reason="test", priority=priority)


# ── adaptive initial breadth ────────────────────────────────────────────────

def test_breadth_floor_preserves_simple_need_behavior():
    """A low-priority, single-verb need never scans NARROWER than the old
    fixed limit of 8 (simple -> 5-8 in the adaptive tiers)."""
    assert _investigation_breadth(_need("open chrome", priority=0.1)) == 8


def test_breadth_widens_with_priority_tier():
    """Medium-priority needs get the main tier (10), high-priority the deep
    tier (20) — the need's own urgency sizes its first look."""
    assert _investigation_breadth(_need("check the disk", priority=0.5)) == 10
    assert _investigation_breadth(_need("check the disk", priority=0.8)) == 20


def test_breadth_widens_with_multi_step_need_text_regardless_of_priority():
    """A cross-domain, multi-verb question needs several capabilities no
    matter how it was routed — the text widens the funnel on its own."""
    multi = ("Find the process, check the logs, scan the network, read the "
             "database, capture the screen and list the files")
    breadth = _investigation_breadth(_need(multi, priority=0.1))
    assert breadth >= 12, breadth


def test_breadth_is_capped():
    everything = " ".join([
        "find search locate list open read extract parse summarize convert",
        "save write create copy move rename delete compress zip unzip send",
        "email upload download install update check verify monitor analyze",
    ])
    assert _investigation_breadth(_need(everything, priority=1.0)) <= 24


# ── iterative expansion: the ranked pool is scanned to exhaustion ──────────

def _fake_match(action_type: str, score: float):
    from app.cognition.tool_matcher import ToolMatch
    # matched_terms mark these as lexically-anchored candidates — their
    # scores (often far above the 2.5 semantic-only ceiling) imply lexical
    # evidence. The planner's conceptual-only no-guessing gate therefore
    # does not apply to them; these tests are about scan order, expansion,
    # safety ceilings and fillability, not about that gate (which has its
    # own suite in tests/test_no_guessing_under_embeddings.py).
    return ToolMatch(action_type=action_type, score=score, payload={"query": "q"},
                     matched_terms=(action_type,))


def _registry_with_ranked(ranked, captured=None):
    """An InvestigationRegistry whose manifest discovery sees exactly
    `ranked` (in order) — capability_entry is patched per tool to control
    safety/fillability at each rank."""
    registry = InvestigationRegistry()

    def fake_rank(user_text, limit=6, domain_hint=None, manifest=None):
        if captured is not None:
            captured["limit"] = limit
            captured["text"] = user_text
        return list(ranked)

    entry: Dict[str, Dict[str, Any]] = {}

    def fake_capability_entry(name):
        return entry.get(name)

    # The handler takes a `payload` dict -> always fillable; safety is the
    # knob each test sets.
    def handler(payload):
        return {"success": True}

    def make(match, safety):
        entry[match.action_type] = {
            "name": match.action_type,
            "safety_level": safety,
            "handler": handler,
        }

    return registry, fake_rank, fake_capability_entry, make, entry


def test_discovery_requests_the_full_ranking_not_a_fixed_window():
    """rank_tools is called ONCE with a limit covering the whole manifest:
    it scores every tool anyway, so the old truncation bought nothing."""
    from app.tools.manifest import get_tool_manifest

    ranked = [_fake_match(f"tool_{i}", 10.0 - i) for i in range(30)]
    captured: Dict[str, Any] = {}
    registry, fake_rank, fake_entry, make, _ = _registry_with_ranked(
        ranked, captured=captured)
    for m in ranked:
        make(m, safety=3)  # all gated -> nothing plannable anywhere

    with patch("app.cognition.tool_matcher.rank_tools", side_effect=fake_rank), \
         patch("app.cognition.tool_registry.capability_entry", side_effect=fake_entry):
        plan = registry.plan(_need("why is the system slow"))

    assert plan is None, "gated everywhere -> honest None after FULL scan"
    assert captured["limit"] >= len(get_tool_manifest()), captured["limit"]


def test_safe_tool_beyond_rank_8_is_discovered():
    """THE finding: ranks 1-8 all gated/unfillable, a safe fillable probe at
    rank 12. The old limit=8 returned None; expansion must find it."""
    ranked = [_fake_match(f"gated_{i}", 10.0 - i) for i in range(11)]
    safe = _fake_match("safe_probe", 5.0)
    ranked.insert(11, safe)
    registry, fake_rank, fake_entry, make, _ = _registry_with_ranked(ranked)
    for m in ranked:
        make(m, safety=3)
    make(safe, safety=0)  # the one safe, fillable tool — at rank 12

    with patch("app.cognition.tool_matcher.rank_tools", side_effect=fake_rank), \
         patch("app.cognition.tool_registry.capability_entry", side_effect=fake_entry):
        plan = registry.plan(_need("diagnose the slowdown", priority=0.8))

    assert plan is not None
    assert plan.tool == "safe_probe"
    assert "rank 12" in plan.reason, plan.reason
    assert "12/12" in plan.reason, "the plan states the honest match rank"


def test_scan_order_stays_rank_order_first_plannable_wins():
    """Expansion widens WHICH tools are considered, not which is chosen:
    the first safe+fillable tool in rank order still wins."""
    ranked = [
        _fake_match("gated_1", 9.0),
        _fake_match("safe_early", 8.0),
        _fake_match("safe_late", 7.0),
    ]
    registry, fake_rank, fake_entry, make, _ = _registry_with_ranked(ranked)
    make(ranked[0], safety=3)
    make(ranked[1], safety=0)
    make(ranked[2], safety=0)

    with patch("app.cognition.tool_matcher.rank_tools", side_effect=fake_rank), \
         patch("app.cognition.tool_registry.capability_entry", side_effect=fake_entry):
        plan = registry.plan(_need("check things"))

    assert plan.tool == "safe_early"


def test_expansion_never_relaxes_the_safety_ceiling():
    """A gated (Level 3) tool at ANY rank is skipped, never proposed —
    expansion widens consideration, never permission."""
    ranked = [_fake_match(f"dangerous_{i}", 10.0 - i) for i in range(20)]
    registry, fake_rank, fake_entry, make, _ = _registry_with_ranked(ranked)
    for m in ranked:
        make(m, safety=3)

    with patch("app.cognition.tool_matcher.rank_tools", side_effect=fake_rank), \
         patch("app.cognition.tool_registry.capability_entry", side_effect=fake_entry):
        plan = registry.plan(_need("investigate everything", priority=1.0))

    assert plan is None


def test_unfillable_tool_is_skipped_not_guessed():
    """A tool whose required parameters the need cannot honestly fill is
    skipped at every rank — expansion does not invent arguments."""
    from app.cognition.tool_matcher import ToolMatch

    def strict_handler(a, b):  # two required params the need cannot fill
        return {"success": True}

    ranked = [
        ToolMatch(action_type="strict_tool", score=9.0, payload={},
                  matched_terms=("strict_tool",)),
        ToolMatch(action_type="fillable_tool", score=8.0, payload={},
                  matched_terms=("fillable_tool",)),
    ]
    registry = InvestigationRegistry()

    def fake_rank(user_text, limit=6, domain_hint=None, manifest=None):
        return list(ranked)

    entry = {
        "strict_tool": {"name": "strict_tool", "safety_level": 0, "handler": strict_handler},
        "fillable_tool": {"name": "fillable_tool", "safety_level": 0,
                          "handler": lambda payload: {"success": True}},
    }

    with patch("app.cognition.tool_matcher.rank_tools", side_effect=fake_rank), \
         patch("app.cognition.tool_registry.capability_entry",
               side_effect=lambda name: entry.get(name)):
        plan = registry.plan(_need("check things"))

    assert plan is not None
    assert plan.tool == "fillable_tool"


# ── real manifest behavior stays intact ────────────────────────────────────

def test_real_manifest_discovery_still_plans():
    """End-to-end over the real manifest: a capability question still plans
    (the bridge that made 170+ tools investigable stays green)."""
    plan = InvestigationRegistry().plan(
        _need("list all your capabilities", priority=0.5)
    )
    assert plan is not None
    assert plan.tool == "list_capabilities"


def test_real_manifest_still_refuses_vague_needs():
    """The no-guessing contract: a genuinely vague need matches nothing
    above the noise floor — expansion cannot rescue an empty pool."""
    assert InvestigationRegistry().plan(_need("what is this", target="mystery")) is None


def test_plan_reason_carries_rank_evidence():
    """The chosen plan states its rank in the ranking — how well-matched the
    tool was is now visible evidence, not a silent truncation."""
    plan = InvestigationRegistry().plan(
        _need("list all your capabilities", priority=0.5)
    )
    assert plan is not None
    assert "rank " in plan.reason and "/" in plan.reason
