"""Predicted competence is calibrated only against recorded outcomes."""

from app.cognition.confidence_calibrator import ConfidenceCalibrator


def test_longitudinal_report_detects_overconfidence_and_trend(tmp_path):
    calibrator = ConfidenceCalibrator(str(tmp_path / "calibration.db"))
    # Earlier predictions are badly overconfident; recent predictions improve.
    for confidence, outcome in [(0.9, False), (0.9, False), (0.9, True)]:
        calibrator.record("web_search", confidence, outcome)
    for confidence, outcome in [(0.6, True), (0.6, False), (0.6, True)]:
        calibrator.record("web_search", confidence, outcome)

    report = calibrator.longitudinal_report()
    assert report["total_records"] == 6
    assert report["evidence_sufficient"] is True
    assert report["earlier_absolute_error"] > report["recent_absolute_error"]
    assert report["trend"] == "improving"
    assert report["actions"]["web_search"]["samples"] == 6
    assert "not self-reported" in report["note"]


def test_empty_calibration_admits_insufficient_history():
    report = ConfidenceCalibrator().longitudinal_report()
    assert report["total_records"] == 0
    assert report["evidence_sufficient"] is False
    assert report["trend"] == "insufficient_history"
