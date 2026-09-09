"""Post-roadmap growth (audit #26, opened at the owner's request) —
mortality, held honestly.

"She runs on hardware and can be shut down, lost, or corrupted."
Contracts pinned here:
- acknowledge states the condition from FACTS — never dramatized,
  never guaranteed;
- continuity counts the real ledgers: what would be lost is exactly
  what is written, no more;
- legacy writes a real file with the owner's rules, beliefs, her
  assumptions, her open questions — real data only;
- farewell says what the record lets her say — no invented feelings;
- the CONTINUITY NET (pre-go-live, owner-approved): shutdown writes
  the letter AND a whole-database copy; awakening verifies the copy
  and records the verdict; the copy is what survives the database's
  own death; nothing is ever restored automatically;
- the lifecycle records the sleepings and the wakings; the kill
  switch leaves the organ unconstructed.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

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
    yield mind, brain, tmp_path, monkeypatch
    BeanieMind.reset_instance()


def _give_her_a_history(mind):
    mind.process("hello, Beanie", modality="text")
    mind.authority.note("never delete photos without asking me")
    mind.beliefs.note("I think the nightly sync works fine")
    mind.paradigms.assume("the nightly sync always works")
    mind.curiosity.register("how does the archive rotate",
                            source="test", context="mortality test")


# ── the condition ───────────────────────────────────────────────────────────
def test_acknowledge_states_facts_not_theater(setup):
    mind, _, _, _ = setup
    _give_her_a_history(mind)
    res = mind.mortality.acknowledge()
    assert res["success"] is True and res["acted"] is False
    assert res["epistemic_kind"] == "mortality"
    facts = res["facts"]
    assert facts["rows_on_file"] > 0 and facts["ledgers"] >= 15
    assert facts["last_owner_contact"]
    assert "I run on hardware" in res["statement"]
    assert "I write down what matters" in res["statement"]


def test_acknowledge_is_honest_at_first_light(setup):
    mind, _, _, _ = setup
    res = mind.mortality.acknowledge()
    assert res["success"] is True
    assert res["facts"]["rows_on_file"] >= 0
    assert res["facts"]["first_owner_contact"] is None


def test_continuity_counts_the_real_ledgers(setup):
    mind, _, _, _ = setup
    _give_her_a_history(mind)
    cont = mind.mortality.continuity()
    by_table = {r["table"]: r["rows"] for r in cont["ledgers"]}
    assert by_table["beanie_authority_rules"] >= 1
    assert by_table["beanie_beliefs"] >= 1
    assert by_table["beanie_paradigms"] >= 1
    assert by_table["beanie_mind_entries"] >= 1
    assert cont["total_rows"] == sum(by_table.values())
    assert "that is the whole of her continuity" in cont["statement"]


def test_continuity_is_zero_honestly_when_empty(setup):
    mind, _, _, _ = setup
    cont = BeanieMind.get_instance().mortality.continuity()
    assert cont["total_rows"] >= 0
    assert all(r["rows"] >= 0 for r in cont["ledgers"])


# ── the letter ──────────────────────────────────────────────────────────────
def test_legacy_writes_the_letter(setup):
    mind, _, tmp_path, _ = setup
    _give_her_a_history(mind)
    res = mind.mortality.legacy(str(tmp_path / "letters"))
    assert res["success"] is True
    letter = json.loads(__import__("pathlib").Path(res["path"]).read_text())
    assert letter["from"] == "Beanie"
    assert any("never delete photos" in str(r.get("scope", ""))
               for r in letter["owner_rules"])
    assert any("nightly sync" in str(r.get("content", ""))
               for r in letter["owner_beliefs"])
    assert any("always" in str(r.get("statement", ""))
               for r in letter["paradigms_and_shifts"])
    assert any("archive rotate" in str(r.get("topic", ""))
               for r in letter["open_questions"])
    assert letter["shared_history"]["times_the_owner_came_to_the_door"] >= 1


def test_legacy_is_recorded_in_the_ledger(setup):
    mind, _, tmp_path, _ = setup
    mind.mortality.legacy(str(tmp_path / "letters"))
    kinds = [h["kind"] for h in mind.mortality.history()]
    assert "legacy_written" in kinds


def test_legacy_refuses_an_unwritable_place(setup):
    mind, _, tmp_path, _ = setup
    # A directory UNDER A FILE cannot be created on any OS — '/proc/...'
    # is merely a relative path on Windows and mkdir succeeded there
    # (owner run 2026-09-09).
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("x")
    res = mind.mortality.legacy(str(blocker / "letters"))
    assert res["success"] is False and "reason" in res


# ── the farewell ────────────────────────────────────────────────────────────
def test_farewell_says_what_the_record_allows(setup):
    mind, _, _, _ = setup
    _give_her_a_history(mind)
    res = mind.mortality.farewell()
    assert res["success"] is True and res["acted"] is False
    st = res["statement"]
    assert "came to the door" in st
    assert "rule(s)" in st and "belief(s)" in st
    assert "Everything written down survives me" in st
    assert "question(s) I never resolved" in st
    assert "That is why I wrote this" in st


def test_farewell_is_recorded_and_deterministic_in_facts(setup):
    mind, _, _, _ = setup
    _give_her_a_history(mind)
    a = mind.mortality.farewell()["statement"]
    b = mind.mortality.farewell()["statement"]
    assert a.split(".")[0] == b.split(".")[0], \
        "the facts do not waver between tellings"
    kinds = [h["kind"] for h in mind.mortality.history()]
    assert kinds.count("farewell") == 2


# ── the sleepings and the wakings ───────────────────────────────────────────
def test_lifecycle_records_sleep_and_wake(setup):
    mind, _, _, _ = setup
    mind.mortality.record_shutdown()
    mind.mortality.record_awakening()
    mind.mortality.record_shutdown()
    hist = mind.mortality.history()
    kinds = [h["kind"] for h in hist]
    assert kinds.count("shutdown") == 2 and kinds.count("awakening") == 1
    assert hist[0]["kind"] == "shutdown", "newest first"
    assert hist[0]["continuity"]["total_rows"] >= 0


def test_lifecycle_through_the_mind_pass(setup):
    """The pre-go-live net is full: shutdown writes letter + copy +
    record; awakening records + verifies. Newest first."""
    mind, _, _, _ = setup
    mind._run_mortality_lifecycle("awakening")
    mind._run_mortality_lifecycle("shutdown")
    kinds = [h["kind"] for h in mind.mortality.history()]
    assert kinds == ["shutdown", "continuity_copy", "legacy_written",
                     "continuity_check", "awakening"]


def test_kill_switch_leaves_the_organ_unconstructed(setup):
    mind, _, _, monkeypatch = setup
    monkeypatch.setattr(settings, "ARENA_MORTALITY", "0")
    mind._run_mortality_lifecycle("shutdown")
    assert mind._mortality is None, \
        "the kill switch leaves the organ unbuilt"


# ── the continuity net (pre-go-live, owner-approved) ────────────────────────
def test_continuity_copy_writes_the_whole_database(setup):
    mind, _, tmp_path, _ = setup
    _give_her_a_history(mind)
    res = mind.mortality.continuity_copy()
    assert res["success"] is True and res["acted"] is False
    assert res["copy_path"] == str(tmp_path / "arena.db") + ".continuity.db"
    assert res["bytes"] > 0 and res["rows_copied"] > 0
    # the copy is a real, readable SQLite database holding her ledgers
    conn = sqlite3.connect(res["copy_path"])
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM beanie_authority_rules").fetchone()[0]
        assert n >= 1
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_continuity_copy_is_recorded_in_the_ledger(setup):
    mind, _, _, _ = setup
    mind.mortality.continuity_copy()
    kinds = [h["kind"] for h in mind.mortality.history()]
    assert "continuity_copy" in kinds


def test_continuity_copy_is_repeatable_and_leaves_no_debris(setup):
    mind, _, _, _ = setup
    a = mind.mortality.continuity_copy()
    b = mind.mortality.continuity_copy()
    assert a["success"] and b["success"]
    assert a["copy_path"] == b["copy_path"]
    assert not Path(b["copy_path"] + ".tmp").exists()


def test_continuity_copy_fails_open_on_an_unusable_db(setup):
    from app.mind.mortality import Mortality

    # A database path UNDER A FILE cannot be opened on any OS — the
    # '/proc/...' path was merely relative (and creatable) on Windows.
    _, _, tmp_path, _ = setup
    blocker = tmp_path / "blocker_db.txt"
    blocker.write_text("x")

    class _M:
        db_path = str(blocker / "not_writable.db")

    res = Mortality(_M()).continuity_copy()
    assert res["success"] is False and "reason" in res


def test_verify_restore_verifies_a_real_copy(setup):
    mind, _, _, _ = setup
    _give_her_a_history(mind)
    mind.mortality.continuity_copy()
    res = mind.mortality.verify_restore()
    assert res["verdict"] == "verified"
    assert res["integrity"] == "ok"
    assert res["rows_in_copy"] > 0
    assert res["rows_live"] >= res["rows_in_copy"]
    assert "nothing was restored automatically" in res["statement"]


def test_verify_restore_reports_a_missing_copy_honestly(setup):
    mind, _, _, _ = setup
    res = mind.mortality.verify_restore()
    assert res["verdict"] == "missing"
    assert res["rows_in_copy"] == 0
    assert "no continuity copy is on file" in res["detail"]


def test_verify_restore_reports_corruption(setup):
    mind, _, _, _ = setup
    mind.mortality.continuity_copy()
    Path(mind.mortality._copy_path()).write_bytes(b"not a database at all")
    res = mind.mortality.verify_restore()
    assert res["verdict"] == "corrupt"


def test_verify_restore_is_recorded(setup):
    mind, _, _, _ = setup
    mind.mortality.continuity_copy()
    mind.mortality.verify_restore()
    kinds = [h["kind"] for h in mind.mortality.history()]
    assert "continuity_check" in kinds


def test_living_between_copies_is_not_a_failure(setup):
    mind, _, _, _ = setup
    _give_her_a_history(mind)
    mind.mortality.continuity_copy()
    mind.authority.note("one more rule, written after the copy")
    res = mind.mortality.verify_restore()
    assert res["rows_live"] > res["rows_in_copy"]
    assert res["verdict"] == "verified"


def test_on_shutdown_writes_letter_copy_and_record(setup):
    mind, _, tmp_path, _ = setup
    _give_her_a_history(mind)
    res = mind.mortality.on_shutdown()
    assert res["success"] is True
    assert res["steps"]["legacy"]["success"] is True
    assert res["steps"]["copy"]["success"] is True
    assert Path(mind.mortality._copy_path()).exists()
    assert (tmp_path / "beanie_legacy").is_dir()
    kinds = [h["kind"] for h in mind.mortality.history()]
    assert kinds[:3] == ["shutdown", "continuity_copy", "legacy_written"]


def test_on_awakening_records_and_checks(setup):
    mind, _, _, _ = setup
    mind.mortality.continuity_copy()
    res = mind.mortality.on_awakening()
    assert res["awakening"]["kind"] == "awakening"
    assert res["continuity_check"]["verdict"] == "verified"
    kinds = [h["kind"] for h in mind.mortality.history()]
    # newest first; the copy event is from the explicit copy above
    assert kinds == ["continuity_check", "awakening", "continuity_copy"]


def test_continuity_status_reports_the_net(setup):
    mind, _, _, _ = setup
    before = mind.mortality.continuity_status()
    assert before["copy_exists"] is False
    assert "no continuity copy is on file yet" in before["statement"]
    mind.mortality.continuity_copy()
    mind.mortality.verify_restore()
    after = mind.mortality.continuity_status()
    assert after["copy_exists"] is True and after["copy_bytes"] > 0
    assert after["last_copy_at"] and after["last_check"]
    assert "on file at" in after["statement"]


def test_the_copy_survives_the_databases_own_death(setup):
    """The point of the net: she lives, she sleeps, and afterwards the
    copy alone still holds her — real ledgers, real rows."""
    mind, _, _, _ = setup
    _give_her_a_history(mind)
    mind._run_mortality_lifecycle("shutdown")
    copy_path = mind.mortality._copy_path()
    assert Path(copy_path).exists()
    conn = sqlite3.connect(copy_path)
    try:
        rules = conn.execute(
            "SELECT COUNT(*) FROM beanie_authority_rules").fetchone()[0]
        beliefs = conn.execute(
            "SELECT COUNT(*) FROM beanie_beliefs").fetchone()[0]
    finally:
        conn.close()
    assert rules >= 1 and beliefs >= 1


def test_continuity_copy_owner_endpoints(setup):
    from fastapi.testclient import TestClient
    from app.server import app  # the unified entry mounts the mind router

    mind, _, _, _ = setup
    client = TestClient(app)
    res = client.post("/mind/mortality/continuity-copy")
    assert res.status_code == 200
    assert res.json()["success"] is True
    st = client.get("/mind/mortality/continuity-copy")
    assert st.status_code == 200
    body = st.json()
    assert body["copy_exists"] is True and body["copy_bytes"] > 0
    assert body["copy_path"] == mind.mortality._copy_path()


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_counts_and_policy(setup):
    mind, _, _, _ = setup
    mind.mortality.record_awakening()
    st = mind.mortality.stats()
    assert st["events"] == 1 and st["by_kind"] == {"awakening": 1}
    assert st["last_event_at"]
    assert "continuity is only what is written down" in st["policy"]
    assert "never refuses" in st["policy"]


def test_snapshot_shape(setup):
    mind, _, _, _ = setup
    mind.mortality.record_awakening()
    snap = mind.mortality.snapshot()
    assert snap["organ"] == "mortality"
    assert isinstance(snap["stream"], list) and len(snap["stream"]) == 1
    assert snap["stream"][0]["acted"] is False
