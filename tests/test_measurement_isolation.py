"""Regression guards for the P1 measurement-isolation fix.

measure_capabilities() must be observationally pure: it must not leave probe
artifacts in the REAL cognitive stores (beliefs, memory, causal graph,
cross-domain, planning patterns).
"""

from app.cognition.runtime import CognitiveRuntime


def test_measurement_leaves_no_belief_residue(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    before = {b.subject for b in runtime.beliefs.beliefs.list()}
    runtime.measure_capabilities()
    after = {b.subject for b in runtime.beliefs.beliefs.list()}

    # No __scorecard_* / __probe_* belief subjects may have been persisted.
    assert before == after
    assert not any(s.startswith("__scorecard_") or s.startswith("__probe_") for s in after)


def test_measurement_leaves_no_memory_residue(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    before = runtime.memory.search("__scorecard_", limit=1000)
    runtime.measure_capabilities()
    after = runtime.memory.search("__scorecard_", limit=1000)

    assert len(before) == len(after)
    assert len(after) == 0


def test_measurement_still_reports_verified(tmp_path):
    """Isolation must not break the scorecard's behavioral checks."""
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))
    report = runtime.measure_capabilities()
    by_name = {c["capability"]: c for c in report["checks"]}

    assert by_name["belief_evidence_discipline"]["status"] == "verified"
    assert by_name["memory_retrieval"]["status"] == "verified"
    assert by_name["causal_reasoning"]["status"] == "verified"
    assert by_name["cross_domain_transfer_behavioral"]["status"] == "verified"
    assert by_name["planning_patterns_behavioral"]["status"] == "verified"
