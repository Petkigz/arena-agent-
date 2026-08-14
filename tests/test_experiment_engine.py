import pytest
from app.cognition.experiment_engine import ExperimentEngine

def test_experiment_engine():
    exp = ExperimentEngine.test_hypothesis_in_sandbox(
        hypothesis_name="Test Echo Command",
        command_or_script="echo Hello Experiment"
    )
    assert exp.success is True
    assert "Hello Experiment" in exp.output_summary

def test_self_play_exploration():
    res = ExperimentEngine.run_self_play_sandbox_exploration()
    assert res["success"] is True
    assert res["total_experiments_run"] == 2
