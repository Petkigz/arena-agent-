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
- the lifecycle records the sleepings and the wakings; the kill
  switch leaves the organ unconstructed.
"""

from __future__ import annotations

import json

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
    mind, _, _, _ = setup
    res = mind.mortality.legacy("/proc/definitely/not/writable")
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
    mind, _, _, _ = setup
    mind._run_mortality_lifecycle("awakening")
    mind._run_mortality_lifecycle("shutdown")
    kinds = [h["kind"] for h in mind.mortality.history()]
    assert kinds == ["shutdown", "awakening"]


def test_kill_switch_leaves_the_organ_unconstructed(setup):
    mind, _, _, monkeypatch = setup
    monkeypatch.setattr(settings, "ARENA_MORTALITY", "0")
    mind._run_mortality_lifecycle("shutdown")
    assert mind._mortality is None, \
        "the kill switch leaves the organ unbuilt"


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
