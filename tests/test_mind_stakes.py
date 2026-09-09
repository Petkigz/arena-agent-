"""Post-roadmap growth (audit #22) — stakes-based effort.

"Does she try equally hard at everything, or does effort follow
stakes?" Contracts pinned here:
- stakes come from four EVIDENCE-BACKED signals: risk markers in the
  words, owner emphasis, her own verified failure history, and the
  owner's authority rules — never vibes;
- levels are routine / careful / critical and the effort plans NEST;
- the organ assesses and records — never executes, never vetoes;
- the door assesses every non-empty request; the kill switch leaves
  the organ unconstructed.
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


# ── the four signals ────────────────────────────────────────────────────────
def test_plain_request_is_routine(setup):
    mind, _, _ = setup
    res = mind.stakes.assess("what time is it")
    assert res["success"] is True and res["acted"] is False
    assert res["epistemic_kind"] == "stakes"
    assert res["level"] == "routine" and res["score"] <= 1
    assert res["reasons"] == []


def test_risk_markers_raise_stakes(setup):
    mind, _, _ = setup
    for task, cat in [("delete the old backups", "destroys_data"),
                      ("pay the hosting invoice", "money"),
                      ("send the report to the client", "outward_comms")]:
        res = mind.stakes.assess(task)
        assert res["level"] in ("careful", "critical")
        assert any(cat in r for r in res["reasons"]), task


def test_owner_emphasis_raises_stakes(setup):
    mind, _, _ = setup
    res = mind.stakes.assess("this is important, do it carefully")
    assert res["level"] in ("careful", "critical")
    assert any("owner emphasis" in r for r in res["reasons"])


def test_verified_failure_history_raises_stakes(setup):
    mind, _, _ = setup
    for _ in range(2):
        rec = mind.learn({"kind": "action", "content": "run the export job",
                          "source": "test", "success": False})
        assert rec["success"] is True
    res = mind.stakes.assess("run the export job for me")
    assert res["level"] in ("careful", "critical")
    assert any("verified failure" in r for r in res["reasons"])


def test_owner_rule_touching_topic_raises_stakes(setup):
    mind, _, _ = setup
    mind.authority.note("never delete photos without asking me")
    res = mind.stakes.assess("delete the old photos")
    assert any("owner rule touches this topic" in r for r in res["reasons"])


def test_rule_read_is_read_only_no_asks_opened(setup):
    mind, _, _ = setup
    mind.authority.note("never delete photos without asking me")
    before = len(mind.authority.pending_asks())
    mind.stakes.assess("delete the old photos")
    mind.stakes.assess("pay the hosting invoice")
    assert len(mind.authority.pending_asks()) == before, \
        "judging stakes is not asking permission"


# ── levels and effort plans ─────────────────────────────────────────────────
def test_critical_combination(setup):
    mind, _, _ = setup
    for _ in range(2):
        mind.learn({"kind": "action", "content": "delete the archive files",
                    "source": "test", "success": False})
    res = mind.stakes.assess(
        "please delete the archive files, this is important")
    assert res["level"] == "critical" and res["score"] >= 4
    plan = " ".join(res["effort_plan"])
    assert "shadow advocate" in plan
    assert "the decision belongs to the owner" in plan


def test_effort_plans_nest(setup):
    mind, _, _ = setup
    routine = mind.stakes.effort_plan("routine")
    careful = mind.stakes.effort_plan("careful")
    critical = mind.stakes.effort_plan("critical")
    assert routine and careful[: len(routine)] == routine
    assert careful and critical[: len(careful)] == careful
    assert len(critical) > len(careful) > len(routine)


def test_low_stakes_is_honest_not_ceremony(setup):
    mind, _, _ = setup
    res = mind.stakes.assess("what did we talk about yesterday")
    assert res["level"] == "routine"
    assert len(res["effort_plan"]) == 2


# ── honesty and determinism ─────────────────────────────────────────────────
def test_assessment_is_deterministic(setup):
    mind, _, _ = setup
    a = mind.stakes.assess("delete the old backups carefully")
    b = mind.stakes.assess("delete the old backups carefully")
    assert a["level"] == b["level"] and a["score"] == b["score"]
    assert a["reasons"] == b["reasons"]


def test_empty_task_assesses_nothing(setup):
    mind, _, _ = setup
    res = mind.stakes.assess("   ")
    assert res["success"] is False
    assert mind.stakes.recent() == []


def test_ledger_records_and_orders(setup):
    mind, _, _ = setup
    mind.stakes.assess("what time is it")
    mind.stakes.assess("pay the hosting invoice")
    rows = mind.stakes.recent()
    assert len(rows) == 2
    assert rows[0]["task"].startswith("pay"), "newest first"
    assert mind.stakes.current()["level"] == rows[0]["level"]
    assert rows[1]["acted"] is False


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_counts_by_level_and_policy(setup):
    mind, _, _ = setup
    mind.stakes.assess("what time is it")
    mind.stakes.assess("delete the old backups")
    st = mind.stakes.stats()
    assert st["assessments"] == 2
    assert st["by_level"].get("routine") == 1
    assert st["by_level"].get("careful", 0) + st["by_level"].get("critical", 0) == 1
    assert st["levels"] == ["routine", "careful", "critical"]
    assert "effort follows stakes" in st["policy"]
    assert "never vetoes" in st["policy"]


def test_snapshot_shape(setup):
    mind, _, _ = setup
    mind.stakes.assess("send the invoice to the client")
    snap = mind.stakes.snapshot()
    assert snap["organ"] == "stakes"
    assert snap["assessments"] == 1
    assert isinstance(snap["stream"], list) and len(snap["stream"]) == 1


# ── the door ────────────────────────────────────────────────────────────────
def test_door_kill_switch_leaves_organ_unconstructed(setup):
    mind, _, monkeypatch = setup
    monkeypatch.setattr(settings, "ARENA_STAKES", "0")
    mind._run_stakes("delete everything carefully")
    assert mind._stakes is None, "the kill switch leaves the organ unbuilt"


def test_door_assesses_every_nonempty_request(setup):
    mind, brain, _ = setup
    mind.process("please delete the old backups, carefully", modality="text")
    assert brain.calls, "the brain still runs the cycle"
    rows = mind.stakes.recent()
    assert len(rows) == 1
    assert rows[0]["level"] in ("careful", "critical")
    mind.process("", modality="text")
    assert len(mind.stakes.recent()) == 1, "empty input assesses nothing"
