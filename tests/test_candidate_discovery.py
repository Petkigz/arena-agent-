"""P0 bottleneck #3: candidate generation flows from the manifest by
semantic matching, not from hard-coded per-domain shortlists.

'filesystem' used to propose ONLY search_files + web_search while 170+
tools (compress_files, pdf_merge, analyze_data, ping, ...) were
unreachable from the candidate pipeline. Now:
goal -> representation -> capability discovery (manifest) ->
semantic matching (rank_tools) -> candidate actions."""
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.tool_matcher import rank_tools


def test_discovery_finds_tools_the_domain_baseline_never_proposed():
    hits = rank_tools("compress my vacation photos into a zip", limit=5, domain_hint="filesystem")
    actions = [h.action_type for h in hits]
    assert "compress_files" in actions and hits[0].action_type == "compress_files"


def test_discovery_matches_each_manifest_domain():
    cases = [
        ("merge these two pdfs", "documents", "pdf_merge"),
        ("run a ping to google dns", "network", "ping"),
        ("analyze this csv of my expenses", "data", "analyze_data"),
    ]
    for text, domain, expected in cases:
        actions = [h.action_type for h in rank_tools(text, limit=5, domain_hint=domain)]
        assert expected in actions, f"{text!r} -> {actions}"


def test_discovery_domain_boost_ranks_domain_tools_first():
    no_hint = [h.action_type for h in rank_tools("analyze this csv of my expenses", limit=5)]
    hinted = [h.action_type for h in rank_tools("analyze this csv of my expenses", limit=5, domain_hint="data")]
    # With the goal's domain hint, the domain's own analysis tool must not
    # rank below an unrelated one.
    assert hinted.index("analyze_data") <= no_hint.index("analyze_data") if "analyze_data" in no_hint else True


def test_discovery_ignores_weak_single_token_noise():
    """'open photoshop' is the domain baseline's job (open_application);
    discovery must not pad the list with weak 1.0-overlap tools."""
    hits = rank_tools("open photoshop", limit=5, domain_hint="desktop_os")
    assert all(h.score >= 1.5 for h in hits)


def test_synthesis_now_includes_manifest_discovery():
    """The candidate pipeline for a filesystem goal discovers the actual
    tool the request needs (compress_files) alongside the baseline."""
    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="filesystem",
        user_text="compress my vacation photos into a zip",
    )
    by_source = {}
    for c in candidates:
        by_source.setdefault(c.get("source", "domain_baseline"), set()).add(c.get("action_type"))
    # Baseline domain prior is still there…
    assert "search_files" in by_source.get("domain_baseline", set())
    # …and discovery reached beyond it.
    assert "compress_files" in by_source.get("manifest_discovery", set())


def test_synthesis_does_not_duplicate_discovered_baselines():
    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="filesystem",
        user_text="search my pc for documents called contract",
    )
    actions = [c.get("action_type") for c in candidates]
    assert len(actions) == len(set(actions)), f"duplicate candidates: {actions}"


def test_discovered_candidates_carry_payloads():
    hits = rank_tools("merge these two pdfs", limit=3, domain_hint="documents")
    for h in hits:
        assert h.payload.get("query"), "discovered candidates must carry a usable payload"
