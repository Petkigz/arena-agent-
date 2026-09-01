"""Owner review P1 #9 (2026-09-01): the model-fallback disclosure
reaches the API boundary, not just the logs.

Item 1 (9640b53) built the routing ladder — requested model -> closest
LOADED fallback (LOUD) -> simulation — with the loudness living in a
WARNING log, a `model_fallback` tag on the raw LLM response dict, and
an inspection event list. But the runtime discarded everything from
that dict except `choices` and `model`: when the owner's main model
isn't loaded and a stand-in answers, the RESPONSE PAYLOAD said nothing.
"Observable, never silent" has to hold at the boundary the consumer
actually sees — otherwise the owner needs log spelunking to learn why
answers feel different ("why is this dumber?" was the original
incident).

The contract pinned here: when a loaded fallback model answered, the
pipeline response carries `model_fallback: {requested, used, reason}`
naming BOTH models; when the requested model answered, the key is
absent (nothing to disclose). The simulation case already discloses via
`llm_available: False` + the DEFERRED lifecycle — simulation is not a
fallback, it's the honest last resort.
"""

from unittest.mock import patch


FALLBACK_INFO = {
    "requested": "qwen2.5-9b-instruct",
    "used": "qwen3.5-9b",
    "reason": "requested model is not loaded; using the closest loaded model",
}


def _fake_llm(with_fallback, reply="All good."):
    def _llm(**kwargs):
        res = {
            "success": True,
            "id": "chat-real",
            "model": (FALLBACK_INFO["used"] if with_fallback else "fast-model"),
            "choices": [{"message": {"content": reply}}],
        }
        if with_fallback:
            res["model_fallback"] = dict(FALLBACK_INFO)
        return res
    return _llm


def test_answer_response_surfaces_model_fallback():
    """A loaded fallback model answered — the response payload says so,
    naming BOTH the requested and the stand-in model."""
    from app.cognition.cognitive_pipeline import CognitivePipeline

    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_fake_llm(with_fallback=True)):
        res = CognitivePipeline.process_chat(
            user_text="hello, how are you today?")

    surfaced = res.get("model_fallback")
    assert isinstance(surfaced, dict)
    assert surfaced["requested"] == FALLBACK_INFO["requested"]
    assert surfaced["used"] == FALLBACK_INFO["used"]
    assert surfaced.get("reason")
    # The stand-in is also what model_used reports — one story, no drift
    # between the two disclosure fields.
    assert res.get("model_used") == FALLBACK_INFO["used"]


def test_answer_response_has_no_fallback_key_when_requested_model_answered():
    """The requested model answered — nothing to disclose, no key."""
    from app.cognition.cognitive_pipeline import CognitivePipeline

    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_fake_llm(with_fallback=False)):
        res = CognitivePipeline.process_chat(
            user_text="hello, how are you today?")

    assert "model_fallback" not in res
    assert res.get("model_used") == "fast-model"


def test_rest_chat_response_surfaces_model_fallback():
    """The final boundary: /chat's JSON names both models when a loaded
    fallback answered — a client (or the owner reading the network tab)
    learns WHY the answer came from a stand-in without log access."""
    from fastapi.testclient import TestClient
    from app.main import app

    api = TestClient(app)
    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_fake_llm(with_fallback=True)):
        resp = api.post("/chat", json={
            "messages": [{"role": "user", "content": "hello there"}],
            "complexity": "fast",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["model_fallback"]["requested"] == FALLBACK_INFO["requested"]
    assert data["model_fallback"]["used"] == FALLBACK_INFO["used"]
    # The stand-in is also what `model` reports — one story.
    assert data["model"] == FALLBACK_INFO["used"]


def test_rest_chat_response_has_no_fallback_key_when_requested_model_answered():
    from fastapi.testclient import TestClient
    from app.main import app

    api = TestClient(app)
    with patch("app.llm.llm_client.generate_chat_completion",
               side_effect=_fake_llm(with_fallback=False)):
        resp = api.post("/chat", json={
            "messages": [{"role": "user", "content": "hello there"}],
            "complexity": "fast",
        })

    assert resp.status_code == 200
    assert "model_fallback" not in resp.json()
