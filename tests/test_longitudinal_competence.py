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


def test_empty_and_sample_poor_calibration_never_claims_calibrated():
    calibrator = ConfidenceCalibrator()
    assert calibrator.generate_report().is_calibrated is False
    calibrator.record("search_files", 1.0, True)
    assert calibrator.generate_report("search_files").is_calibrated is False
    assert calibrator.generate_report("search_files").evidence_sufficient is False


def test_unknown_is_not_a_negative_calibration_sample_and_survives_reload(tmp_path):
    path = str(tmp_path / "calibration.db")
    calibrator = ConfidenceCalibrator(path)
    for _ in range(5):
        assert calibrator.record("search_files", 0.8, None) is None
    assert calibrator.total_records() == 0
    assert ConfidenceCalibrator(path).total_records() == 0
    assert calibrator.calibrate("search_files", 0.8) == 0.8


def test_calibration_never_borrows_failures_from_another_action_or_goal_class():
    calibrator = ConfidenceCalibrator()
    for _ in range(5):
        calibrator.record("camera_photo", 0.8, False, goal_type="vision")
        calibrator.record("search_files", 0.8, False, goal_type="find_music")
    assert calibrator.calibrate("web_search", 0.8) == 0.8
    assert calibrator.calibrate("search_files", 0.8, {"goal_type": "find_report"}) == 0.8
    assert calibrator.calibrate("search_files", 0.8, {"goal_type": "find_music"}) < 0.8


def test_well_calibrated_action_is_not_overridden_by_unrelated_global_history():
    calibrator = ConfidenceCalibrator()
    for outcome in [True, True, False, False]:
        calibrator.record("search_files", 0.5, outcome)
    for _ in range(10):
        calibrator.record("camera_photo", 0.5, False)
    assert calibrator.calibrate("search_files", 0.5) == 0.5


def test_sparse_bins_do_not_meet_the_calibration_sample_floor():
    calibrator = ConfidenceCalibrator()
    for confidence in [0.7, 0.8, 0.9]:
        calibrator.record("search_files", confidence, True)
    assert calibrator.generate_report("search_files").evidence_sufficient is False


def test_non_finite_confidence_and_non_boolean_outcomes_are_rejected():
    import pytest
    calibrator = ConfidenceCalibrator()
    for invalid in [float("nan"), float("inf"), -float("inf")]:
        with pytest.raises(ValueError, match="finite"):
            calibrator.record("search_files", invalid, True)
        with pytest.raises(ValueError, match="finite"):
            calibrator.calibrate("search_files", invalid)
    with pytest.raises(ValueError, match="actual_outcome"):
        calibrator.record("search_files", 0.8, "unknown")
