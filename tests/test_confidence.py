from app.cognition.confidence import ConfidenceCalibrator


def test_source_reliability_updates_from_outcomes():
    calibrator = ConfidenceCalibrator(prior=0.5, prior_strength=2)
    initial = calibrator.reliability("vision")
    calibrator.record("vision", True)
    calibrator.record("vision", True)
    assert calibrator.reliability("vision") > initial
    calibrator.record("vision", False)
    assert 0.0 <= calibrator.reliability("vision") <= 1.0
