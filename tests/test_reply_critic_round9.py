"""Round 9 — tighten the loop (owner go-ahead 2026-09-13).

Two organs, both pinned here:
  * the CRITIC PASS — the fast lane reads the draft reply against the
    executed evidence and appends a VISIBLE correction when a claim
    outruns what actually ran. It never touches verified outcomes,
    never double-corrects a guarded reply, treats a simulated provider
    as no critic at all, and fails open on everything.
  * the BOUNDED SWEEP — the autonomous cycle's workspace walk is capped
    and reports truncation honestly (the 284k-file-walk headache).
"""

import pytest

from app.cognition.reply_critic import critique_reply
from app.cognition.periodic_autonomous_cycle import _recent_workspace_files


class StubLLM:
    def __init__(self, content="", simulated=False, raises=False):
        self.content = content
        self.simulated = simulated
        self.raises = raises
        self.calls = 0

    def generate_chat_completion(self, messages, **kwargs):
        self.calls += 1
        if self.raises:
            raise RuntimeError("provider down")
        if self.simulated:
            return {"simulated": True,
                    "choices": [{"message": {"content": self.content}}]}
        return {"choices": [{"message": {"content": self.content}}]}


def _result(reply="I backed up the folder to the external drive.",
            executed=None, verified=False, guard=None):
    out = {
        "assistant_reply": reply,
        "user_text": "back up my projects folder",
        "goal_verified": verified,
        "executed_actions": executed if executed is not None else [
            {"action_type": "executed",
             "detail": "Copied 3 files to D:/backup"}],
        "goal_lifecycle_state": "waiting_for_evidence",
    }
    if guard:
        out["announcement_guard"] = guard
    return out


EXCEEDS = '{"exceeds": true, "unsupported_claim": "backed up to the external drive"}'
CLEAN = '{"exceeds": false, "unsupported_claim": ""}'


class TestCriticPass:
    def test_unsupported_claim_gets_a_visible_correction(self):
        out = critique_reply(_result(), llm_client=StubLLM(EXCEEDS))
        assert out["critic_correction"] == "backed up to the external drive"
        # the owner still sees what she was about to be told
        assert out["assistant_reply"].startswith(
            "I backed up the folder to the external drive.")
        assert "not supported by what actually executed" in out["assistant_reply"]

    def test_supported_reply_is_untouched(self):
        out = critique_reply(_result(), llm_client=StubLLM(CLEAN))
        assert "critic_correction" not in out
        assert out["assistant_reply"] == \
            "I backed up the folder to the external drive."

    def test_verified_outcomes_are_never_critiqued(self):
        stub = StubLLM(EXCEEDS)
        out = critique_reply(_result(verified=True), llm_client=stub)
        assert stub.calls == 0
        assert "critic_correction" not in out

    def test_guarded_replies_are_never_double_corrected(self):
        stub = StubLLM(EXCEEDS)
        out = critique_reply(
            _result(guard="unverified_outcome_surfaced"), llm_client=stub)
        assert stub.calls == 0
        assert "critic_correction" not in out

    def test_no_execution_is_the_honesty_guards_case_not_the_critics(self):
        stub = StubLLM(EXCEEDS)
        out = critique_reply(_result(executed=[]), llm_client=stub)
        assert stub.calls == 0

    def test_simulated_provider_is_not_a_critic(self):
        out = critique_reply(_result(), llm_client=StubLLM(EXCEEDS, simulated=True))
        assert "critic_correction" not in out

    def test_unparseable_verdict_is_ignored(self):
        out = critique_reply(_result(), llm_client=StubLLM("sorry, I cannot"))
        assert "critic_correction" not in out

    def test_provider_failure_fails_open(self):
        original = _result()
        out = critique_reply(original, llm_client=StubLLM(raises=True))
        assert out["assistant_reply"] == original["assistant_reply"]
        assert "critic_correction" not in out

    def test_kill_switch(self, monkeypatch):
        stub = StubLLM(EXCEEDS)
        monkeypatch.setenv("ARENA_REPLY_CRITIC", "0")
        out = critique_reply(_result(), llm_client=stub)
        assert stub.calls == 0
        assert "critic_correction" not in out

    def test_empty_reply_is_skipped(self):
        stub = StubLLM(EXCEEDS)
        assert critique_reply(_result(reply=""), llm_client=stub) == _result(reply="")
        assert stub.calls == 0


class TestBoundedSweep:
    def test_cap_reports_truncation_honestly(self, tmp_path):
        for i in range(12):
            (tmp_path / f"file_{i}.txt").write_text("x")
        names, truncated = _recent_workspace_files(tmp_path, limit=5)
        assert truncated is True
        assert len(names) <= 5

    def test_small_tree_is_not_truncated(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        names, truncated = _recent_workspace_files(tmp_path, limit=100)
        assert names == ["a.txt"]
        assert truncated is False

    def test_missing_directory_fails_open(self, tmp_path):
        names, truncated = _recent_workspace_files(tmp_path / "nope")
        assert names == []
        assert truncated is False


def test_wiring_is_in_place():
    import inspect

    from app.cognition import periodic_autonomous_cycle as pac
    from app.cognition import runtime as cog_runtime

    assert "critique_reply(result)" in inspect.getsource(cog_runtime)
    assert "_recent_workspace_files(workspace)" in inspect.getsource(pac)
    from app.config import settings
    assert hasattr(settings, "ARENA_REPLY_CRITIC")
