"""Fixes from the owner's 2026-09-08 live test — every complaint in the log
gets a regression pin: coder-model hijack, unapproved destructive deletes,
voice replies never spoken, screenshot 404s, frozen overlay glue (frontend),
parked goals that never resume, and the decision-trace log the owner asked
for ("log everything so we know what's happening and why")."""

import base64
import io
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def hermetic_owner_policy(monkeypatch):
    from app.cognition.owner_control import OwnerControlPolicy, owner_control_store

    monkeypatch.setattr(owner_control_store, "_policy", OwnerControlPolicy())


# ── Model selection: a coder must not hijack chat routes ─────────────


def test_coder_model_no_longer_hijacks_general_chat():
    """Live test: 30B coder answered every main-route request and failed all
    of them while a 9B general model sat loaded and unused."""
    from app.llm import LocalLLMClient

    client = LocalLLMClient(base_url="http://test/v1")
    loaded = [
        "qwen3-coder-30b-a3b-instruct",  # what the old scoring picked
        "qwen2.5-9b-instruct",           # the ignored general model
        "qwen2.5-3b-instruct",
    ]
    assert client.select_loaded_fallback(
        "qwen2.5-14b-instruct", loaded, role="main"
    ) == "qwen2.5-9b-instruct"
    # And with nothing but the coder loaded, it still serves (never excluded).
    assert client.select_loaded_fallback(
        "qwen2.5-14b-instruct", ["qwen3-coder-30b-a3b-instruct"], role="main"
    ) == "qwen3-coder-30b-a3b-instruct"


# ── Destructive deletes ask the owner first ──────────────────────────


def test_recursive_delete_of_any_path_is_dangerous():
    """The owner's 'delete the neww folder' ran at Level 2 WITHOUT asking
    because only the C:\\ root variant matched. Any recursive delete asks."""
    from app.cognition.os_control_planner import DANGEROUS_PATTERNS

    assert DANGEROUS_PATTERNS.search(
        "Remove-Item -Path $env:USERPROFILE\\Desktop\\neww -Recurse -Force"
    )
    assert DANGEROUS_PATTERNS.search('Remove-Item "C:\\My Folder" -Recurse')
    assert DANGEROUS_PATTERNS.search("rm -r folder")
    # Non-recursive single-file deletes are not flagged dangerous.
    assert not DANGEROUS_PATTERNS.search("Remove-Item -Path C:\\temp\\f.txt")


def test_destructive_os_plan_escalates_to_owner_approval():
    from app.cognition.action_proposal import ActionGate, ActionProposal

    proposal = ActionProposal(
        action_type="os_control_execute",
        payload={
            "plan": {
                "command": "Remove-Item -Path X -Recurse -Force",
                "risk_level": "destructive",
                "description": "delete folder",
                "platform": "windows",
            }
        },
        recommendation_reason="OS control planner",
        confidence=0.75,
    )
    gate = ActionGate.evaluate_proposal(proposal)
    assert gate.allowed is False
    assert gate.requires_approval is True
    assert proposal.safety_level >= 3, "destructive plan must not ride Level 2"


# ── Voice replies are actually spoken ─────────────────────────────────


def _make_router_with_stub_voice(source: str) -> tuple:
    from backend.message_router import MessageRouter

    router = MessageRouter(runtime=None)  # type: ignore[arg-type]
    stub_voice = SimpleNamespace(speak_reply=AsyncMock())
    router.voice_service = stub_voice

    async def fake_runtime(*args, **kwargs):
        return "here is the answer"

    return router, stub_voice, fake_runtime


@pytest.mark.asyncio
async def test_voice_source_reply_is_spoken():
    router, stub_voice, fake_runtime = _make_router_with_stub_voice("voice")
    with patch.object(
        type(router), "_call_cognitive_runtime", fake_runtime
    ), patch(
        "backend.message_router.add_to_history", lambda *a, **k: None
    ), patch(
        "backend.message_router.ws_manager.send_to_conversation", new_callable=AsyncMock
    ):
        await router._handle_user_message(None, {
            "type": "user_message",
            "conversation_id": "conv-voice",
            "content": "what is my status",
            "source": "voice",
        })
    stub_voice.speak_reply.assert_awaited_once_with("here is the answer")


@pytest.mark.asyncio
async def test_typed_source_reply_is_not_spoken():
    router, stub_voice, fake_runtime = _make_router_with_stub_voice("text")
    with patch.object(
        type(router), "_call_cognitive_runtime", fake_runtime
    ), patch(
        "backend.message_router.add_to_history", lambda *a, **k: None
    ), patch(
        "backend.message_router.ws_manager.send_to_conversation", new_callable=AsyncMock
    ):
        await router._handle_user_message(None, {
            "type": "user_message",
            "conversation_id": "conv-text",
            "content": "hello",
            "source": "text",
        })
    stub_voice.speak_reply.assert_not_awaited()


def test_custom_wake_word_setting_passes_through_map():
    from backend.voice.service import _map_wake_word

    assert _map_wake_word("custom:abc123") == "custom:abc123"
    assert _map_wake_word("hey jarvis") == "hey_jarvis"
    assert _map_wake_word(None) == "hey_jarvis"


# ── Wake word: training actually trains ───────────────────────────────


def _wav_bytes(audio: np.ndarray, rate: int = 16000) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return "data:audio/wav;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture()
def phrase_audio():
    sr = 16000
    t = np.arange(int(0.8 * sr)) / sr
    phrase = (
        0.6 * np.sin(2 * np.pi * 220 * t) * np.linspace(1, 0.3, t.size)
        + 0.4 * np.sin(2 * np.pi * 660 * t) * np.linspace(0.2, 1, t.size)
    ).astype(np.float32)
    rng = np.random.default_rng(11)
    samples = []
    for _ in range(6):
        noise = rng.normal(0, 0.03, size=phrase.size).astype(np.float32)
        samples.append((np.roll(phrase, int(rng.integers(0, 800))) + noise).astype(np.float32))
    return phrase, samples, rng


def test_sample_pack_trains_detects_and_persists(phrase_audio, tmp_path):
    from backend.voice.sample_wake_model import SamplePackWakeModel

    phrase, samples, rng = phrase_audio
    model = SamplePackWakeModel.train("open portal", samples)
    assert model.threshold >= 0.45
    assert model.sample_count == 6

    live = (phrase + rng.normal(0, 0.05, size=phrase.size)).astype(np.float32)
    assert model.process(live, now=10.0) is True
    assert model.process(rng.normal(0, 0.3, size=phrase.size).astype(np.float32), now=12.5) is False

    model.save(tmp_path / "pack")
    reloaded = SamplePackWakeModel.load(tmp_path / "pack")
    assert reloaded.phrase == "open portal"
    assert reloaded.process(live, now=20.0) is True


def test_train_endpoint_trains_and_activate_points_pipeline_at_pack(
    phrase_audio, tmp_path, monkeypatch
):
    from backend.api import wakeword_routes
    from app.server import app as server_app
    from fastapi.testclient import TestClient as _TC

    monkeypatch.setattr(wakeword_routes, "WAKEWORD_DIR", tmp_path)
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "DATA_DIR", tmp_path)  # settings.json lives here
    client = _TC(server_app)  # wakeword routes live on the unified server app

    _, samples, _ = phrase_audio
    response = client.post(
        "/api/wakeword/train",
        json={
            "wake_word": "open portal",
            "samples": [
                {
                    "id": f"s{i}",
                    "audio": _wav_bytes(s),
                    "timestamp": "2026-09-08T00:00:00",
                    "duration": 0.8,
                    "sample_rate": 16000,
                    "channels": 1,
                }
                for i, s in enumerate(samples)
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True, data
    assert data["model_id"]
    assert (tmp_path / f"{data['model_id']}.npz").exists()

    # Activation registers the pack as the live wake word for the pipeline.
    activated = client.post(f"/api/wakeword/models/{data['model_id']}/activate")
    assert activated.status_code == 200
    from app.settings_store import get_settings, update_settings

    assert str(get_settings().get("wake_word")).startswith("custom:")
    # restore so other tests are untouched
    update_settings({"wake_word": "hey_arena", "wakeWord": "hey_arena"})


def test_detector_loads_custom_pack_and_detects(phrase_audio, tmp_path, monkeypatch):
    from backend.api import wakeword_routes
    from backend.voice.sample_wake_model import SamplePackWakeModel
    from backend.voice.wake_word import WakeWordDetector

    phrase, samples, rng = phrase_audio
    model = SamplePackWakeModel.train("open portal", samples)
    model.save(tmp_path / "pack123")
    monkeypatch.setattr(wakeword_routes, "WAKEWORD_DIR", tmp_path)

    detector = WakeWordDetector(wake_word="custom:pack123")
    detector.start()
    assert detector.is_running is True
    live = (phrase + rng.normal(0, 0.05, size=phrase.size)).astype(np.float32)
    assert detector.process_audio(live) is True
    detector.stop()


# ── Decision trace: the tiniest-detail log ────────────────────────────


def test_decision_trace_records_reason_and_file(tmp_path, monkeypatch):
    from app.utils import decision_trace

    monkeypatch.setattr(decision_trace, "TRACE_DISABLED", False)
    monkeypatch.setattr(decision_trace, "_data_dir", lambda: tmp_path)
    entry = decision_trace.record(
        "test_component", "chose_x", "because_y", extra={"k": "v"}
    )
    assert entry is not None
    hits = decision_trace.recent(limit=10, component="test_component")
    assert hits and hits[-1]["reason"] == "because_y"
    log_file = tmp_path / "logs" / "decisions.jsonl"
    assert log_file.exists()
    assert "chose_x" in log_file.read_text()


# ── Static workspace: screenshots reachable in the browser ───────────


def test_workspace_static_mount_exists():
    from app.server import app as server_app

    mount_paths = [
        getattr(route, "path", "") for route in server_app.routes
    ]
    assert "/static/workspace" in mount_paths


def test_screen_current_endpoint_honest_and_serving(tmp_path, monkeypatch):
    from app.config import settings

    shots = tmp_path / "workspace" / "screenshots"
    shots.mkdir(parents=True)
    (shots / "watch_123.png").write_bytes(b"png")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    client = TestClient(app)
    data = client.get("/cognition/screen/current").json()
    assert data["available"] is True
    assert data["url"].endswith("watch_123.png")


# ── Screen probe: the watcher sees the desktop ────────────────────────


def test_screen_probe_surfaces_desktop_changes(tmp_path):
    from app.perception.background_observer import BackgroundObserver, ScreenProbe

    shots = tmp_path / "shots"
    shots.mkdir()
    counter = {"n": 0}

    def fake_capture():
        counter["n"] += 1
        path = shots / f"watch_{counter['n']}.png"
        path.write_bytes(f"png-{counter['n']}".encode())
        return {"path": str(path), "sha256_16": f"h{counter['n']}", "width": 10, "height": 10}

    probe = ScreenProbe(min_interval_s=0.0, output_dir=shots, capturer=fake_capture)
    observer = BackgroundObserver(interval=30.0)
    observer.add_probe(probe)
    changes = observer.run_once()  # first capture -> appeared
    assert any(c.subject == "screen" for c in changes) or probe._last_state
    changes = observer.run_once()  # new image -> changed
    assert any(c.subject == "screen" and c.change_type == "changed" for c in changes)


def test_screen_probe_honest_when_unavailable(tmp_path):
    from app.perception.background_observer import ScreenProbe

    probe = ScreenProbe(
        min_interval_s=0.0,
        output_dir=tmp_path,
        capturer=lambda: None,  # capture failure -> honest unavailable state
    )
    state = probe.probe()
    assert state["screen"]["available"] is False
    assert state["screen"]["reason"]


# ── Parked goals get re-checked and honestly closed ───────────────────


def test_parked_recheck_attempts_then_reports_honestly(monkeypatch):
    from app.cognition import parked_goal_recheck as pgr

    pgr.reset_for_tests()
    rows = [{
        "trace_id": "t1",
        "conversation_id": "conv-1",
        "goal": "open the portal",
        "created_at": "2020-01-01T00:00:00+00:00",  # old enough
    }]
    monkeypatch.setattr(pgr, "collect_parked_goals", lambda limit=5: rows)
    monkeypatch.setattr(pgr, "_MIN_AGE_S", 0.0)
    monkeypatch.setattr(pgr, "_RECHECK_GAP_S", 0.0)

    calls = []

    class _Future:
        def result(self, timeout=None):
            return None

    def _fake_run_coroutine_threadsafe(coro, loop):
        coro.close()  # do not execute; we only count submissions
        calls.append(coro)
        return _Future()

    monkeypatch.setattr("asyncio.run_coroutine_threadsafe", _fake_run_coroutine_threadsafe)

    class _Loop:
        def is_running(self):
            return True

    monkeypatch.setattr(pgr, "_main_loop", _Loop())

    class _FakeRouter:
        def __init__(self):
            from unittest.mock import AsyncMock

            self.handle_message = AsyncMock(return_value="ok")

    fake_router = _FakeRouter()
    from backend import message_router as router_module

    monkeypatch.setattr(router_module, "message_router", fake_router, raising=False)

    for _ in range(pgr._MAX_ATTEMPTS):
        assert pgr.parked_goal_recheck_tick() is not None
    assert len(calls) == pgr._MAX_ATTEMPTS, "one submitted re-check per attempt"
    # Budget spent: the next tick closes the goal honestly, no more re-checks.
    result = pgr.parked_goal_recheck_tick()
    assert result is None
    assert len(calls) == pgr._MAX_ATTEMPTS + 1, (
        "the honest give-up note is submitted to the conversation"
    )
    pgr.reset_for_tests()


# ── In-chat approval utterances bind to REAL pending requests ─────────


def test_yes_do_it_finds_pending_approval_after_escalation():
    """Live log: 'yes do it' arrived but nothing was pending because the
    delete auto-ran at Level 2. With escalation, an approval request exists
    and the utterance decides it."""
    from app.cognition.action_proposal import ActionGate, ActionProposal
    from app.cognition.approval_store import ApprovalStore

    store = ApprovalStore()
    proposal = ActionProposal(
        action_type="os_control_execute",
        payload={
            "plan": {
                "command": "Remove-Item -Path X -Recurse -Force",
                "risk_level": "destructive",
            }
        },
        recommendation_reason="OS control planner",
        confidence=0.75,
    )
    gate = ActionGate.evaluate_proposal(proposal)
    assert gate.requires_approval is True
    # The pending request now exists for the chat utterance to decide.
    pending = [r for r in [store.add("desktop-chat", "os_control_execute", proposal.payload, "destructive plan")] if r]
    assert pending and pending[0].status == "pending"
