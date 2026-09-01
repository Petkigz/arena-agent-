from app.cognition.runtime import CognitiveRuntime


def test_unknown_required_capability_asks_not_proceeds(tmp_path):
    """
    CONTRACT CHANGE (owner review item 7, 2026-09-01, P0): unresolved
    REQUIRED capability phrases must NOT silently become 'unconstrained'.

    History (both directions are real live incidents):
      * The ORIGINAL P0 guard made any unknown phrase block execution; the
        LLM's hallucinated filler ('ability to express emotions verbally')
        vetoed real tools 100% of the time. That was fixed by IGNORING
        unknown phrases — which overshot: when every phrase was ignored,
        `action_available` defaulted to True and the planner proceeded
        WITHOUT the requested capability (the exact fallback the owner
        flagged as dangerous).
      * NOW the capability resolver (exact/alias/semantic) resolves the
        recurring real phrases ('file searching capability' → search_files),
        and what remains is honestly UNRESOLVED: recorded False in the map
        (keyed by the LLM's phrase, status visible in the ladder) so the
        cycle asks/replans instead of acting unconstrained. Phantom filler
        still cannot flip a READY capability to False — it fails on its
        own line.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    req_caps = ["quantum_teleportation", "os.launch_app"]
    cap_map = runtime.check_capability_availability(req_caps, "quantum_domain")

    # The fictional phrase is honestly unresolved — present and False,
    # not silently absent, and not flipping the real capability's line.
    assert cap_map.get("quantum_teleportation") is False
    assert cap_map.get("os.launch_app") is True

    # Unresolved REQUIRED capabilities gate: ask/replan, never
    # 'unconstrained' (the old empty-map → True fallback is dead).
    action_available = all(cap_map.values()) if cap_map else True
    assert action_available is False

    status = runtime.check_capability_status(
        ["quantum_teleportation"], "quantum_domain")
    assert status["quantum_teleportation"]["status"] == "unresolved"


def test_known_capabilities_evaluate_to_true(tmp_path):
    """
    Verify known native capabilities (e.g. os.launch_app, filesystem.search) evaluate to True.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    req_caps = ["os.launch_app", "filesystem.search"]
    cap_map = runtime.check_capability_availability(req_caps, "desktop_os")

    assert cap_map["os.launch_app"] is True
    assert cap_map["filesystem.search"] is True

    action_available = all(cap_map.values())
    assert action_available is True
