"""In-chat correction detection and recording (conservative, existing-path reuse)."""

from types import SimpleNamespace

from backend.chat_corrections import (
    detect_chat_correction,
    record_chat_correction,
    resolve_target_trace,
)


# ── Detection: explicit hits ─────────────────────────────────────────────

def test_detects_owner_correction_with_retrieval_type():
    detected = detect_chat_correction(
        "No, you searched the wrong folder, search the whole pc"
    )
    assert detected is not None
    assert detected["correction_type"] == "retrieval"


def test_detects_intent_correction():
    detected = detect_chat_correction("I meant the Q3 report, not the Q2 one")
    assert detected is not None
    assert detected["correction_type"] == "intent"


def test_detects_factual_disagreement_opener():
    detected = detect_chat_correction("That's wrong, Berlin is not the capital")
    assert detected is not None
    assert detected["correction_type"] == "factual"


def test_detects_strong_phrase_without_opener():
    detected = detect_chat_correction("you looked in the wrong place entirely")
    assert detected is not None
    assert detected["correction_type"] == "retrieval"


# ── Detection: conservative misses ───────────────────────────────────────

def test_ordinary_message_is_not_a_correction():
    assert detect_chat_correction("what's the weather like today?") is None
    assert detect_chat_correction("no way, that's awesome!") is None
    assert detect_chat_correction("can you search the file again slowly") is None


def test_empty_message_is_not_a_correction():
    assert detect_chat_correction("") is None
    assert detect_chat_correction("   ") is None


def test_unclassifiable_opener_is_unspecified_not_guessed():
    detected = detect_chat_correction("try again")
    assert detected is not None
    assert detected["correction_type"] == "unspecified"


# ── Prior-trace resolution ───────────────────────────────────────────────

def test_resolves_most_recent_trace_linked_assistant_reply():
    messages = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1", "trace_id": "trace_old"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2", "trace_id": "trace_new"},
        {"role": "user", "content": "No, you searched the wrong folder"},
    ]
    target = resolve_target_trace("conv", fetch=lambda cid, limit: messages)
    assert target == {
        "trace_id": "trace_new",
        "reply_excerpt": "a2",
    }


def test_legacy_traceless_rows_are_not_targets():
    messages = [
        {"role": "assistant", "content": "legacy reply"},  # no trace link
        {"role": "user", "content": "No, that's wrong"},
    ]
    assert resolve_target_trace("conv", fetch=lambda cid, limit: messages) is None


def test_store_failure_is_an_honest_noop():
    def broken(cid, limit):
        raise RuntimeError("db closed")
    assert resolve_target_trace("conv", fetch=broken) is None


# ── Recording through the EXISTING owner-correction path ────────────────


def _stub_runtime(candidates):
    """Stub the two EXISTING stores the record path must reuse."""

    class StubTraining:
        def __init__(self):
            self.created = []

        def list(self):
            return list(candidates)

        def propose_owner_correction(self, **kwargs):
            candidate = SimpleNamespace(
                candidate_id=f"train_{len(self.created) + 1:03d}",
                source_trace_id=kwargs.get("source_trace_id", ""),
                action_type=kwargs.get("action_type", ""),
                response=kwargs.get("response", ""),
                strategy_update={"generalized": False},
                evidence=["owner_correction"],
            )
            self.created.append(kwargs)
            return candidate

    class StubMeasurements:
        def __init__(self):
            self.recorded = []

        def record(self, **kwargs):
            self.recorded.append(kwargs)
            return SimpleNamespace(correction_id=f"corr_{len(self.recorded):03d}")

    return SimpleNamespace(
        training_examples=StubTraining(),
        correction_measurements=StubMeasurements(),
        outcomes=SimpleNamespace(),
    )


def _messages_with_trace():
    return [
        {"role": "user", "content": "do i have a song called kaba"},
        {"role": "assistant", "content": "no matches found", "trace_id": "trace_kaba"},
        {"role": "user", "content": "No, you searched the wrong folder, search the whole pc"},
    ]


def test_records_correction_via_existing_stores():
    runtime = _stub_runtime([])
    note = record_chat_correction(
        runtime, "conv-1", "No, you searched the wrong folder, search the whole pc",
        fetch=lambda cid, limit: _messages_with_trace(),
    )
    assert note is not None
    assert note["correction_type"] == "retrieval"
    assert note["target_trace_id"] == "trace_kaba"
    assert note["duplicate"] is False
    # EXISTING store reuse: candidate proposed pending review, measurement once.
    assert len(runtime.training_examples.created) == 1
    kwargs = runtime.training_examples.created[0]
    assert kwargs["source_trace_id"] == "trace_kaba"
    assert kwargs["action_type"] == "owner_correction"
    assert "edit this candidate before approval" in kwargs["note"]
    assert len(runtime.correction_measurements.recorded) == 1


def test_duplicate_retry_records_only_one_measurement():
    runtime = _stub_runtime([])
    first = record_chat_correction(
        runtime, "conv-1", "No, you searched the wrong folder, search the whole pc",
        fetch=lambda cid, limit: _messages_with_trace(),
    )
    assert first is not None and first["duplicate"] is False
    # A retry of the SAME correction message resolves to the same trace and
    # the same redacted instruction: no second candidate, no second sample.
    from app.cognition.training_examples import redact_training_text
    clean, _ = redact_training_text(
        "No, you searched the wrong folder, search the whole pc"
    )
    runtime.training_examples.list = (  # simulate the store returning the created candidate
        lambda: [SimpleNamespace(
            candidate_id="train_001",
            source_trace_id="trace_kaba",
            action_type="owner_correction",
            response=clean,
            strategy_update={"generalized": False},
            evidence=[],
        )]
    )
    second = record_chat_correction(
        runtime, "conv-1", "No, you searched the wrong folder, search the whole pc",
        fetch=lambda cid, limit: _messages_with_trace(),
    )
    assert second is not None and second["duplicate"] is True
    assert len(runtime.correction_measurements.recorded) == 1


def test_non_correction_message_never_touches_the_stores():
    runtime = _stub_runtime([])
    note = record_chat_correction(runtime, "conv-1", "thanks, that worked")
    assert note is None
    assert runtime.training_examples.created == []
    assert runtime.correction_measurements.recorded == []


def test_correction_without_linkable_trace_is_an_honest_noop():
    runtime = _stub_runtime([])
    note = record_chat_correction(
        runtime, "conv-2", "No, that's wrong",
    )
    assert note is None
    assert runtime.training_examples.created == []
    assert runtime.correction_measurements.recorded == []


def test_missing_stores_skip_without_raising():
    runtime = SimpleNamespace()  # no training_examples / correction_measurements
    note = record_chat_correction(
        runtime, "conv-1", "No, you searched the wrong folder",
    )
    assert note is None


# ── Router hook: the chat turn still runs; the event reaches the room ───

import asyncio


def test_router_records_in_chat_correction_and_message_still_flows(tmp_path, monkeypatch):
    """An explicit in-chat correction is recorded through the REAL runtime
    stores against the prior reply's REAL persisted trace, a
    correction_recorded event is sent to the room, and the turn itself still
    completes normally."""
    import backend.message_router as mr
    from unittest.mock import patch
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.reasoning_cycle import ReasoningDecision, ReasoningAction
    from app.cognition.reasoning_loop import CycleTrace
    from app.config import settings
    from app.database import DatabaseManager
    from backend.websocket_server import ws_manager

    db_path = str(tmp_path / "arena.db")
    # The runtime's explicit db_path feeds the training store's trace lookup,
    # while traces persist to settings.DB_PATH — point BOTH at the same temp
    # file (production does exactly this: path = settings.DB_PATH).
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "traces.db"))
    runtime = CognitiveRuntime(db_path=str(tmp_path / "traces.db"))
    monkeypatch.setattr(mr, "db", DatabaseManager(db_path=str(tmp_path / "assistant.db")))
    mr._conversation_histories.clear()

    sent = []

    async def record_send(conversation_id, payload):
        sent.append(payload)

    monkeypatch.setattr(ws_manager, "send_to_conversation", record_send)

    router = mr.MessageRouter(runtime=runtime)
    mock_trace = CycleTrace(
        decisions=[ReasoningDecision(action=ReasoningAction.ANSWER, confidence=0.9, reason="answer")]
    )
    fake_llm = {"choices": [{"message": {"content": "searching the whole pc now"}, "index": 0}], "model": "fast"}

    with patch.object(runtime.loop, "run", return_value=mock_trace), \
         patch.object(runtime, "_integrate_phase_modules"), \
         patch("app.llm.llm_client.generate_chat_completion", return_value=fake_llm):
        # Turn 1: an ordinary task — a real trace is persisted and bound to
        # the assistant reply.
        asyncio.run(router._handle_user_message(None, {
            "conversation_id": "conv_corr",
            "content": "do i have a song called kaba on my pc",
        }))
        history = mr.db.get_conversation_messages("conv_corr")
        bound = [m for m in history if m.get("trace_id")]
        assert bound, "the first reply must carry a persisted trace link"
        target_trace = bound[-1]["trace_id"]

        # Turn 2: the owner corrects it in chat.
        reply = asyncio.run(router._handle_user_message(None, {
            "conversation_id": "conv_corr",
            "content": "No, you searched the wrong folder, search the whole pc",
        }))

    # The corrective turn still ran as an ordinary message (the runtime may
    # append its epistemic presentation to the reply text).
    assert "searching the whole pc now" in reply

    # The correction event reached the conversation room.
    correction_events = [p for p in sent if p.get("type") == "correction_recorded"]
    assert len(correction_events) == 1
    event = correction_events[0]
    assert event["target_trace_id"] == target_trace
    assert event["correction_type"] == "retrieval"
    assert event["duplicate"] is False

    # The REAL existing stores hold the evidence: one pending owner-correction
    # candidate linked to the exact trace, one correction measurement. (The
    # runtime also proposes its own verified-outcome LoRA candidate from the
    # first turn — that one is skill=formulate_answer, not a correction.)
    candidates = [
        c for c in runtime.training_examples.list()
        if c.source_type == "owner_correction"
    ]
    assert len(candidates) == 1
    assert candidates[0].source_trace_id == target_trace
    assert candidates[0].status.value == "pending"
    summary = runtime.correction_measurements.summary()
    assert summary.total_corrections == 1
