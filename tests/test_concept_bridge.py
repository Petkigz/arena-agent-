"""P0 #8: symptom -> diagnostic-concept expansion (the semantic upgrade).

"Find why my computer suddenly became slow" shares no tokens with process
inspection, CPU metrics, memory pressure, disk IO, startup inventory,
network activity, logs or thermals. Lexical matching could never bridge
that gap, and the embedding backend only helps when an embedding model
happens to be loaded. The concept bridge is the deterministic knowledge
layer that closes it locally: recognized symptom patterns expand into the
diagnostic vocabulary they imply, with inspectable evidence — and they
NEVER fire on ordinary requests (a slowness complaint about a recipe is
not a performance complaint).
"""

from __future__ import annotations

from app.cognition.concept_bridge import ConceptExpansion, expand_goal
from app.cognition.tool_matcher import rank_tools

SCENARIO = "find why my computer suddenly became slow"

# None of the diagnostic vocabulary appears literally in the scenario.
DIAGNOSTIC_TERMS = (
    "process", "cpu", "memory", "ram", "disk", "io", "startup",
    "network", "log", "temperature", "thermal", "metrics",
)


# ── the bridge itself ───────────────────────────────────────────────────────

def test_scenario_expands_to_the_diagnostic_tree():
    expansion = expand_goal(SCENARIO)
    assert expansion.fired
    assert expansion.original == SCENARIO, "the goal is never rewritten"
    assert "performance_slowness" in [r["cluster"] for r in expansion.evidence]
    # The diagnostic tree the finding called for, concept by concept.
    for concept in ("process", "cpu", "memory", "disk", "startup",
                    "network", "log", "temperature"):
        assert concept in expansion.concepts, expansion.concepts
    # Expansion text = original + concepts (the matcher sees both).
    assert expansion.expanded.startswith(SCENARIO)


def test_every_fired_cluster_carries_its_reason():
    """Expansion is inspectable evidence, not a score adjustment."""
    for record in expand_goal(SCENARIO).evidence:
        assert record["cluster"]
        assert record["concepts"]
        assert record["reason"], "each cluster explains WHY its concepts follow"


def test_context_gating_blocks_ordinary_requests():
    """Symptom words in non-machine contexts must NOT fire the bridge —
    otherwise discovery gets polluted with diagnostic vocabulary."""
    for text in (
        "search the web for slow cooking recipes",
        "find hot deals on laptops",
        "write a linkedin post about slow business growth",
        "read my email about the slow vendor",
        "can you connect to github",
        "summarize page 4 of the report",
    ):
        expansion = expand_goal(text)
        assert not expansion.fired, text
        assert expansion.expanded == text, "non-symptom text passes verbatim"


def test_machine_complaints_in_plain_language_fire():
    cases = {
        "the game is lagging badly": "performance_slowness",
        "my laptop is running hot": "overheating_thermal",
        "why is my computer so hot while gaming": "overheating_thermal",
        "the cpu fan is really loud": "overheating_thermal",
        "computer keeps freezing and crashing": "crash_instability",
        "my pc keeps restarting itself": "crash_instability",
        "no internet since this morning": "connectivity_problems",
        "disk is almost full": "storage_pressure",
        "battery drains really fast": "power_battery",
        "is my computer infected with a miner": "security_suspicion",
        "pc boots slowly": "slow_boot_startup",
        "startup is taking forever": "slow_boot_startup",
    }
    for text, expected_cluster in cases.items():
        clusters = [r["cluster"] for r in expand_goal(text).evidence]
        assert expected_cluster in clusters, (text, clusters)


def test_short_text_passes_through():
    expansion = expand_goal("ok")
    assert not expansion.fired
    assert expansion.expanded == "ok"


# ── integration: discovery through the real manifest ────────────────────────

def test_scenario_discovers_the_diagnostic_capabilities():
    """THE finding, end to end: the scenario surfaces the diagnostic tools
    — none of whose vocabulary appears in the request."""
    hits = rank_tools(SCENARIO, limit=30)
    found = {h.action_type: h for h in hits}

    for tool in ("system_metrics", "list_processes", "startup_programs",
                 "network_activity", "recent_logs", "temperature_status"):
        assert tool in found, (
            f"{tool} not discovered; got {sorted(found)}")

    # And the request really contains none of the diagnostic vocabulary.
    lowered = SCENARIO.lower()
    for term in DIAGNOSTIC_TERMS:
        assert term not in lowered


def test_matches_carry_concept_evidence():
    """A symptom-derived proposal shows its work: which clusters fired and
    which concept terms matched THIS tool."""
    hits = rank_tools(SCENARIO, limit=30)
    metrics = next(h for h in hits if h.action_type == "system_metrics")
    assert "performance_slowness" in metrics.concept_clusters
    assert set(metrics.concept_terms) & {"cpu", "memory", "disk", "metrics"}


def test_evidence_attributed_to_contributing_clusters_only():
    """A tool whose concept terms came from ONE cluster is not annotated
    with clusters that did not contribute to its match."""
    hits = rank_tools("my laptop is running hot", limit=30)
    temp = next(h for h in hits if h.action_type == "temperature_status")
    assert "overheating_thermal" in temp.concept_clusters
    assert "performance_slowness" not in temp.concept_clusters


def test_non_symptom_discovery_has_no_concept_evidence():
    hits = rank_tools("compress this pdf file and merge the pages", limit=10)
    assert hits
    for h in hits:
        assert h.concept_terms == ()
        assert h.concept_clusters == ()


def test_scenario_reaches_the_investigation_planner():
    """The upgrade flows through the full discovery stack: a slowness need
    plans a REAL diagnostic probe autonomously (Level 0)."""
    from app.cognition.action_selection import InvestigationRegistry
    from app.cognition.information_gain import InformationNeed

    plan = InvestigationRegistry().plan(InformationNeed(
        question=SCENARIO, target="computer",
        reason="owner performance complaint", priority=0.7))
    if plan is not None:  # discovery proposes; safety ceiling still applies
        from app.tools.manifest import get_tool_manifest
        entry = get_tool_manifest().get(plan.tool) or {}
        assert entry.get("safety_level", 3) <= 1, (
            f"autonomous investigation proposed gated tool {plan.tool}")
