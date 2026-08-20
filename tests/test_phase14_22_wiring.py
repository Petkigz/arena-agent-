"""
Phase 14 + Phase 22 wiring guards: the recovered branch's modules must be invoked
by the CognitiveRuntime cycle (not just exist as standalone, test-only code), and
the runtime singleton must be thread-safe.
"""

import threading
from unittest.mock import patch

from app.cognition.runtime import CognitiveRuntime


def test_runtime_instantiates_phase14_and_phase22(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    assert hasattr(runtime, "advanced_cognition")
    assert hasattr(runtime, "language_grounding")


def test_integration_invokes_phase14_and_phase22(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    with patch.object(runtime.metacognitive_monitor, "record_process"), \
         patch.object(runtime.causal_inference, "add_causal_relationship"), \
         patch.object(runtime.strategic_planning, "get_strategic_overview", return_value={}), \
         patch.object(runtime.cross_domain_transfer, "get_transfer_summary", return_value={}), \
         patch.object(runtime.creative_generation, "get_creativity_summary", return_value={}), \
         patch.object(runtime.social_cognition, "infer_mental_state"), \
         patch.object(runtime.social_cognition, "record_interaction"), \
         patch.object(runtime.consciousness, "create_experience"), \
         patch.object(runtime.embodied_cognition, "get_embodied_summary", return_value={}), \
         patch.object(runtime.cultural_learning, "record_observed_behavior"), \
         patch.object(runtime.advanced_cognition, "get_phase14_report", return_value={}) as p14_report, \
         patch.object(runtime.advanced_cognition.uncertainty_quantifier, "calibrate_confidence") as p14_cal, \
         patch.object(runtime.language_grounding, "ground_utterance", return_value={"meaning": {}}) as p22_ground:

        runtime._integrate_phase_modules(
            user_text="test task",
            intent_type="research",
            latency_ms=12.3,
            reasoning_action="answer",
            success=True,
            goal_verified=True,
        )

    p14_report.assert_called_once()
    p14_cal.assert_called_once()
    p22_ground.assert_called_once()


def test_get_instance_is_thread_safe(tmp_path):
    """Concurrent get_instance() calls must return the same runtime object."""
    CognitiveRuntime._instance = None
    CognitiveRuntime._instance_lock = threading.Lock()
    db = str(tmp_path / "arena.db")

    results = []

    def _get():
        results.append(CognitiveRuntime.get_instance(db_path=db))

    threads = [threading.Thread(target=_get) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 20
    assert all(r is results[0] for r in results)
