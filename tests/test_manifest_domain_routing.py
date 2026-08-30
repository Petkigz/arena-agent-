"""P0 bottleneck #2: the semantic layer must reason in the manifest's own
domain vocabulary, not squash every request into seven legacy domains.

The manifest is the unified capability source (23 categories, 170+ tools);
VALID_DOMAINS now derives from it, keyword routing reaches the new
domains (code/data/documents/finance/network/messaging/learning/security/
vision/self_awareness/...), and required_capabilities name REAL tools so
capability awareness resolves them against the registry."""
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.tools.manifest import get_tool_manifest


def test_valid_domains_include_manifest_categories():
    cats = {str(e.get("category")) for e in get_tool_manifest().values() if e.get("category")}
    valid = SemanticGoalInterpreter._valid_domains()
    assert cats <= valid, f"manifest categories missing from valid domains: {cats - valid}"
    # Legacy aliases stay valid for backward compatibility.
    assert {"desktop_os", "filesystem", "web_research", "mobile_phone",
            "vision_desktop", "diagnostic", "conversation"} <= valid


def test_manifest_domain_keyword_routing():
    cases = [
        ("write a python script to organize my downloads", "code", "run_coding_agent"),
        ("analyze this csv of my expenses", "data", "analyze_data"),
        ("merge these two pdfs", "documents", "pdf"),
        ("whats my budget looking like", "finance", None),
        ("run a traceroute to google", "network", None),
        ("check my loras", "learning", "list_loras"),
        ("send me a telegram message", "messaging", "send_telegram"),
        ("give me my daily briefing", "productivity", "daily_briefing"),
        ("what can you do", "self_awareness", "list_capabilities"),
        ("run an opsec audit on my machine", "security", None),
    ]
    registered = set(get_tool_manifest().keys())
    for text, domain, cap in cases:
        g = SemanticGoalInterpreter.interpret_goal(text)
        assert g.target_domain == domain, f"{text!r} -> {g.target_domain}, expected {domain}"
        if cap:
            assert any(cap in c for c in g.required_capabilities), (text, g.required_capabilities)
            assert any(c in registered for c in g.required_capabilities), (
                f"{text!r}: caps must be real registered tools, got {g.required_capabilities}"
            )


def test_manifest_domain_caps_resolve_to_real_tools():
    """Every representative cap for a manifest domain must be a registered
    tool (or llm.generate) — invented capability phrases are what produced
    spurious deferrals."""
    registered = set(get_tool_manifest().keys())
    for domain, _kw in SemanticGoalInterpreter._MANIFEST_DOMAIN_KEYWORDS:
        caps = SemanticGoalInterpreter._representative_caps(domain)
        assert caps, domain
        for cap in caps:
            assert cap in registered or cap == "llm.generate", (domain, cap)


def test_legacy_routing_is_unchanged():
    """The seven legacy domains keep their routing (regression guard)."""
    assert SemanticGoalInterpreter.interpret_goal("Open Photoshop").target_domain == "desktop_os"
    assert SemanticGoalInterpreter.interpret_goal("Find document contract.pdf").target_domain == "filesystem"
    assert SemanticGoalInterpreter.interpret_goal("Search web for Qwen2.5 benchmarks").target_domain == "web_research"
    assert SemanticGoalInterpreter.interpret_goal("call mom").target_domain == "mobile_phone"
    # File questions about a .pdf FILE must never be hijacked into the
    # pdf-manipulation domain by a bare 'pdf' keyword (word boundaries keep
    # 'report.pdf' from matching; the file search itself is handled by the
    # observation router at ANSWER time).
    g = SemanticGoalInterpreter.interpret_goal("do i have a file called report.pdf")
    assert g.target_domain != "documents"
    assert SemanticGoalInterpreter.interpret_goal("Find document contract.pdf").target_domain == "filesystem"


def test_investigation_keeps_semantics_but_gains_the_domain():
    """'why does my python script crash' stays an information_need but is a
    CODE investigation now, not generic diagnostic/desktop_os."""
    g = SemanticGoalInterpreter.interpret_goal("why does my python script crash")
    assert g.primary_intent_type == "information_need"
    assert g.target_domain == "code"
    assert "run_coding_agent" in g.required_capabilities


def test_new_domain_candidates_propose_real_tools():
    """build_candidates_for_domain gives manifest-category domains their
    primary Level-0 tool (so the ACT path can genuinely execute) plus the
    conversational fallback."""
    candidates = SemanticGoalInterpreter.build_candidates_for_domain("data", "analyze this csv")
    actions = [c["action_type"] for c in candidates]
    assert "formulate_answer" in actions
    real = [a for a in actions if a in set(get_tool_manifest().keys())]
    assert real, f"expected a real manifest tool among candidates, got {actions}"
