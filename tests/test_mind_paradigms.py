"""Post-roadmap growth (audit #21) — ontological paradigm shifts.

"Can she overturn a deep assumption when verified evidence breaks it —
or does she only patch exceptions forever?" Contracts pinned here:
- paradigms come from universal MARKERS in the owner's words or from
  her own verified tally — never invented; imperatives addressed at
  her are the authority organ's lane;
- one verified counter-example STRAINS, two OVERTURN — and the shift
  is recorded exactly once, with its evidence and a replacement that
  names the change;
- unrelated evidence does not break a paradigm;
- the door captures universals and scans; the kill switch leaves the
  organ unconstructed.
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


def _seed(mind, content, success):
    rec = mind.learn({"kind": "observation", "content": content,
                      "source": "test", "success": success})
    assert rec["success"] is True


# ── capture: markers only, never vibes ──────────────────────────────────────
def test_no_markers_means_nothing_assumed(setup):
    mind, _, _ = setup
    assert mind.paradigms.assume("the sync job ran fine today") is None
    assert mind.paradigms.paradigms() == []


def test_positive_universal_captured(setup):
    mind, _, _ = setup
    res = mind.paradigms.assume("the nightly sync always works")
    assert res["captured"] is True and res["polarity"] == "positive"
    assert res["source"] == "owner_teaching" and res["status"] == "held"
    assert res["acted"] is False


def test_negative_universal_captured(setup):
    mind, _, _ = setup
    res = mind.paradigms.assume("the export job never finishes")
    assert res["captured"] is True and res["polarity"] == "negative"


def test_imperatives_belong_to_authority_not_ontology(setup):
    mind, _, _ = setup
    assert mind.paradigms.assume(
        "never delete photos without asking me") is None
    assert mind.paradigms.assume("please always restart before syncing") is None
    assert mind.paradigms.paradigms() == []


def test_restatement_does_not_duplicate(setup):
    mind, _, _ = setup
    mind.paradigms.assume("the nightly sync always works")
    again = mind.paradigms.assume("the nightly sync always works")
    assert again["captured"] is False and again["compounded"] is True
    assert len(mind.paradigms.paradigms()) == 1


# ── the shift mechanism ─────────────────────────────────────────────────────
def test_one_counter_example_strains_but_holds(setup):
    mind, _, _ = setup
    mind.paradigms.assume("the nightly sync always works")
    _seed(mind, "the nightly sync failed to start", False)
    res = mind.paradigms.scan()
    assert res["strained"] == 1 and res["overturned_now"] == 0
    row = mind.paradigms.paradigms()[0]
    assert row["status"] == "strained" and len(row["anomalies"]) == 1


def test_two_counter_examples_overturn(setup):
    mind, _, _ = setup
    mind.paradigms.assume("the nightly sync always works")
    _seed(mind, "the nightly sync failed to start", False)
    _seed(mind, "the nightly sync failed mid-copy", False)
    res = mind.paradigms.scan()
    assert res["overturned_now"] == 1
    shift = res["overturned"][0]
    assert len(shift["anomalies"]) == 2
    assert all(a["verified"] for a in shift["anomalies"])
    assert "no longer universal" in shift["replacement"]
    assert "2 verified counter-example(s)" in shift["replacement"]


def test_negative_paradigm_overturned_by_successes(setup):
    mind, _, _ = setup
    mind.paradigms.assume("the export job never finishes")
    _seed(mind, "the export job finished early", True)
    _seed(mind, "the export job finished cleanly", True)
    res = mind.paradigms.scan()
    assert res["overturned_now"] == 1


def test_unrelated_evidence_does_not_break(setup):
    mind, _, _ = setup
    mind.paradigms.assume("the nightly sync always works")
    _seed(mind, "the weather widget crashed twice", False)
    _seed(mind, "the weather widget crashed again", False)
    res = mind.paradigms.scan()
    assert res["overturned_now"] == 0 and res["strained"] == 0
    assert mind.paradigms.paradigms()[0]["status"] == "held"


def test_overturn_is_recorded_exactly_once(setup):
    mind, _, _ = setup
    mind.paradigms.assume("the nightly sync always works")
    _seed(mind, "the nightly sync failed to start", False)
    _seed(mind, "the nightly sync failed mid-copy", False)
    first = mind.paradigms.scan()
    second = mind.paradigms.scan()
    assert first["overturned_now"] == 1
    assert second["overturned_now"] == 0
    assert len(mind.paradigms.shifts()) == 1
    assert mind.paradigms.shifts()[0]["overturned_at"]


# ── generalizations from her own record ─────────────────────────────────────
def test_generalize_from_clean_success_record(setup):
    mind, _, _ = setup
    for c in ("the backup job finished early",
              "the backup job verified its archive",
              "the backup job ran clean end to end"):
        _seed(mind, c, True)
    res = mind.paradigms.generalize("the backup job")
    assert res["formed"] is True and res["source"] == "own_record"
    assert "has held so far" in res["statement"]


def test_generalize_refuses_without_a_clean_record(setup):
    mind, _, _ = setup
    _seed(mind, "the backup job finished early", True)
    _seed(mind, "the backup job stalled once", False)
    res = mind.paradigms.generalize("the backup job")
    assert res["formed"] is False and "verified failure" in res["reason"]
    only_two = mind.paradigms.generalize("the sync helper")
    assert only_two["formed"] is False


def test_shifts_lists_only_overturned(setup):
    mind, _, _ = setup
    mind.paradigms.assume("the nightly sync always works")
    mind.paradigms.assume("the cache never expires")
    _seed(mind, "the nightly sync failed to start", False)
    _seed(mind, "the nightly sync failed mid-copy", False)
    mind.paradigms.scan()
    shifts = mind.paradigms.shifts()
    assert len(shifts) == 1 and "sync" in shifts[0]["statement"]


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_counts_and_policy(setup):
    mind, _, _ = setup
    mind.paradigms.assume("the nightly sync always works")
    st = mind.paradigms.stats()
    assert st["paradigms"] == 1 and st["by_status"] == {"held": 1}
    assert st["overturn_threshold"] == 2 and st["generalize_after"] == 3
    assert "two verified counter-examples overturn" in st["policy"]


def test_snapshot_shape(setup):
    mind, _, _ = setup
    mind.paradigms.assume("the nightly sync always works")
    snap = mind.paradigms.snapshot()
    assert snap["organ"] == "paradigms"
    assert isinstance(snap["stream"], list) and len(snap["stream"]) == 1


# ── the door ────────────────────────────────────────────────────────────────
def test_door_kill_switch_leaves_organ_unconstructed(setup):
    mind, _, monkeypatch = setup
    monkeypatch.setattr(settings, "ARENA_PARADIGMS", "0")
    mind._run_paradigms("the nightly sync always works")
    assert mind._paradigms is None, "the kill switch leaves the organ unbuilt"


def test_door_captures_and_scans(setup):
    mind, brain, _ = setup
    mind.process("the nightly sync always works", modality="text")
    assert brain.calls, "the brain still runs the cycle"
    assert len(mind.paradigms.paradigms()) == 1
    # verified counter-evidence arrives; the next pass through the door
    # records the strain — the shift happens when the evidence does
    _seed(mind, "the nightly sync failed to start", False)
    mind.process("run it again", modality="text")
    assert mind.paradigms.paradigms()[0]["status"] == "strained"
