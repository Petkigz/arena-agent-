import pytest
from app.cognition.trace import CognitiveTrace
from app.cognition.pipeline import CognitivePipeline

def test_cognitive_trace():
    trace = CognitiveTrace(user_input="How's the weather?")
    assert trace.user_input == "How's the weather?"
    assert trace.session_id is not None
    assert trace.is_finalized is False

    trace.finalize(reply="Sunny", actions=[], latency=12.5)
    assert trace.is_finalized is True
    assert trace.latency_ms == 12.5

def test_cognitive_pipeline_process_chat():
    res = CognitivePipeline.process_chat("Can you open Firefox and search Ordinary?")
    assert "trace_id" in res
    assert "session_id" in res
    assert "assistant_reply" in res
    assert "model_used" in res
