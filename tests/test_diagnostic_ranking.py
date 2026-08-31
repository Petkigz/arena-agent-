"""Diagnostic hypothesis ranking (P2 review).

The concept bridge's breadth is right for DISCOVERY but widens the
candidate surface: 'my computer is slow' puts the whole diagnostic tree
in competition. This suite pins the layer that resolves the competition —
probes ordered by how much they DISCRIMINATE between the hypotheses the
symptom actually makes plausible:

  * vague symptom -> broad measurement first (covers the most hypotheses)
  * specific symptom -> the specific probe first (its cluster's weight
    is concentrated on one hypothesis)
  * co-occurring symptoms strengthen shared explanations
  * the planner says WHICH hypotheses the chosen probe discriminates
  * non-diagnostic goals keep discovery's lexical order untouched
"""
from app.cognition.concept_bridge import expand_goal
from app.cognition.diagnostic_ranking import (
    active_hypotheses,
    rank_probes_by_discrimination,
)


def _clusters(text):
    return [e["cluster"] for e in expand_goal(text).evidence]


# ── the hypothesis model ────────────────────────────────────────────────────

def test_vague_slowness_ranks_broad_measurement_first():
    """Plain slowness makes four hypotheses equally plausible with no way
    to tell them apart: system_metrics (CPU+memory+disk) and
    list_processes (CPU+memory+background) discriminate the most;
    one-hypothesis probes rank strictly below them."""
    ranked = rank_probes_by_discrimination(["performance_slowness"])
    top = [r.tool for r in ranked[:2]]
    assert set(top) == {"system_metrics", "list_processes"}, ranked
    narrow = {r.tool: r.score for r in ranked}
    assert narrow["startup_programs"] < narrow["system_metrics"]
    # For a pure slowness complaint these bear on NOTHING active:
    assert "temperature_status" not in narrow
    assert "recent_logs" not in narrow
    assert "network_activity" not in narrow


def test_specific_boot_complaint_ranks_startup_inventory_first():
    """'Startup is taking forever' concentrates the boot cluster's whole
    weight on startup_bloat — the specific probe outranks the generic
    broad sweep that wins for vague slowness."""
    ranked = rank_probes_by_discrimination(
        ["performance_slowness", "slow_boot_startup"])
    assert ranked[0].tool == "startup_programs", ranked
    scores = {r.tool: r.score for r in ranked}
    assert scores["startup_programs"] > scores["system_metrics"]


def test_co_occurring_symptoms_strengthen_shared_explanations():
    """Heat AND crashes both implicate thermal throttling: the shared
    hypothesis accumulates weight from both clusters, so
    temperature_status outranks what either symptom alone would rank it."""
    heat_only = {
        r.tool: r.score for r in rank_probes_by_discrimination(
            ["overheating_thermal"])}
    heat_and_crash_list = rank_probes_by_discrimination(
        ["overheating_thermal", "crash_instability"])
    heat_and_crash = {r.tool: r.score for r in heat_and_crash_list}
    assert heat_and_crash["temperature_status"] > heat_only["temperature_status"]
    # and the shared explanation outranks the heat cluster's other option
    # (scores tie; the tie-break prefers the probe testing the STRONGEST
    # hypothesis — thermal_throttling, strengthened by both symptoms)
    order = [r.tool for r in heat_and_crash_list]
    assert order.index("temperature_status") < order.index("system_metrics")


def test_connectivity_is_one_concentrated_hypothesis():
    ranked = rank_probes_by_discrimination(["connectivity_problems"])
    assert ranked[0].tool == "network_activity"


def test_no_hypotheses_means_no_reordering():
    """Clusters without probe-bearing hypotheses (battery today) rank
    nothing — the caller leaves discovery's order untouched."""
    assert rank_probes_by_discrimination(["power_battery"]) == []
    assert rank_probes_by_discrimination([]) == []
    assert active_hypotheses(["power_battery"]) == []


def test_ranking_is_deterministic():
    """Same inputs, same order — score desc, then name asc for ties."""
    a = rank_probes_by_discrimination(["performance_slowness"])
    b = rank_probes_by_discrimination(["performance_slowness"])
    assert [r.tool for r in a] == [r.tool for r in b]


# ── planner integration ─────────────────────────────────────────────────────

def test_slow_computer_plans_broad_measurement_not_random_tree_member():
    """The review's exact case: 'my computer is slow' must plan the probe
    that discriminates the most active hypotheses — not whichever of the
    six competing diagnostic tools shares the most tokens with the
    injected vocabulary."""
    from app.cognition.action_selection import InvestigationRegistry
    from app.cognition.information_gain import InformationNeed

    plan = InvestigationRegistry().plan(InformationNeed(
        question="my computer is slow", target="computer",
        reason="owner performance complaint", priority=0.5))
    assert plan is not None
    assert plan.tool in ("system_metrics", "list_processes"), plan.tool
    # The plan SHOWS its discrimination evidence.
    assert "hypotheses" in plan.reason


def test_boot_complaint_plans_startup_inventory():
    """A specific complaint plans the specific probe, ahead of the broad
    sweep that wins for vague slowness."""
    from app.cognition.action_selection import InvestigationRegistry
    from app.cognition.information_gain import InformationNeed

    plan = InvestigationRegistry().plan(InformationNeed(
        question="startup is taking forever", target="computer",
        reason="owner boot complaint", priority=0.5))
    assert plan is not None
    assert plan.tool == "startup_programs", plan.tool


def test_non_diagnostic_goal_keeps_lexical_order():
    """No symptom fired -> no reordering: a capability question still
    plans list_capabilities exactly as before (and the live-script B3
    'rank evidence' contract still holds)."""
    from app.cognition.action_selection import InvestigationRegistry
    from app.cognition.information_gain import InformationNeed

    plan = InvestigationRegistry().plan(InformationNeed(
        question="list all your capabilities", target="arena",
        reason="live verification", priority=0.5))
    assert plan is not None
    assert plan.tool == "list_capabilities"
    assert "rank " in plan.reason and "/" in plan.reason
    assert "hypotheses" not in plan.reason


def test_vague_needs_still_refuse_under_ranking():
    """The hypothesis layer must not open a guessing path: a vague need
    with no fired clusters still plans NOTHING."""
    from app.cognition.action_selection import InvestigationRegistry
    from app.cognition.information_gain import InformationNeed

    assert InvestigationRegistry().plan(InformationNeed(
        question="what is this", target="mystery",
        reason="test", priority=0.5)) is None
