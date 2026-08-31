"""P0 bottleneck #4: WorldModel capability discovery must not stop at an
arbitrary [:5] slice (find_entities orders by last_seen — recency, not
relevance). ALL capabilities now flow through a ranked funnel:
semantic relevance -> availability -> safety -> historical success ->
resource cost -> top candidates."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.cognition.goal_interpreter import SemanticGoalInterpreter


def _cap(name, description="", confidence=1.0, **attrs):
    return SimpleNamespace(name=name, attributes={"description": description, **attrs}, confidence=confidence)


def _world(caps):
    wm = MagicMock()
    wm.find_entities.return_value = caps
    return wm


WM = "world_model_capability"


def test_relevant_capability_beyond_position_five_is_discovered():
    """The old [:5] slice saw only the five most-recently-seen entities; a
    relevant capability at position 8 was invisible. The funnel sees ALL."""
    caps = [_cap(f"phone_command_helper_{i}") for i in range(7)]
    caps.append(_cap("diagnostic", "run a system diagnostic to check crash logs"))
    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="desktop_os",
        user_text="run a diagnostic on my system to check the crash",
        world_model=_world(caps),
    )
    wm_caps = [c for c in candidates if c.get("source") == WM]
    assert "diagnostic" in [c["action_type"] for c in wm_caps]
    # And it RANKS first — relevance beats recency.
    assert wm_caps[0]["action_type"] == "diagnostic"


def test_funnel_ranks_by_semantic_relevance():
    caps = [
        _cap("opsec_audit", "security audit"),           # recent, irrelevant
        _cap("diagnostic", "system diagnostic crash logs"),
    ]
    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="desktop_os", user_text="run a diagnostic to check the crash",
        world_model=_world(caps),
    )
    wm_caps = [c["action_type"] for c in candidates if c.get("source") == WM]
    assert wm_caps.index("diagnostic") < wm_caps.index("opsec_audit")


def test_non_executable_capability_is_never_proposed():
    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="desktop_os", user_text="teleport my files",
        world_model=_world([_cap("quantum_teleportation")]),
    )
    assert "quantum_teleportation" not in [c.get("action_type") for c in candidates]


def test_safety_level_ranks_lower_destructive_tools():
    """Equal relevance, different safety levels: the less destructive tool
    ranks first (candidates are proposals, but ordering matters to the
    planner)."""
    # Manifest entries are deliberately non-descriptive so the manifest
    # discovery step (1.5) does not discover/dedupe them away — relevance
    # here comes from the ENTITY descriptions; safety from the manifest.
    def _entry(name, level):
        return {
            "name": name, "category": "system", "handler": lambda **kw: {"success": True},
            "description": "internal handler", "safety_level": level, "availability": None,
        }
    fake_manifest = {
        "diagnostic_low": _entry("diagnostic_low", 0),
        "diagnostic_high": _entry("diagnostic_high", 3),
    }
    caps = [_cap("diagnostic_high", "system diagnostic crash logs"),
            _cap("diagnostic_low", "system diagnostic crash logs")]
    import app.tools.manifest as manifest_mod
    original = manifest_mod.get_tool_manifest
    manifest_mod.get_tool_manifest = lambda: fake_manifest
    try:
        candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
            domain="desktop_os", user_text="run a diagnostic on the crash logs",
            world_model=_world(caps),
        )
    finally:
        manifest_mod.get_tool_manifest = original
    wm_caps = [c["action_type"] for c in candidates if c.get("source") == WM]
    assert wm_caps.index("diagnostic_low") < wm_caps.index("diagnostic_high")


def test_historical_success_boost_from_memory_lessons():
    """A capability named in a successful past lesson outranks an equally
    relevant capability without history."""
    mem = MagicMock()
    mem.search.return_value = [SimpleNamespace(
        content="Used strategy: diagnostic_logs workflow worked",
        task_id="t_past1")]
    caps = [_cap("diagnostic_metrics", "system diagnostic crash logs"),
            _cap("diagnostic_logs", "system diagnostic crash logs")]
    candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
        domain="desktop_os", user_text="run a diagnostic on the crash logs",
        memory_store=mem, world_model=_world(caps),
    )
    wm_caps = [c["action_type"] for c in candidates if c.get("source") == WM]
    assert wm_caps.index("diagnostic_logs") < wm_caps.index("diagnostic_metrics")


def test_unavailable_integration_spends_no_candidate_slot():
    """A capability whose manifest availability check reports offline cannot
    run now — it must not take a slot from runnable candidates."""
    def _entry(name, available):
        return {
            "name": name, "category": "system", "handler": lambda **kw: {"success": True},
            "description": "internal handler", "safety_level": 0,
            "availability": (lambda: available),
        }
    fake_manifest = {
        "diagnostic_probe": _entry("diagnostic_probe", False),
        "screen_capture": _entry("screen_capture", True),
    }
    caps = [_cap("diagnostic_probe", "system diagnostic crash logs"),
            _cap("screen_capture", "capture the screen")]
    import app.tools.manifest as manifest_mod
    original = manifest_mod.get_tool_manifest
    manifest_mod.get_tool_manifest = lambda: fake_manifest
    try:
        candidates = SemanticGoalInterpreter.synthesize_candidates_from_context(
            domain="desktop_os", user_text="run a diagnostic and capture the screen",
            world_model=_world(caps),
        )
    finally:
        manifest_mod.get_tool_manifest = original
    all_actions = [c.get("action_type") for c in candidates]
    assert "screen_capture" in all_actions
    # Unavailable: proposed by NO source — the slot goes to runnable tools.
    assert "diagnostic_probe" not in all_actions


# ── availability state is PER-CAPABILITY evidence (P1 review) ──────────────
# The state was computed inside the ranking loop but read from the leftover
# loop variable AFTER sorting — every candidate inherited whichever state
# the LAST-examined capability happened to leave behind. A not_checked
# capability labeled 'available' skips the planner's probe-before-commit;
# an available one labeled 'not_checked' flags phantom risk to the owner.
#
# Scenario design: the high-rank capability's MANIFEST description is bland
# (so the earlier manifest_discovery source does not claim it — the
# world-model block only sees capabilities no other source proposed) while
# its ENTITY description is rich, giving it the top world-model rank.

def _entry_with_state(name, manifest_description, available):
    """A manifest entry whose availability checker reports `available`
    (True / None=not_checked / False=offline)."""
    return {
        "name": name, "category": "system", "handler": lambda **kw: {"success": True},
        "description": manifest_description, "safety_level": 0,
        "availability": (lambda: available),
    }


def _synth(caps, fake_manifest, user_text):
    import app.tools.manifest as manifest_mod
    original = manifest_mod.get_tool_manifest
    manifest_mod.get_tool_manifest = lambda: fake_manifest
    try:
        return SemanticGoalInterpreter.synthesize_candidates_from_context(
            domain="desktop_os", user_text=user_text, world_model=_world(caps),
        )
    finally:
        manifest_mod.get_tool_manifest = original


def _wm_payload(candidates, action_type):
    for c in candidates:
        if c.get("source") == WM and c.get("action_type") == action_type:
            return c["payload"]
    raise AssertionError(f"no world-model candidate for {action_type}: "
                         f"{[c.get('action_type') for c in candidates]}")


def _wm_caps(candidates):
    return [c["action_type"] for c in candidates if c.get("source") == WM]


def test_not_checked_state_is_not_overwritten_by_later_available_cap():
    """Dangerous direction: a NOT_CHECKED capability that ranks FIRST must
    not inherit 'available' from an available capability examined after it
    (the leftover loop variable) — that label tells the planner its
    dependency was verified when nobody ever probed it."""
    fake_manifest = {
        "phone_command": _entry_with_state("phone_command", "helper", None),
        "screen_capture": _entry_with_state("screen_capture", "capture the screen", True),
    }
    # find_entities order: the not_checked (high-rank) cap FIRST, the
    # available cap LAST — the leftover variable held 'available'.
    caps = [_cap("phone_command", "send a text message from the phone"),
            _cap("screen_capture", "capture the screen")]
    candidates = _synth(caps, fake_manifest, "send a text message")
    wm_caps = _wm_caps(candidates)
    # The scenario requires the not_checked cap to rank first.
    assert wm_caps.index("phone_command") < wm_caps.index("screen_capture")
    assert _wm_payload(candidates, "phone_command")["availability"] == "not_checked"
    assert _wm_payload(candidates, "screen_capture")["availability"] == "available"


def test_available_state_is_not_overwritten_by_later_not_checked_cap():
    """Over-cautious direction: an AVAILABLE capability must not inherit
    'not_checked' from a not_checked capability examined after it — phantom
    risk shown to the owner, needless probing before every commit."""
    fake_manifest = {
        "phone_command": _entry_with_state("phone_command", "helper", True),
        "screen_capture": _entry_with_state("screen_capture", "capture the screen", None),
    }
    caps = [_cap("phone_command", "send a text message from the phone"),
            _cap("screen_capture", "capture the screen")]
    candidates = _synth(caps, fake_manifest, "send a text message")
    assert _wm_payload(candidates, "phone_command")["availability"] == "available"
    assert _wm_payload(candidates, "screen_capture")["availability"] == "not_checked"
