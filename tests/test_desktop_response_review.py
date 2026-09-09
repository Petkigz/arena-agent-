"""Tests for the desktop Review-response slice (GUI-free paths).

Covers the same contract the web slice tests cover, on the desktop side:

- desktop.response_review payload logic (validation, retry identity, gating).
- DesktopChatClient parsing of the cognitive_metadata frame and trace-carrying
  history (the frames the web consumes and the desktop used to drop).
- ArenaBackendClient's response-review endpoints (paths, payloads, headers,
  and honest failure on unexpected shapes) via httpx.MockTransport.

The PySide6 widget itself is exercised offscreen and skips automatically where
Qt is not installed — the GUI-free logic above is what CI covers everywhere.
"""

import json
import re

import httpx
import pytest

from desktop.backend_client import ArenaBackendClient, BackendConnectionError
from desktop.chat_client import DesktopChatClient
from desktop.response_review import (
    MAX_EVIDENCE_IDS,
    ResponseReviewError,
    build_task_evaluation_payload,
    build_usefulness_payload,
    new_submission_id,
    parse_evidence_ids,
    reviewable_trace,
)

_SUBMISSION_ID_SHAPE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


# ── retry identity ───────────────────────────────────────────────────────────

def test_new_submission_id_matches_backend_pattern_and_is_unique():
    ids = {new_submission_id() for _ in range(50)}
    assert len(ids) == 50
    for sid in ids:
        assert _SUBMISSION_ID_SHAPE.match(sid)
        assert sid.startswith("desktop-")


# ── usefulness payload ───────────────────────────────────────────────────────

def test_build_usefulness_payload_happy_path():
    payload = build_usefulness_payload("helpful", note=" found the file ",
                                       submission_id=new_submission_id())
    assert payload == {
        "usefulness": "helpful",
        "note": "found the file",
        "submission_id": payload["submission_id"],
    }


def test_build_usefulness_payload_rejects_unknown_level():
    with pytest.raises(ResponseReviewError):
        build_usefulness_payload("amazing", submission_id=new_submission_id())


def test_build_usefulness_payload_rejects_short_submission_id():
    with pytest.raises(ResponseReviewError):
        build_usefulness_payload("helpful", submission_id="abc")


# ── task evaluation payload (measurement only) ──────────────────────────────

def test_build_task_evaluation_payload_defaults():
    payload = build_task_evaluation_payload(
        trace_id="trace_abc123",
        task_key=" budget-report ",
        observed_outcome="success",
        submission_id=new_submission_id(),
    )
    assert payload["task_key"] == "budget-report"
    assert payload["trace_id"] == "trace_abc123"
    assert payload["usefulness"] == "unknown"
    assert payload["split"] == "held_out"
    assert payload["condition"] == "single"
    assert payload["correction_received"] is False
    assert payload["evidence_ids"] == []


def test_build_task_evaluation_payload_rejects_empty_task_key_and_bad_outcome():
    sid = new_submission_id()
    with pytest.raises(ResponseReviewError):
        build_task_evaluation_payload(trace_id="t1", task_key="   ",
                                      observed_outcome="success", submission_id=sid)
    with pytest.raises(ResponseReviewError):
        build_task_evaluation_payload(trace_id="t1", task_key="k",
                                      observed_outcome="maybe", submission_id=sid)


def test_build_task_evaluation_payload_rejects_unlinked_trace():
    with pytest.raises(ResponseReviewError):
        build_task_evaluation_payload(trace_id="  ", task_key="k",
                                      observed_outcome="success",
                                      submission_id=new_submission_id())


def test_parse_evidence_ids_dedupes_and_caps():
    text = "a, b ,a  c," + " ,".join(f"e{i}" for i in range(30))
    ids = parse_evidence_ids(text)
    assert ids[0] == "a" and "b" in ids and "c" in ids
    assert len(ids) == MAX_EVIDENCE_IDS
    assert len(ids) == len(set(ids))


# ── gating: unlinked replies are unreviewable ────────────────────────────────

def test_reviewable_trace_gating():
    assert reviewable_trace("trace_1") is True
    assert reviewable_trace("  trace_1  ") is True
    assert reviewable_trace("") is False
    assert reviewable_trace("   ") is False
    assert reviewable_trace(None) is False
    assert reviewable_trace(123) is False


# ── WS frame parsing: metadata + detailed history ────────────────────────────

def test_cognitive_metadata_frame_reaches_callback():
    c = DesktopChatClient(ws_url="ws://unused", conversation_id="conv-1")
    seen = []
    c.on_cognitive_metadata = lambda cid, mid, tid: seen.append((cid, mid, tid))
    c._handle_text(json.dumps({
        "type": "cognitive_metadata",
        "conversation_id": "conv-1",
        "message_id": "msg_1",
        "trace_id": "trace_1",
    }))
    assert seen == [("conv-1", "msg_1", "trace_1")]


def test_history_detail_carries_trace_ids_and_plain_history_unchanged():
    c = DesktopChatClient(ws_url="ws://unused", conversation_id="conv-1")
    plain, detail = [], []
    c.on_history = lambda cid, h: plain.append((cid, h))
    c.on_history_detail = lambda cid, items: detail.append((cid, items))
    c._handle_text(json.dumps({
        "type": "conversation_history",
        "conversation_id": "conv-1",
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello", "message_id": "msg_2", "trace_id": "trace_2"},
        ],
    }))
    assert plain == [("conv-1", [("user", "hi"), ("assistant", "hello")])]
    items = detail[0][1]
    assert items[0]["trace_id"] == "" and items[0]["message_id"] == ""
    assert items[1]["trace_id"] == "trace_2" and items[1]["message_id"] == "msg_2"


def test_frames_without_metadata_fire_nothing():
    c = DesktopChatClient(ws_url="ws://unused", conversation_id="conv-1")
    seen = []
    c.on_cognitive_metadata = seen.append
    c._handle_text(json.dumps({"type": "message_token", "token": "x", "done": True}))
    assert seen == []


# ── REST client endpoints ────────────────────────────────────────────────────

def _client_with(handler, api_key=""):
    client = ArenaBackendClient(base_url="http://localhost:8000", api_key=api_key)
    # Replace only the transport (as the existing desktop tests do) while
    # preserving the real client's headers — the X-API-Key contract under
    # test is set by the constructor/set_api_key on those headers.
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler), timeout=1.0,
        headers=client._client.headers)
    return client


def test_record_trace_usefulness_posts_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["key"] = request.headers.get("X-API-Key")
        return httpx.Response(200, json={
            "success": True,
            "feedback": {"feedback_id": "fb_1", "trace_id": "trace_1"},
        })

    client = _client_with(handler, api_key="secret")
    result = client.record_trace_usefulness(
        "trace_1", usefulness="helpful", note="n", submission_id="desktop-abcdef1234")
    client.close()

    assert seen["path"] == "/cognition/traces/trace_1/usefulness"
    assert seen["key"] == "secret"
    assert seen["body"] == {
        "usefulness": "helpful", "note": "n", "submission_id": "desktop-abcdef1234"}
    assert result["feedback"]["feedback_id"] == "fb_1"


def test_trace_task_evaluations_builds_filtered_query():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"success": True, "evaluations": [], "report": {}})

    client = _client_with(handler)
    client.trace_task_evaluations("trace 1", split="contract", limit=50)
    client.close()

    assert seen["path"] == "/benchmarks/phase1/tasks/evaluations"
    assert seen["params"]["trace_id"] == "trace 1"
    assert seen["params"]["split"] == "contract"
    assert seen["params"]["limit"] == "50"


def test_record_task_evaluation_posts_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "success": True,
            "evaluation": {"evaluation_id": "ev_1", "trace_id": "trace_1"},
        })

    client = _client_with(handler)
    payload = build_task_evaluation_payload(
        trace_id="trace_1", task_key="k", observed_outcome="failure",
        correction_received=True, submission_id=new_submission_id())
    result = client.record_trace_task_evaluation(payload)
    client.close()

    assert seen["path"] == "/benchmarks/phase1/tasks/evaluations"
    assert seen["body"] == payload
    assert result["evaluation"]["evaluation_id"] == "ev_1"


def test_response_explanation_uses_introspection_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/self-awareness/introspection/trace_9"
        return httpx.Response(200, json={
            "success": True,
            "facts": {"trace_id": "trace_9", "request": "q", "goal_verified": True},
            "explanation": ["gate passed"],
        })

    client = _client_with(handler)
    result = client.response_explanation("trace_9")
    client.close()
    assert result["facts"]["trace_id"] == "trace_9"


def test_http_error_surfaces_as_backend_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "unknown trace"})

    client = _client_with(handler)
    with pytest.raises(BackendConnectionError):
        client.trace_usefulness("missing")
    client.close()


# ── the Qt widget (skips where no Qt runtime exists) ─────────────────────────

def test_response_review_bar_widget_offscreen():
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from desktop.pages.response_review import ResponseReviewBar

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "feedback": [], "evaluations": []})

    client = _client_with(handler)
    bar = ResponseReviewBar(client=client, trace_id="trace_1", message_id="msg_1")
    assert bar._toggle.text() == "Review response"
    # isHidden() is the explicit-hide contract: isVisible() also demands
    # shown ancestors, which the offscreen test harness never provides.
    assert bar._body.isHidden()  # collapsed until the owner opens it
    bar._toggle_expanded()
    assert not bar._body.isHidden()
    # Local validation failure: nothing is sent, an honest message is shown.
    bar._submit_evaluation()
    assert "task key" in bar._eval_status.text().lower()
    client.close()
    app.processEvents()
