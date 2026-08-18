from app.cognition.runtime import CognitiveRuntime


def test_unknown_capability_evaluates_to_false(tmp_path):
    """
    P0 Fix Verification:
    Verify that an unknown or fictional capability (e.g. quantum_teleportation)
    evaluates to False in check_capability_availability and does NOT return True via an 'or True' flaw.
    """
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    req_caps = ["quantum_teleportation", "os.launch_app"]
    cap_map = runtime.check_capability_availability(req_caps, "quantum_domain")

    assert cap_map["quantum_teleportation"] is False
    assert cap_map["os.launch_app"] is True

    action_available = all(cap_map.values())
    assert action_available is False


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
