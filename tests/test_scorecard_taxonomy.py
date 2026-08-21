"""Regression guard: the capability scorecard exposes a real evidence taxonomy,
distinguishing presence from performance — not just a flat list of 'verified'."""

from app.cognition.runtime import CognitiveRuntime

SEVEN_CATEGORIES = {
    "structural", "integration", "behavioral", "robustness",
    "transfer", "generalization", "longitudinal",
}


def test_checks_carry_evidence_category(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "a.db"))
    report = runtime.measure_capabilities()
    for check in report["checks"]:
        assert check["category"] in SEVEN_CATEGORIES | {"unclassified"}


def test_report_includes_category_summary(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "a.db"))
    report = runtime.measure_capabilities()
    assert "categories" in report
    # Every one of the seven taxonomy categories is represented.
    for cat in SEVEN_CATEGORIES:
        assert cat in report["categories"], f"missing category {cat}"
        assert report["categories"][cat]["verified"] <= report["categories"][cat]["total"]


def test_generalization_and_longitudinal_are_present(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "a.db"))
    by_name = {c["capability"]: c for c in runtime.measure_capabilities()["checks"]}
    assert by_name["capability_generalization"]["category"] == "generalization"
    assert by_name["learning_changes_behavior"]["category"] == "longitudinal"
    assert by_name["persistence_roundtrip"]["category"] == "robustness"
