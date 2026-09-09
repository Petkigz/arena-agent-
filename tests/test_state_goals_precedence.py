"""P15 carry-over, closed: mind-first precedence for current_goals.

The mind's Motivation organ is the AUTHORITATIVE view of her goals (one
cognitive authority); the runtime's CommitmentLedger stays wired as the
legacy surface — shown under its own key when both are readable, used
as the fallback when the mind organ cannot be read. Same pattern as
the attention room.
"""

from __future__ import annotations

import pytest

from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore
from app.mind import BeanieMind
from app.mind.state import BeanieState


class _Brain:
    def __init__(self, tmp_path):
        self.memory = MemoryStore(tmp_path / "memory.db")
        self.confidence_calibrator = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        self.working_memory = None
        self.hardware_self_model = {}
        self.phase7_preferences = None

    def process_cognitive_cycle(self, user_text, **kwargs):
        return {"success": True, "assistant_reply": "ok"}


class _CommitStub:
    def summary(self):
        return {"open": 2, "items": ["a", "b"]}


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain
    BeanieMind.reset_instance()


def test_mind_first_when_the_mind_is_present(setup):
    mind, _ = setup
    room = mind.state()["current_goals"]
    assert room["status"] == "ok"
    assert room["component"] == "Motivation", \
        "the mind organ is the authoritative goal surface"
    assert "priorities" in room["data"] and "stats" in room["data"]


def test_legacy_surface_stays_wired_beside_the_mind(setup):
    mind, _ = setup
    mind.runtime.commitments = _CommitStub()
    room = mind.state()["current_goals"]
    assert room["component"] == "Motivation"
    assert room["data"]["commitments_legacy"] == {"open": 2,
                                                  "items": ["a", "b"]}


def test_runtime_only_falls_back_to_commitments(tmp_path):
    brain = _Brain(tmp_path)
    brain.commitments = _CommitStub()
    room = BeanieState(brain, identity=None, mind=None)._current_goals()
    assert room["status"] == "ok"
    assert room["component"] == "_CommitStub"
    assert room["data"] == {"open": 2, "items": ["a", "b"]}


def test_runtime_only_without_anything_is_honest(tmp_path):
    room = BeanieState(_Brain(tmp_path), identity=None,
                       mind=None)._current_goals()
    assert room["status"] == "unavailable"


def test_motivation_stats_are_visible_in_the_room(setup):
    mind, _ = setup
    room = mind.state()["current_goals"]
    stats = room["data"]["stats"]
    assert stats["goals"] >= 0 and "policy" in stats
