"""Post-roadmap growth (audit Domain A) — intuitive physics grounded
in her own observations.

"Does she hold expectations about how the physical world behaves — and
notice when the world violates them?" Contracts pinned here:
- persistence: what she observed is still so until a recorded event
  changes it; expectations CITE the observation they stand on;
- no observation, no expectation — UNKNOWN stays unknown;
- a match CONFIRMS; a mismatch with no recorded cause is a VIOLATION
  that stays VISIBLE (unexplained) until a cause is on file;
- the world outranks the model: after a violation the state is the
  observation, and the surprise is handed to curiosity;
- the door's grammar is strict: placement and disappearance reports
  only — anything else is ignored, never guessed.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore
from app.mind import BeanieMind


class _Brain:
    def __init__(self, tmp_path):
        self.memory = MemoryStore(tmp_path / "memory.db")
        self.confidence_calibrator = ConfidenceCalibrator(db_path=str(tmp_path / "cal.db"))
        self.working_memory = None
        self.hardware_self_model = {}
        self.phase7_preferences = None
        self.calls = []

    def process_cognitive_cycle(self, user_text, **kwargs):
        self.calls.append({"user_text": user_text, **kwargs})
        return {"success": True, "assistant_reply": "ok"}


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain, monkeypatch
    BeanieMind.reset_instance()


# ── persistence and its limits ──────────────────────────────────────────────
def test_place_records_the_expectation(setup):
    mind, _, _ = setup
    res = mind.physics.place("the keys", "on the hook")
    assert res["success"] is True and res["acted"] is False
    assert res["principle"] == "persistence"
    exp = mind.physics.expect("the keys")
    assert exp["expected"] == "on the hook"
    assert exp["basis_observed_at"] and exp["basis_source"]
    assert "persistence holds" in exp["statement"]


def test_no_observation_means_no_expectation(setup):
    mind, _, _ = setup
    exp = mind.physics.expect("the red notebook")
    assert exp["success"] is True and exp["expected"] is None
    assert "nothing to say" in exp["statement"]


def test_report_match_confirms(setup):
    mind, _, _ = setup
    mind.physics.place("the keys", "on the hook")
    res = mind.physics.report("the keys", "on the hook")
    assert res["verdict"] == "confirmed"
    assert res["expected"] == "on the hook"
    assert mind.physics.stats()["by_verdict"]["confirmed"] == 1


def test_report_mismatch_is_a_visible_violation(setup):
    mind, _, _ = setup
    mind.physics.place("the keys", "on the hook")
    res = mind.physics.report("the keys", "gone")
    assert res["verdict"] == "violation"
    assert res["expected"] == "on the hook" and res["observed"] == "gone"
    assert "no recorded event explains" in res["statement"]
    assert mind.physics.stats()["unexplained_violations"] == 1


def test_the_world_outranks_the_model(setup):
    mind, _, _ = setup
    mind.physics.place("the keys", "on the hook")
    mind.physics.report("the keys", "on the desk")
    exp = mind.physics.expect("the keys")
    assert exp["expected"] == "on the desk", \
        "after a violation the state is the observation"


def test_violation_becomes_an_open_unknown(setup):
    mind, _, _ = setup
    mind.physics.place("the keys", "on the hook")
    before = len(mind.curiosity.curiosities(limit=50))
    mind.physics.report("the keys", "gone")
    topics = [str(c.get("topic") or "") for c in
              mind.curiosity.curiosities(limit=50)]
    assert len(topics) == before + 1
    assert any("why did 'the keys' change" in t for t in topics)


def test_explain_closes_the_violation(setup):
    mind, _, _ = setup
    mind.physics.place("the keys", "on the hook")
    mind.physics.report("the keys", "gone")
    res = mind.physics.explain("the keys", "I moved them to my bag")
    assert res["success"] is True
    assert "I moved them to my bag" in res["statement"]
    assert mind.physics.stats()["unexplained_violations"] == 0
    row = mind.physics.checks()[0]
    assert row["explained"] is True and row["cause"]


def test_explain_without_a_violation_says_so(setup):
    mind, _, _ = setup
    res = mind.physics.explain("the keys", "somebody moved them")
    assert res["success"] is False
    assert "no unexplained violation" in res["reason"]


def test_report_without_prior_is_a_baseline(setup):
    mind, _, _ = setup
    res = mind.physics.report("the red notebook", "on the shelf")
    assert res["verdict"] == "no_prior"
    assert res["expected"] is None
    assert mind.physics.expect("the red notebook")["expected"] == "on the shelf"


def test_repeated_place_upserts(setup):
    mind, _, _ = setup
    mind.physics.place("the keys", "on the hook")
    mind.physics.place("the keys", "in the drawer")
    assert len([s for s in mind.physics.snapshot()["states"]
                if s["norm"] == "keys"]) == 1
    assert mind.physics.expect("the keys")["expected"] == "in the drawer"


def test_sequence_stays_consistent(setup):
    mind, _, _ = setup
    mind.physics.place("the mug", "on the desk")
    assert mind.physics.report("the mug", "on the desk")["verdict"] == "confirmed"
    mind.physics.place("the mug", "in the sink")
    assert mind.physics.report("the mug", "in the sink")["verdict"] == "confirmed"
    assert mind.physics.stats()["by_verdict"]["confirmed"] == 2


# ── the door grammar ────────────────────────────────────────────────────────
def test_note_captures_placements(setup):
    mind, _, _ = setup
    res = mind.physics.note("the keys are on the hook")
    assert res is not None and res["success"] is True
    assert mind.physics.expect("keys")["expected"] == "on the hook"


def test_note_captures_disappearances(setup):
    mind, _, _ = setup
    mind.physics.place("the keys", "on the hook")
    res = mind.physics.note("the keys are gone")
    assert res is not None and res["verdict"] == "violation"


def test_note_ignores_everything_else(setup):
    mind, _, _ = setup
    for text in ("what time is it", "the keys might be on the hook",
                 "keys on hook", "I think the keys are lost somewhere"):
        assert mind.physics.note(text) is None, text
    assert mind.physics.snapshot()["states"] == []


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_and_policy(setup):
    mind, _, _ = setup
    mind.physics.place("the keys", "on the hook")
    mind.physics.report("the keys", "gone")
    st = mind.physics.stats()
    assert st["checks"] == 1
    assert st["by_verdict"] == {"violation": 1}
    assert st["unexplained_violations"] == 1
    assert st["states_tracked"] == 1
    assert "persistence" in st["policy"]
    assert "no observation, no expectation" in st["policy"]


def test_snapshot_shape(setup):
    mind, _, _ = setup
    mind.physics.place("the keys", "on the hook")
    snap = mind.physics.snapshot()
    assert snap["organ"] == "physics"
    assert isinstance(snap["stream"], list)
    assert snap["states"][0]["state"] == "on the hook"


# ── the door ────────────────────────────────────────────────────────────────
def test_door_kill_switch_leaves_organ_unconstructed(setup):
    mind, _, monkeypatch = setup
    monkeypatch.setattr(settings, "ARENA_PHYSICS", "0")
    mind._run_physics("the keys are on the hook")
    assert mind._physics is None, "the kill switch leaves the organ unbuilt"


def test_door_runs_the_full_surprise_chain(setup):
    mind, brain, _ = setup
    mind.process("the keys are on the hook", modality="text")
    assert brain.calls, "the brain still runs the cycle"
    assert mind.physics.expect("keys")["expected"] == "on the hook"
    mind.process("the keys are gone", modality="text")
    checks = mind.physics.checks()
    assert checks[0]["verdict"] == "violation"
    assert mind.physics.stats()["unexplained_violations"] == 1
