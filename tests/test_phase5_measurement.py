"""
Phase 5 guards: the capability scorecard measures real, wired capabilities (not
percentage-based "AGI" claims) and reports a fully-wired runtime truthfully.
"""

from app.cognition.runtime import CognitiveRuntime


def test_measure_capabilities_returns_evidence_backed_report(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    report = runtime.measure_capabilities()

    assert "checks" in report
    assert "verified_count" in report
    assert "total_count" in report
    assert "not_claimed" in report
    assert report["verified_count"] <= report["total_count"]

    # Every check carries evidence.
    for check in report["checks"]:
        assert check["capability"]
        assert check["status"] in ("verified", "missing")
        assert check["evidence"]


def test_measure_capabilities_reports_full_wiring(tmp_path):
    """With all modules instantiated, module_wiring must be 'verified'."""
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    report = runtime.measure_capabilities()
    by_name = {c["capability"]: c for c in report["checks"]}

    assert by_name["module_wiring"]["status"] == "verified"
    assert by_name["hardware_self_awareness"]["status"] == "verified"
    assert by_name["autonomy_loop"]["status"] == "verified"
    assert by_name["approval_gate"]["status"] == "verified"
    assert by_name["tri_state_verification"]["status"] == "verified"
    assert by_name["verification_honesty"]["status"] == "verified"
    assert by_name["belief_evidence_discipline"]["status"] == "verified"
    assert by_name["memory_retrieval"]["status"] == "verified"
    assert by_name["causal_reasoning"]["status"] == "verified"
    assert by_name["goal_verification_behavioral"]["status"] == "verified"
    assert by_name["cross_domain_transfer_behavioral"]["status"] == "verified"
    assert by_name["skill_classification_behavioral"]["status"] == "verified"
    assert by_name["planning_patterns_behavioral"]["status"] == "verified"
    assert by_name["proactive_maintenance_behavioral"]["status"] == "verified"


def test_measure_capabilities_detects_missing_module(tmp_path):
    """The scorecard must NOT report 'verified' when a module is missing."""
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    runtime.language_grounding = None  # simulate an unwired module

    report = runtime.measure_capabilities()
    by_name = {c["capability"]: c for c in report["checks"]}

    assert by_name["module_wiring"]["status"] == "missing"
