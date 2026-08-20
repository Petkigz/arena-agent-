"""
Phase 3 guards: the agent must hold a hardware self-model, be able to report it,
and adapt its model route to live hardware load.
"""

from unittest.mock import patch

from app.utils.hardware_governor import HardwareGovernor
from app.cognition.runtime import CognitiveRuntime


def test_build_self_model_returns_expected_shape():
    model = HardwareGovernor.build_self_model()

    for key in (
        "cpu_model", "cpu_logical_threads", "hybrid_architecture",
        "p_core_threads", "e_core_threads", "ram_total_gb", "gpu_model",
        "gpu_acceleration", "hardware_tier", "operating_mode", "live",
        "recommendation",
    ):
        assert key in model, f"missing key '{key}'"


def test_runtime_has_hardware_self_model(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    report = runtime.get_hardware_self_report()
    assert "hardware_self_model" in report
    assert "summary" in report
    assert "CPU:" in report["summary"]
    assert "RAM:" in report["summary"]


def test_effective_complexity_downgrades_under_memory_pressure(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    # High RAM pressure → downgrade main → fast.
    runtime.hardware_self_model = {
        "live": {"ram_percent": 92.0},
        "recommendation": {"downgrade_to_fast_when_ram_above": 80.0},
    }
    assert runtime._select_effective_complexity("main") == "fast"

    # Low RAM pressure → keep requested route.
    runtime.hardware_self_model = {
        "live": {"ram_percent": 40.0},
        "recommendation": {"downgrade_to_fast_when_ram_above": 80.0},
    }
    assert runtime._select_effective_complexity("main") == "main"

    # 'fast' is never downgraded further.
    runtime.hardware_self_model = {
        "live": {"ram_percent": 99.0},
        "recommendation": {"downgrade_to_fast_when_ram_above": 80.0},
    }
    assert runtime._select_effective_complexity("fast") == "fast"


def test_cycle_exposes_hardware_self_model_on_blackboard(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    from app.cognition.reasoning_cycle import ReasoningDecision, ReasoningAction
    from app.cognition.reasoning_loop import CycleTrace

    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.ANSWER, confidence=0.9, reason="answer")]
    )
    fake_llm = {"choices": [{"message": {"content": "hi"}, "index": 0}], "model": "fast"}

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch.object(runtime, "_integrate_phase_modules"), \
         patch("app.llm.llm_client.generate_chat_completion", return_value=fake_llm):

        runtime.process_cognitive_cycle(user_text="hello", complexity="fast")

    assert runtime.blackboard.get("hardware_self_model") is not None
