"""
Phase 2 wiring guards: the previously-orphaned cognition modules (Phases 11-21)
must actually be invoked by the CognitiveRuntime cycle, not merely exist as
standalone, test-only code.

Two layers of proof:
  1. process_cognitive_cycle() calls _integrate_phase_modules().
  2. _integrate_phase_modules() invokes a meaningful method on every module.
"""

from unittest.mock import patch, MagicMock

from app.cognition.runtime import CognitiveRuntime
from app.cognition.reasoning_cycle import ReasoningDecision, ReasoningAction
from app.cognition.reasoning_loop import CycleTrace


def _mock_answer_cycle(runtime):
    """Force the reasoning loop to route through the ANSWER branch."""
    return CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.ANSWER, confidence=0.9, reason="answer")]
    )


def test_cycle_invokes_phase_integration(tmp_path):
    """process_cognitive_cycle must call _integrate_phase_modules."""
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    fake_llm = {
        "choices": [{"message": {"content": "hello"}, "index": 0}],
        "model": "fast",
    }

    with patch.object(runtime.loop, "run", return_value=_mock_answer_cycle(runtime)), \
         patch.object(runtime, "_integrate_phase_modules") as mock_integrate, \
         patch("app.llm.llm_client.generate_chat_completion", return_value=fake_llm):

        res = runtime.process_cognitive_cycle(user_text="hello", complexity="fast")

        assert res["success"] is True
        mock_integrate.assert_called_once()


def test_phase_integration_invokes_all_nine_modules(tmp_path):
    """_integrate_phase_modules must touch all nine Phase 11-21 modules."""
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    patches = {
        "metacognitive": patch.object(runtime.metacognitive_monitor, "record_process"),
        "causal": patch.object(runtime.causal_inference, "add_causal_relationship"),
        "strategic": patch.object(runtime.strategic_planning, "get_strategic_overview", return_value={}),
        "transfer": patch.object(runtime.cross_domain_transfer, "get_transfer_summary", return_value={}),
        "creative": patch.object(runtime.creative_generation, "get_creativity_summary", return_value={}),
        "social_infer": patch.object(runtime.social_cognition, "infer_mental_state"),
        "social_record": patch.object(runtime.social_cognition, "record_interaction"),
        "consciousness": patch.object(runtime.consciousness, "create_experience"),
        "embodied": patch.object(runtime.embodied_cognition, "get_embodied_summary", return_value={}),
        "cultural": patch.object(runtime.cultural_learning, "record_observed_behavior"),
    }

    # Enter all patches and keep references to the underlying mocks.
    mocks = {name: p.start() for name, p in patches.items()}

    try:
        runtime._integrate_phase_modules(
            user_text="test task",
            intent_type="research",
            latency_ms=12.3,
            reasoning_action="answer",
            success=True,
            goal_verified=True,
        )
    finally:
        for p in patches.values():
            p.stop()

    # Every module must have been invoked.
    for name, mock in mocks.items():
        assert mock.call_count == 1, f"module '{name}' was invoked {mock.call_count} times, expected 1"


def test_phase_integration_creative_fallback_on_failure(tmp_path):
    """On goal failure, creative generation produces alternatives for replanning."""
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"))

    class _Idea:
        description = "alternative idea"

    with patch.object(runtime.metacognitive_monitor, "record_process"), \
         patch.object(runtime.causal_inference, "add_causal_relationship"), \
         patch.object(runtime.strategic_planning, "get_strategic_overview", return_value={}), \
         patch.object(runtime.cross_domain_transfer, "get_transfer_summary", return_value={}), \
         patch.object(runtime.creative_generation, "generate_ideas", return_value=[_Idea(), _Idea()]) as gen, \
         patch.object(runtime.social_cognition, "infer_mental_state"), \
         patch.object(runtime.social_cognition, "record_interaction"), \
         patch.object(runtime.consciousness, "create_experience"), \
         patch.object(runtime.embodied_cognition, "get_embodied_summary", return_value={}), \
         patch.object(runtime.cultural_learning, "record_observed_behavior"):

        runtime._integrate_phase_modules(
            user_text="test task",
            intent_type="research",
            latency_ms=12.3,
            reasoning_action="act",
            success=False,
            goal_verified=False,
        )

    gen.assert_called_once()
