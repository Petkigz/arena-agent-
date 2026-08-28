from app.cognition.runtime import CognitiveRuntime


def test_unknown_capability_is_ignored_not_a_veto(tmp_path):
    """
    CONTRACT CHANGE (live-evidence, owner-directed): unresolvable capability
    phrases are IGNORED rather than vetoing. The original P0 guard made any
    unknown phrase block execution; on the owner's machine the LLM emitted
    free-text phrases like 'ability to express emotions verbally' on EVERY
    message, so real registered tools were vetoed 100% of the time by
    hallucinated filler. Unknown phrases now never appear in the map (so they
    cannot flip `all()` to False); resolvable capabilities still evaluate
    strictly True/False against the registry — the 'or True' flaw stays fixed.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    req_caps = ["quantum_teleportation", "os.launch_app"]
    cap_map = runtime.check_capability_availability(req_caps, "quantum_domain")

    # The fictional phrase is not a False veto entry; it is simply absent.
    assert "quantum_teleportation" not in cap_map
    assert cap_map["os.launch_app"] is True

    action_available = all(cap_map.values()) if cap_map else True
    assert action_available is True  # phantom filler cannot block real tools


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
