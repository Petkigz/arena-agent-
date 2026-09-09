"""Post-roadmap growth (audit #18) — idle replay / dream-like
consolidation.

"When nothing is asked of her, does she replay recent experience
offline and consolidate it?" Contracts pinned here:
- only experiences ALREADY in the ledger are replayed — never invented;
  the watermark prevents re-dreaming the same material;
- threads are gathered from vocabulary overlap and judged ONLY by the
  verifier's tally: strengthen / revisit / open;
- the door replays only when the quiet between messages crossed the
  idle window; the kill switch leaves the organ unconstructed;
- replay describes — never acts, never edits the record.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore
from app.mind import BeanieMind
from app.mind.idle_replay import IdleReplay


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


def _seed(mind, content, success=None):
    exp = {"kind": "observation", "content": content, "source": "test"}
    if success is not None:
        exp["success"] = success
    rec = mind.learn(exp)
    assert rec["success"] is True
    return rec


# ── replay reads only her own record ────────────────────────────────────────
def test_replay_with_no_experiences_rests(setup):
    mind, _, _ = setup
    res = mind.idle_replay.replay()
    assert res["success"] is True and res["acted"] is False
    assert res["epistemic_kind"] == "idle_replay"
    assert res["events_reviewed"] == 0
    assert "the mind rested" in res["statement"]
    assert mind.idle_replay.replays()[0]["statement"] == res["statement"]


def test_replay_reviews_new_experiences(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job ran clean", True)
    _seed(mind, "the nightly sync job copied all files", True)
    _seed(mind, "an unrelated note about the weather", None)
    res = mind.idle_replay.replay()
    assert res["events_reviewed"] == 3
    assert "replayed 3 new experience(s)" in res["statement"]


def test_thread_gathered_from_related_experiences(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job ran clean", True)
    _seed(mind, "the nightly sync job copied all files", True)
    _seed(mind, "an unrelated note about the weather", None)
    res = mind.idle_replay.replay()
    assert len(res["threads"]) == 1, "the singleton stands alone"
    thread = res["threads"][0]
    assert thread["events"] == 2
    assert "sync" in thread["label"] and "nightly" in thread["label"]


def test_thread_verdict_revisit_on_verified_failures(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job failed to start", False)
    _seed(mind, "the nightly sync job failed again", False)
    res = mind.idle_replay.replay()
    assert res["threads"][0]["verdict"] == "revisit"
    assert res["threads"][0]["failures"] == 2
    assert "revisit" in res["statement"]


def test_thread_verdict_strengthen_on_verified_successes(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job ran clean", True)
    _seed(mind, "the nightly sync job copied all files", True)
    res = mind.idle_replay.replay()
    assert res["threads"][0]["verdict"] == "strengthen"


def test_thread_verdict_open_when_mixed(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job ran clean", True)
    _seed(mind, "the nightly sync job failed at the end", False)
    res = mind.idle_replay.replay()
    assert res["threads"][0]["verdict"] == "open"


def test_unknown_verdicts_stay_open(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job was attempted", None)
    _seed(mind, "the nightly sync job log is silent", None)
    res = mind.idle_replay.replay()
    thread = res["threads"][0]
    assert thread["verdict"] == "open"
    assert thread["successes"] == 0 and thread["failures"] == 0


# ── the watermark: no re-dreaming ───────────────────────────────────────────
def test_watermark_prevents_rereview(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job ran clean", True)
    first = mind.idle_replay.replay()
    assert first["events_reviewed"] == 1
    _seed(mind, "the backup job finished early", True)
    _seed(mind, "the backup job verified its archive", True)
    second = mind.idle_replay.replay()
    assert second["events_reviewed"] == 2, "only NEW material is replayed"
    third = mind.idle_replay.replay()
    assert third["events_reviewed"] == 0
    assert "the mind rested" in third["statement"]


def test_watermark_survives_a_new_instance(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job ran clean", True)
    mind.idle_replay.replay()
    fresh = IdleReplay(mind, db_path=mind.db_path)
    res = fresh.replay()
    assert res["events_reviewed"] == 0, \
        "the watermark lives in the ledger, not in memory"


def test_open_gaps_are_named(setup):
    mind, _, _ = setup
    _seed(mind, "the export job stalled", False)
    _seed(mind, "the export job stalled", False)
    res = mind.idle_replay.replay()
    assert len(res["open_gaps"]) == 1
    assert res["open_gaps"][0]["verified_failures"] == 2
    assert "open gap(s) still waiting" in res["statement"]


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_count_replays_and_policy(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job ran clean", True)
    _seed(mind, "the nightly sync job copied all files", True)
    mind.idle_replay.replay()
    _seed(mind, "the backup job finished early", True)
    mind.idle_replay.replay()
    st = mind.idle_replay.stats()
    assert st["replays"] == 2
    assert st["events_reviewed_total"] == 3
    assert st["threads_found_total"] >= 1
    assert st["last_replay_at"]
    assert st["idle_window_seconds"] >= 0
    assert "verifier's tally" in st["policy"]
    assert "never acts" in st["policy"]


def test_snapshot_shape(setup):
    mind, _, _ = setup
    _seed(mind, "the nightly sync job ran clean", True)
    mind.idle_replay.replay()
    snap = mind.idle_replay.snapshot()
    assert snap["organ"] == "idle_replay"
    assert snap["replays"] == 1
    assert isinstance(snap["stream"], list) and len(snap["stream"]) == 1
    assert snap["stream"][0]["acted"] is False


# ── the door: idle window, kill switch, clock ───────────────────────────────
def test_maybe_replay_waits_for_idle_window(setup):
    mind, _, monkeypatch = setup
    monkeypatch.setattr(settings, "ARENA_IDLE_REPLAY_SECONDS", "100000")
    _seed(mind, "the nightly sync job ran clean", True)
    now = datetime.now(timezone.utc).isoformat()
    res = mind.idle_replay.maybe_replay(now)
    assert res["replayed"] is False
    assert "idle window" in res["reason"]
    monkeypatch.setattr(settings, "ARENA_IDLE_REPLAY_SECONDS", "1")
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    res = mind.idle_replay.maybe_replay(old)
    assert res["replayed"] is True
    assert res["events_reviewed"] == 1
    assert res["elapsed_seconds"] > 3600


def test_maybe_replay_without_previous_entry(setup):
    mind, _, _ = setup
    res = mind.idle_replay.maybe_replay(None)
    assert res["replayed"] is False
    assert "no previous entry" in res["reason"]


def test_door_kill_switch_leaves_organ_unconstructed(setup):
    mind, _, monkeypatch = setup
    monkeypatch.setattr(settings, "ARENA_IDLE_REPLAY", "0")
    mind._run_idle_replay()
    assert mind._idle_replay is None, \
        "the kill switch leaves the organ unbuilt"


def test_door_replays_after_the_idle_window(setup):
    mind, brain, monkeypatch = setup
    # window of 5s: the two-hour quiet crosses it, the immediate
    # follow-up message does not
    monkeypatch.setattr(settings, "ARENA_IDLE_REPLAY_SECONDS", "5")
    _seed(mind, "the nightly sync job ran clean", True)
    mind._last_door_iso = (
        datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    mind.process("hello again", modality="text")
    assert brain.calls, "the brain still runs the cycle"
    assert mind._idle_replay is not None
    rows = mind.idle_replay.replays()
    assert len(rows) == 1 and rows[0]["source"] == "idle"
    assert mind._last_door_iso is not None
    # a second immediate message finds no idle window and no new replay
    mind.process("one more thing", modality="text")
    assert len(mind.idle_replay.replays()) == 1
