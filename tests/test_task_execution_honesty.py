"""The owner's 2026-09-08 corrections, pinned:

1. Tasks must be DONE or honestly reported — never "I'm working on it"
   announcements, never success claims the machine did not verify.
2. Model lanes per the owner's plan: 3b-class for conversation, best
   general (9b) for heavy work, the CODE SPECIALIST for coding tasks.
3. The screen watcher stays vision-capable but resource-light: memory
   captures, write-only-on-change, tiny retention.
4. Elevated operation is the owner's intended posture when acknowledged.
"""

import httpx
import pytest

from app.config import settings
from app.cognition.completion_honesty import enforce_completion_honesty


# ── 1. Completion honesty guard ───────────────────────────────────────


def test_promise_without_action_is_replaced():
    """The 'kampala' case: a knowledge_query reply promising 'I'll fetch...
    please hold' with nothing executed."""
    result = {
        "user_text": "kampala",
        "assistant_reply": "I'll fetch the weather for Kampala right now. Please hold while I check.",
        "goal_verified": True,  # even a self-'verified' chat cycle
        "executed_actions": [{"action_type": "formulate_answer"}],
        "goal_lifecycle_state": "achieved",
        "session_id": "desktop-chat",
    }
    guarded = enforce_completion_honesty(result, enabled=True)
    assert "have not actually done" in guarded["assistant_reply"]
    assert "do it" in guarded["assistant_reply"]
    assert guarded["announcement_guard"] == "promise_without_action_replaced"


def test_unverified_delete_claim_gets_honest_status():
    """The 'neww folder' case: the command ran, verification says NOT
    achieved, yet the reply claimed 'I have observed that the folder has
    been deleted'."""
    result = {
        "user_text": "can you delete the neww folder on my desktop",
        "assistant_reply": "I have observed that the neww folder has been deleted from your desktop.",
        "goal_verified": False,
        "executed_actions": [
            {"action_type": "os_control_execute"},
            {"action_type": "formulate_answer"},
        ],
        "goal_lifecycle_state": "failed",
        "verification": {"reason": "deletion not observed on disk"},
        "session_id": "desktop-chat",
    }
    guarded = enforce_completion_honesty(result, enabled=True)
    assert guarded["assistant_reply"].startswith(
        "I have observed"  # original claim kept visible...
    )
    assert "Honest status: I ran os_control_execute" in guarded["assistant_reply"]
    assert "FAILED" in guarded["assistant_reply"]
    assert "deletion not observed" in guarded["assistant_reply"]


def test_announcing_after_failed_action_gets_status():
    """The launch_app case: action failed, reply keeps announcing 'Let's
    check...' — the owner must see the real state."""
    result = {
        "user_text": "open richst tv",
        "assistant_reply": "I see you're trying to open RichST TV. Let's check if it's installed by searching now.",
        "goal_verified": False,
        "executed_actions": [{"action_type": "launch_app"}],
        "goal_lifecycle_state": "waiting_for_evidence",
        "verification": {"reason": "no perception evidence"},
        "session_id": "desktop-chat",
    }
    guarded = enforce_completion_honesty(result, enabled=True)
    assert "UNVERIFIED" in guarded["assistant_reply"]


def test_verified_achieved_reply_is_untouched():
    result = {
        "user_text": "what is 2+2",
        "assistant_reply": "2 + 2 = 4.",
        "goal_verified": True,
        "executed_actions": [{"action_type": "deterministic_calculate"}],
        "goal_lifecycle_state": "achieved",
    }
    guarded = enforce_completion_honesty(result, enabled=True)
    assert guarded["assistant_reply"] == "2 + 2 = 4."
    assert "announcement_guard" not in guarded


def test_guard_disabled_passthrough():
    result = {
        "user_text": "kampala",
        "assistant_reply": "I'll fetch it right now.",
        "executed_actions": [],
        "goal_verified": False,
    }
    guarded = enforce_completion_honesty(result, enabled=False)
    assert guarded["assistant_reply"] == "I'll fetch it right now."


# ── 2. Model lanes: coder for code, general for the rest ──────────────


@pytest.fixture()
def _real_llm_transport(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_DISABLED", raising=False)


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Client error '{self.status_code}'",
                request=httpx.Request("POST", "http://test/v1/chat/completions"),
                response=httpx.Response(self.status_code, text=self.text),
            )

    def json(self):
        return self._json


class _FakeHTTP:
    def __init__(self, loaded):
        self.loaded = loaded
        self.post_models = []

    def get(self, url, timeout=None):
        return _FakeResp(200, {"data": [{"id": m} for m in self.loaded]})

    def close(self):
        pass

    def post(self, url, json=None, timeout=None):
        self.post_models.append((json or {}).get("model"))
        return _FakeResp(200, {
            "id": "chat-1", "model": (json or {}).get("model"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"completion_tokens": 2},
        })


def _client_with(fake):
    from app.llm import LocalLLMClient

    client = LocalLLMClient(base_url="http://test/v1")
    client.client = fake
    return client


OWNER_LIVE_LOADED = [
    "qwen3-coder-30b-a3b-instruct",  # what hijacked chat in the live test
    "qwen2.5-9b-instruct",           # the owner's heavy-task general model
    "qwen2.5-3b-instruct",           # conversational
]


def test_code_lane_routes_to_coder_conversational_to_general(_real_llm_transport, monkeypatch):
    """Owner plan: code tasks -> coder specialist; everything else stays on
    the general lanes (3b fast / 9b main) — the coder must NOT hijack."""
    monkeypatch.setattr(settings, "CODE_MODEL", "auto")
    fake = _FakeHTTP(OWNER_LIVE_LOADED)
    client = _client_with(fake)

    # A coding task on the code lane -> the coder specialist.
    client.generate_chat_completion(
        [{"role": "user", "content": "write a parser"}], complexity="code")
    assert fake.post_models[-1] == "qwen3-coder-30b-a3b-instruct"

    # A conversational reply on the fast lane -> the 3b class model.
    client.generate_chat_completion(
        [{"role": "user", "content": "hi"}], complexity="fast")
    assert fake.post_models[-1] == "qwen2.5-3b-instruct"

    # Heavy work on the main lane -> the best GENERAL model (not the coder).
    client.generate_chat_completion(
        [{"role": "user", "content": "research plan"}], complexity="main")
    assert fake.post_models[-1] == "qwen2.5-9b-instruct"


def test_code_lane_without_coder_falls_back_to_main(_real_llm_transport, monkeypatch):
    monkeypatch.setattr(settings, "CODE_MODEL", "auto")
    fake = _FakeHTTP(["qwen2.5-9b-instruct", "qwen2.5-3b-instruct"])
    client = _client_with(fake)
    client.generate_chat_completion(
        [{"role": "user", "content": "write a parser"}], complexity="code")
    assert fake.post_models[-1] == "qwen2.5-9b-instruct"


def test_code_lane_pinned_model_wins(_real_llm_transport, monkeypatch):
    monkeypatch.setattr(settings, "CODE_MODEL", "qwen2.5-coder-14b")
    fake = _FakeHTTP(OWNER_LIVE_LOADED)
    client = _client_with(fake)
    client.generate_chat_completion(
        [{"role": "user", "content": "write a parser"}], complexity="code")
    # Pinned id not loaded -> honest main-lane fallback (never a fake 200
    # from a model that isn't there).
    assert fake.post_models[-1] == "qwen2.5-9b-instruct"


def test_runtime_code_task_detection():
    from app.cognition.runtime import CognitiveRuntime

    assert CognitiveRuntime._looks_like_code_task("write a python script to sort my files")
    assert CognitiveRuntime._looks_like_code_task("debug the login function")
    assert CognitiveRuntime._looks_like_code_task("refactor this sql query")
    assert not CognitiveRuntime._looks_like_code_task("whats the weather in kampala")
    assert not CognitiveRuntime._looks_like_code_task("open docker")


# ── 3. Screen watcher stays vision-capable but resource-light ─────────


def test_screen_probe_writes_only_on_change(tmp_path, monkeypatch):
    from app.perception.background_observer import BackgroundObserver, ScreenProbe

    probe = ScreenProbe(min_interval_s=0.0, output_dir=tmp_path)
    payloads = iter([
        (b"png-one", "hash1", 100, 100),
        (b"png-one", "hash1", 100, 100),  # unchanged -> NO new write
        (b"png-two", "hash2", 100, 100),  # changed -> write
    ])
    monkeypatch.setattr(probe, "_grab_bytes", lambda: next(payloads))

    observer = BackgroundObserver(interval=30.0)
    observer.add_probe(probe)

    observer.run_once()
    assert len(list(tmp_path.glob("watch_*.png"))) == 1
    state2 = observer.run_once()  # unchanged screen
    assert len(list(tmp_path.glob("watch_*.png"))) == 1, "unchanged screen must not write"
    assert not any(c.subject == "screen" for c in state2), "no change event for identical screen"
    observer.run_once()  # changed screen
    assert len(list(tmp_path.glob("watch_*.png"))) == 2, "changed screen writes one new shot"


def test_screen_probe_retention_is_small(tmp_path, monkeypatch):
    from app.perception.background_observer import ScreenProbe

    probe = ScreenProbe(min_interval_s=0.0, output_dir=tmp_path)
    counter = {"n": 0}

    def grab():
        counter["n"] += 1
        return (f"png-{counter['n']}".encode(), f"h{counter['n']}", 10, 10)

    monkeypatch.setattr(probe, "_grab_bytes", grab)
    for _ in range(9):
        probe._default_capture()
    files = list(tmp_path.glob("watch_*.png"))
    assert len(files) == ScreenProbe.KEEP_LAST


def test_screen_probe_default_cadence_is_slow():
    from app.perception.background_observer import ScreenProbe

    assert ScreenProbe.DEFAULT_MIN_INTERVAL_S >= 300, (
        "the owner asked for a resource-light watcher; default grabs stay rare"
    )


# ── 4. Elevated operation acknowledged by the owner ───────────────────


def test_elevated_acknowledged_becomes_info(monkeypatch):
    from app.server import _log_elevation_status

    monkeypatch.setattr(settings, "ARENA_ELEVATED_ACKNOWLEDGED", "1")
    calls = []

    class _Log:
        def info(self, message, *a, **k):
            calls.append(("INFO", message))

        def warning(self, message, *a, **k):
            calls.append(("WARNING", message))

    _log_elevation_status(is_elevated=True, platform="win32", logger=_Log())
    assert calls and calls[0][0] == "INFO"
    assert "acknowledged by owner policy" in calls[0][1]

    # Unacknowledged stays a warning.
    monkeypatch.setattr(settings, "ARENA_ELEVATED_ACKNOWLEDGED", "0")
    calls.clear()
    _log_elevation_status(is_elevated=True, platform="win32", logger=_Log())
    assert calls[0][0] == "WARNING"
