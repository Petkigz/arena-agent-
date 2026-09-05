"""Owner review item 7 (2026-09-01, P0): capability vocabulary
normalization — unresolved phrases must ASK, never silently become
'unconstrained'.

Live evidence: the LLM emits free-text capability phrases
('file searching capability', 'File system navigation skills',
'Image scanning capability', 'Photo organizing algorithms',
'Report generation capabilities', 'test execution and validation
capability', 'text summarization capability'). The resolver chain
matched NONE of them (no stemming, no noise-word stripping, no
aliases), so they landed in `ignored_phrases` — and when ALL phrases
were ignored, `action_available` defaulted to True: the planner
proceeded WITHOUT the requested capability. That fallback is the bug.

New contract (owner's diagram):
    LLM capability phrase
          ↓
    capability resolver
      ├── exact match    (normalized stem set == a known capability)
      ├── alias match    (curated table of recurring LLM phrases)
      ├── semantic match (strict stem overlap with real tool names)
      └── unresolved     → ask / replan / block — NEVER 'unconstrained'
"""

import pytest

from app.cognition.capability_resolver import CapabilityResolver


# A vocabulary shaped like the runtime's real one (native backing keys,
# known-unimplemented, registry tool names, world-model caps).
VOCAB = {
    # native backing (dotted)
    "filesystem.search": frozenset({"filesystem", "search"}),
    "filesystem.read": frozenset({"filesystem", "read"}),
    "llm.generate": frozenset({"llm", "gener"}),
    "vision.analyze": frozenset({"vision", "analys"}),
    "os.launch_app": frozenset({"os", "launch", "app"}),
    # registry tools
    "search_files": frozenset({"search", "file"}),
    "web_search": frozenset({"web", "search"}),
    "local_execute": frozenset({"local", "execut"}),
    "generate_document": frozenset({"gener", "document"}),
    "summarize_feed": frozenset({"summar", "feed"}),
    "lab_scan": frozenset({"lab", "scan"}),
    "detect_faces": frozenset({"detect", "face"}),
    # world-model style
    "media_processing": frozenset({"media", "process"}),
}


# ── tier 1/2/3: the recurring live phrases RESOLVE ──────────────────────

@pytest.mark.parametrize("phrase,expected_canonical", [
    # (exact tier: stem set equals a real capability's)
    ("file searching capability", "search_files"),
    ("web search capability", "web_search"),
    # (alias tier: curated table for recurring LLM phrasings)
    ("text summarization capability", "llm.generate"),
    ("test execution and validation capability", "local_execute"),
    ("File system navigation skills", "filesystem.read"),
    ("Image scanning capability", "vision.analyze"),
    ("Report generation capabilities", "generate_document"),
])
def test_recurring_llm_phrases_resolve(phrase, expected_canonical):
    res = CapabilityResolver.resolve(phrase, VOCAB)
    assert res.tier != "unresolved", f"{phrase!r} must resolve, got {res.detail}"
    assert res.canonical == expected_canonical, \
        f"{phrase!r} -> {res.canonical} ({res.tier}); want {expected_canonical}"


def test_web_search_capability_resolves_via_extra_vocab():
    vocab = dict(VOCAB)
    vocab["web_search"] = frozenset({"web", "search"})
    res = CapabilityResolver.resolve("web search capability", vocab)
    assert res.tier == "exact"
    assert res.canonical == "web_search"


# ── normalization details ───────────────────────────────────────────────

def test_noise_suffixes_and_stopwords_are_stripped():
    # 'capability/skills/algorithms' are vocabulary noise, not stems —
    # they must neither block nor create a match.
    stems = CapabilityResolver.phrase_stems("Photo organizing algorithms")
    assert stems == frozenset({"photo", "organiz"})


def test_stemmer_unifies_inflections():
    # searching→search, files→file, generation→gener, execution→execut,
    # navigation→navig, summarize→summar — the live misses were exactly
    # these inflection gaps.
    assert CapabilityResolver.phrase_stems("file searching") == \
        frozenset({"file", "search"})
    assert CapabilityResolver.phrase_stems("report generation") == \
        frozenset({"report", "gener"})
    assert CapabilityResolver.phrase_stems("test execution") == \
        frozenset({"test", "execut"})
    assert CapabilityResolver.phrase_stems("file system navigation") == \
        frozenset({"filesystem", "navig"})


# ── the semantic tier is STRICT (no wrong matches) ──────────────────────

def test_semantic_match_requires_strong_overlap():
    # 'image scanning' shares the stem 'scan' with lab_scan — a 1-of-2
    # overlap must NOT resolve to an unrelated tool.
    res = CapabilityResolver.resolve("image scanning capability", VOCAB)
    assert res.canonical != "lab_scan"


def test_weak_overlap_stays_unresolved():
    # Nothing in the vocabulary provides 'photo organizing' — one shared
    # stem with an unrelated tool must not fake it.
    res = CapabilityResolver.resolve("photo organizing algorithms", VOCAB)
    assert res.tier == "unresolved"
    assert res.canonical is None


def test_alias_target_must_exist_in_the_vocabulary():
    # An alias whose canonical capability is not actually registered is
    # UNRESOLVED — never silently satisfied.
    vocab = {k: v for k, v in VOCAB.items() if k != "llm.generate"}
    res = CapabilityResolver.resolve("text summarization capability", vocab)
    assert res.tier == "unresolved"


# ── unresolved: the honest outcome for a composite task phrase ──────────

def test_composite_task_phrase_is_unresolved():
    # 'Photo organizing algorithms' names a composite TASK, not a
    # primitive capability: no registered tool organizes photos. The
    # honest resolution is unresolved → ask/replan, not a fake match and
    # not silent 'unconstrained'.
    res = CapabilityResolver.resolve("Photo organizing algorithms", VOCAB)
    assert res.tier == "unresolved"
    assert "unresolved" in res.detail.lower() or res.detail


def test_fictional_phrase_is_unresolved():
    res = CapabilityResolver.resolve("quantum teleportation capability", VOCAB)
    assert res.tier == "unresolved"


# ── runtime integration ─────────────────────────────────────────────────

def test_recurring_phrases_resolve_to_ready_in_the_runtime(tmp_path):
    """The live misses resolve through the FULL chain — availability
    checked against the real registry, keyed by the LLM's phrase (the
    phrase no longer vanishes from the map)."""
    from app.cognition.runtime import CognitiveRuntime
    rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    cap_map = rt.check_capability_availability(
        ["file searching capability", "text summarization capability"],
        target_domain="filesystem")
    assert cap_map.get("file searching capability") is True
    assert cap_map.get("text summarization capability") is True


def test_unresolved_required_capability_is_not_unconstrained(tmp_path):
    """THE fix: an unresolved REQUIRED capability makes the action
    unavailable (ask/replan/block) — `all(...)` is False, not the old
    empty-map → True 'unconstrained' fallback."""
    from app.cognition.runtime import CognitiveRuntime
    rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    cap_map = rt.check_capability_availability(
        ["photo organizing algorithms"], target_domain="filesystem")
    assert cap_map.get("photo organizing algorithms") is False
    action_available = all(cap_map.values()) if cap_map else True
    assert action_available is False


def test_mixed_resolvable_and_unresolved_still_asks(tmp_path):
    """A resolvable-and-ready capability does not wash out an unresolved
    one: required capabilities are conjunctive."""
    from app.cognition.runtime import CognitiveRuntime
    rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    cap_map = rt.check_capability_availability(
        ["os.launch_app", "photo organizing algorithms"],
        target_domain="desktop_os")
    assert cap_map.get("os.launch_app") is True
    assert cap_map.get("photo organizing algorithms") is False
    assert all(cap_map.values()) is False


def test_unresolved_status_is_visible_in_the_ladder(tmp_path):
    """Measurement honesty: the status ladder names the unresolved
    phrase with its basis — not just a boolean."""
    from app.cognition.runtime import CognitiveRuntime
    rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    status = rt.check_capability_status(
        ["photo organizing algorithms"], target_domain="filesystem")
    entry = status["photo organizing algorithms"]
    assert entry["status"] == "unresolved"
    assert entry["supported"] is False
    assert entry["available"] is False
    assert "unresolved" in entry["evidence"].lower() or \
        "no registered" in entry["evidence"].lower()


# ── end to end: the planner ASKS instead of proceeding ──────────────────

def test_e2e_unresolved_required_capability_defers_with_honest_ask(tmp_path):
    """The exact dangerous shape, end to end: the LLM requires
    'Photo organizing algorithms' for an action intent. The cycle must
    DEFER (ask) naming the unrecognized capability — never ACT as if
    unconstrained, never run anything in the background."""
    from unittest.mock import patch
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.goal_interpreter import SemanticGoalInterpreter
    from app.cognition.cognitive_pipeline import CognitivePipeline

    orig = SemanticGoalInterpreter.interpret_goal.__func__

    def wrapper(*args, **kwargs):
        # interpret_goal is a classmethod; the patch makes this a plain
        # function, so cls is passed explicitly to the original.
        rep = orig(SemanticGoalInterpreter, *args, **kwargs)
        rep.required_capabilities = ["Photo organizing algorithms"]
        rep.primary_intent_type = "action_intent"
        return rep

    def _fake_llm(**kwargs):
        return {"success": True, "id": "chat-real",
                "choices": [{"message": {"content": "placeholder"}}]}

    previous = CognitiveRuntime._instance
    rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    try:
        with patch.object(SemanticGoalInterpreter, "interpret_goal", wrapper), \
             patch("app.llm.llm_client.generate_chat_completion",
                   side_effect=_fake_llm):
            res = CognitivePipeline.process_chat(
                user_text="organize my photo collection into folders by date")
    finally:
        CognitiveRuntime._instance = previous

    assert res.get("reasoning_action") == "defer", \
        f"unresolved required capability must ask, got {res.get('reasoning_action')}"
    reply = str(res.get("assistant_reply", ""))
    assert "Photo organizing algorithms" in reply
    assert "unrecogn" in reply.lower() or "no registered" in reply.lower()
    assert res.get("executed_actions") == []


# ── owner report #4 (D9 live, 2026-09-02): milestone capability phrases ────

def test_d9_milestone_phrases_resolve_to_real_implementations():
    """The D9 photo-organization project's milestone capabilities —
    'file scanning capability', 'date-based categorization', 'duplicate
    detection' — resolved as UNRESOLVED on the owner's machine although
    real implementations exist, gating legitimate work to ask/replan.
    Each now maps to a registered implementation."""
    vocab = CapabilityResolver.build_vocabulary([
        "filesystem.search", "filesystem.read",          # native backing
        "detect_duplicate_files", "group_files_by_date",   # registry tools
        "generate_document", "binary_analyze",
    ])
    cases = {
        "file scanning capability": "filesystem.search",
        "filesystem scanning": "filesystem.search",
        "date-based categorization": "group_files_by_date",
        "duplicate detection": "detect_duplicate_files",
        "duplicate finding": "detect_duplicate_files",
        "file analysis capability": "binary_analyze",
    }
    for phrase, expected in cases.items():
        res = CapabilityResolver.resolve(phrase, vocab)
        assert res.resolved, f"{phrase!r} must resolve (got {res.detail})"
        assert res.canonical == expected, \
            f"{phrase!r} -> {res.canonical!r}, expected {expected!r}"
        assert res.tier == "alias"


def test_alias_targets_missing_from_vocabulary_stay_unresolved():
    """The validation property (owner report #4's 'don't simply mark
    unknown capabilities as available'): an alias whose target is NOT in
    the caller's real vocabulary does not resolve — the curated table
    can never invent a capability the runtime does not have."""
    vocab = CapabilityResolver.build_vocabulary(["generate_document"])
    for phrase in ("file scanning capability", "date-based categorization",
                   "duplicate detection"):
        res = CapabilityResolver.resolve(phrase, vocab)
        assert not res.resolved, \
            f"{phrase!r} must stay unresolved when its target is unregistered"


def test_d9_milestone_phrases_resolve_ready_in_the_runtime(tmp_path):
    """End-to-end through the real capability chain: the exact four
    phrases from the owner's D9 capability table (three unresolved, one
    ready) must all resolve ready, with the alias visible in the
    evidence ladder."""
    from app.cognition.runtime import CognitiveRuntime
    rt = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    phrases = ["file scanning capability", "date-based categorization",
               "duplicate detection", "report generation"]
    cap_map, status_map, unresolved = rt._resolve_capability_status(
        phrases, "filesystem")
    assert unresolved == [], f"unresolved: {unresolved}"
    for p in phrases:
        assert status_map[p]["ready"] is True, (p, status_map[p])
        assert "alias match" in status_map[p]["evidence"], \
            (p, status_map[p]["evidence"])


# ── disjunctive phrases (live 2026-09-05, review P3) ───────────────────

def test_disjunctive_phrase_grounds_via_component():
    """'Image recognition or duplicate detection software/tool' stayed
    unresolved while its component grounds — the LLM lists several
    candidate concepts in one capability line. The phrase must resolve
    to the component's tool, with evidence naming the component."""
    vocab = CapabilityResolver.build_vocabulary(
        ["detect_duplicate_files", "search_files", "detect_faces"])
    res = CapabilityResolver.resolve(
        "Image recognition or duplicate detection software/tool", vocab)
    assert res.resolved
    assert res.tier == "disjunct"
    assert res.canonical == "detect_duplicate_files"
    assert "duplicate detection" in res.detail


def test_conjunctive_phrases_are_not_split():
    """'and' means every part is required — grounding only one part
    would under-constrain the planner, so conjunctions stay whole (and
    here: unresolved, honestly)."""
    vocab = CapabilityResolver.build_vocabulary(
        ["detect_duplicate_files", "search_files"])
    res = CapabilityResolver.resolve(
        "image recognition and duplicate detection", vocab)
    assert not res.resolved


def test_disjunct_with_no_grounding_component_stays_unresolved():
    vocab = CapabilityResolver.build_vocabulary(["search_files"])
    res = CapabilityResolver.resolve(
        "photo scanning or file management", vocab)
    assert not res.resolved


# ── file reading (live 2026-09-05: 'file reading' hung unresolved while ──
# the capability exists natively)

def test_file_reading_phrases_resolve_to_filesystem_read():
    vocab = CapabilityResolver.build_vocabulary(
        ["filesystem.read", "filesystem.search", "read_document"])
    for phrase in ("file reading", "read the file", "read file"):
        res = CapabilityResolver.resolve(phrase, vocab)
        assert res.resolved, phrase
        assert res.tier == "alias"
        assert res.canonical == "filesystem.read"
