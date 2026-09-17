"""Round 10 — context distillation (owner go-ahead 2026-09-13).

What leaves the 16-message window must not leave the mind: departing
turns compress into a standing labeled digest, cost-bounded to one
fast-lane call per 8 departures, and a simulated model NEVER fabricates
memory. These tests pin the contract with an injected provider — no
live model, fully hermetic.
"""

import pytest

from app.cognition import context_distiller as distiller


class StubLLM:
    def __init__(self, content="- owner asked to open itunes\n- verified: not yet",
                 simulated=False, raises=False):
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


@pytest.fixture
def distill_db(monkeypatch, tmp_path):
    import app.database as database_module
    monkeypatch.setattr(
        database_module.db, "db_path", str(tmp_path / "distill.db"))
    database_module.db._init_db()
    return database_module.db


def _history(n_turns):
    return [
        {"role": "user" if i % 2 == 0 else "assistant",
         "content": f"turn {i} content"}
        for i in range(n_turns)
    ]


class TestDigestLifecycle:
    def test_departing_turns_produce_a_persisted_digest(self, distill_db):
        stub = StubLLM(content="- owner asked to open itunes")
        digest = distiller.update_digest("c1", _history(30), llm_client=stub)
        assert stub.calls == 1
        assert digest == "- owner asked to open itunes"
        # persisted: a fresh read sees it
        assert distiller.get_digest("c1") == "- owner asked to open itunes"

    def test_cost_bound_no_call_before_enough_departures(self, distill_db):
        first = StubLLM(content="digest v1")
        distiller.update_digest("c1", _history(30), llm_client=first)
        # 2 more departing turns: below REDISTILL_EVERY — no model call
        second = StubLLM(content="digest v2")
        out = distiller.update_digest("c1", _history(32), llm_client=second)
        assert second.calls == 0
        assert out == "digest v1"

    def test_redistills_after_enough_departures(self, distill_db):
        distiller.update_digest("c1", _history(30), llm_client=StubLLM(content="v1"))
        second = StubLLM(content="v2")
        out = distiller.update_digest(
            "c1", _history(30 + distiller.REDISTILL_EVERY), llm_client=second)
        assert second.calls == 1
        assert out == "v2"

    def test_short_history_needs_no_digest(self, distill_db):
        stub = StubLLM()
        assert distiller.update_digest("c1", _history(18), llm_client=stub) == ""
        assert stub.calls == 0  # only 2 departures < _MIN_DEPARTING_TURNS

    def test_simulated_provider_never_fabricates_memory(self, distill_db):
        # a real digest exists; a simulated re-distillation must not replace it
        distiller.update_digest("c1", _history(30), llm_client=StubLLM(content="real"))
        fake = StubLLM(content="INVENTED MEMORY", simulated=True)
        out = distiller.update_digest(
            "c1", _history(30 + distiller.REDISTILL_EVERY), llm_client=fake)
        assert out == "real"
        assert distiller.get_digest("c1") == "real"

    def test_provider_failure_fails_open_to_previous(self, distill_db):
        distiller.update_digest("c1", _history(30), llm_client=StubLLM(content="real"))
        out = distiller.update_digest(
            "c1", _history(30 + distiller.REDISTILL_EVERY),
            llm_client=StubLLM(raises=True))
        assert out == "real"

    def test_kill_switch(self, distill_db, monkeypatch):
        monkeypatch.setenv("ARENA_CONTEXT_DISTILL", "0")
        stub = StubLLM()
        assert distiller.update_digest("c1", _history(40), llm_client=stub) == ""
        assert stub.calls == 0
        assert distiller.digest_message("anything") is None

    def test_broken_db_fails_open(self, monkeypatch, tmp_path):
        import app.database as database_module
        monkeypatch.setattr(
            database_module.db, "db_path", str(tmp_path / "missing_dir" / "x.db"))
        monkeypatch.setattr(database_module.db, "_initialized", False, raising=False)
        # get_digest must never raise
        assert isinstance(distiller.get_digest("c1"), str)


class TestInjection:
    def test_digest_message_is_labeled_continuity(self):
        msg = distiller.digest_message("- owner asked to open itunes")
        assert msg["role"] == "assistant"
        assert "Context digest" in msg["content"]
        assert "not a new statement" in msg["content"]
        assert "owner asked to open itunes" in msg["content"]

    def test_empty_digest_injects_nothing(self):
        assert distiller.digest_message("") is None
        assert distiller.digest_message("   ") is None


def test_wiring_is_in_place():
    import inspect

    import backend.message_router as mr
    src = inspect.getsource(mr)
    assert "update_digest(conversation_id, history)" in src
    assert "conversation_history=runtime_history" in src
    # the plain window survives as the fail-open path
    assert "runtime_history = history[-16:]" in src
    from app.config import settings
    assert hasattr(settings, "ARENA_CONTEXT_DISTILL")
