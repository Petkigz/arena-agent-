"""The CognitivePipeline bridge must propagate the runtime's verdict —
never manufacture success.

Live P0 from the owner's bottleneck review: process_request returned
success=True even when process_cognitive_cycle ended blocked/unverified,
which made normal testing read as gaslighting ('API says success, nothing
actually happened'). The bridge now propagates success, request_success,
execution_success, goal_verified, verification_unknown,
goal_lifecycle_state and reason, and converts runtime crashes into honest
structured failures instead of 500s."""
from unittest.mock import patch

import pytest

from app.cognition import cognitive_pipeline as cp_mod
from app.cognition.cognitive_pipeline import CognitivePipeline


class _FakeRuntime:
    def __init__(self, result=None, raise_exc=None):
        self._result = result
        self._raise = raise_exc

    def process_cognitive_cycle(self, user_text, complexity="fast", session_id=None, **kw):
        if self._raise:
            raise self._raise
        return self._result


def _patch_runtime(fake):
    return patch.object(cp_mod.CognitiveRuntime, "get_instance", staticmethod(lambda: fake))


def test_failure_propagates_honestly():
    fake = _FakeRuntime({
        "request_success": True,
        "success": False,
        "execution_success": False,
        "goal_verified": False,
        "verification_unknown": True,
        "goal_lifecycle_state": "blocked",
        "reason": "gate blocked",
        "session_id": "sess_1",
        "trace_id": "trace_1",
        "assistant_reply": "I could not do that.",
        "executed_actions": [],
        "latency_ms": 5.0,
        "model_used": "fast",
    })
    with _patch_runtime(fake):
        res = CognitivePipeline.process_request("open notepad")
    assert res["success"] is False
    assert res["request_success"] is True
    assert res["execution_success"] is False
    assert res["goal_verified"] is False
    assert res["verification_unknown"] is True
    assert res["goal_lifecycle_state"] == "blocked"
    assert res["reason"] == "gate blocked"
    assert res["assistant_reply"] == "I could not do that."
    assert res["session_id"] == "sess_1"


def test_success_propagates_honestly():
    fake = _FakeRuntime({
        "request_success": True,
        "success": True,
        "execution_success": True,
        "goal_verified": True,
        "goal_lifecycle_state": "achieved",
        "session_id": "sess_2",
        "trace_id": "trace_2",
        "assistant_reply": "Opened it.",
        "executed_actions": ["launch_app"],
        "latency_ms": 12.0,
        "model_used": "fast",
    })
    with _patch_runtime(fake):
        res = CognitivePipeline.process_request("open firefox")
    assert res["success"] is True
    assert res["goal_verified"] is True
    assert res["goal_lifecycle_state"] == "achieved"
    assert res["executed_actions"] == ["launch_app"]
    assert res["reason"] is None


def test_runtime_exception_is_an_honest_failure_not_a_500():
    fake = _FakeRuntime(raise_exc=RuntimeError("boom in the reasoning loop"))
    with _patch_runtime(fake):
        res = CognitivePipeline.process_request("anything")
    assert res["success"] is False
    assert res["request_success"] is False
    assert "boom in the reasoning loop" in res["reason"]
    assert res["assistant_reply"]
    assert res["goal_lifecycle_state"] == "failed"


def test_reason_is_synthesized_when_runtime_omits_it():
    fake = _FakeRuntime({
        "success": False,
        "goal_verified": False,
        "goal_lifecycle_state": "waiting_for_evidence",
    })
    with _patch_runtime(fake):
        res = CognitivePipeline.process_request("find my files")
    assert res["success"] is False
    assert res["reason"] == "goal not verified (lifecycle state: waiting_for_evidence)"


def test_non_dict_runtime_result_is_an_honest_failure():
    fake = _FakeRuntime(result=None)
    with _patch_runtime(fake):
        res = CognitivePipeline.process_request("anything")
    assert res["success"] is False
    assert "NoneType" in res["reason"]
