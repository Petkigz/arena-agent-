"""Phase 18 (Beanie AGI roadmap) — owner authority.

"Not arbitrary system morals. Not random hard-coded restrictions."
Charter §2 (ask, never refuse) contracts pinned here:
- rules come ONLY from the owner's statements (plus Phase-16 boundaries);
- five lanes: always_allowed / ask_first / never_do / trusted_context /
  temporary, with never-lane strongest;
- risk patterns decide WHEN TO ASK — never a silent drop, never a bare
  refusal; the default is to ask (asking is never refusing);
- ask-first opens a TYPED requires_owner_approval ask with a real reason;
- the owner's answer is obeyed; a declined ask is the owner's decision;
- authority ≠ intelligence: judging authorization executes nothing
  (acted: False on every verdict);
- repeated rules compound, never duplicate.
"""

from __future__ import annotations

import pytest

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

    def process_cognitive_cycle(self, user_text, **kwargs):
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


# ── the default is to ask, never to refuse ──────────────────────────────────
def test_unruled_action_defaults_to_asking_not_refusing(setup):
    mind, _, _ = setup
    v = mind.authority.check("water the plants")
    assert v["success"] is True and v["acted"] is False
    assert v["lane"] == "ask_first"
    assert any("asking is never refusing" in r for r in v["reasons"])
    assert v["ask"]["requires_owner_approval"] is True
    assert v["ask"]["ask_id"] is not None


def test_risky_action_asks_with_the_risk_named(setup):
    mind, _, _ = setup
    v = mind.authority.check("delete the old downloads folder")
    assert v["lane"] == "ask_first"
    assert any("risk pattern" in r and "delete" in r for r in v["reasons"])
    assert "refus" not in " ".join(v["reasons"]).lower()  # no refusal framing


def test_high_safety_level_asks(setup):
    mind, _, _ = setup
    v = mind.authority.check("run the report exporter", safety_level=4)
    assert v["lane"] == "ask_first"
    assert any("safety level" in r for r in v["reasons"])


# ── owner rules set the lanes ───────────────────────────────────────────────
def test_never_rule_is_quoted_back_not_refused(setup):
    mind, _, _ = setup
    rules = mind.authority.note("Never delete my photos")
    assert rules and rules[0]["lane"] == "never_do"
    v = mind.authority.check("delete my photos from last year")
    assert v["lane"] == "never_do"
    assert any("Never delete my photos" in r for r in v["reasons"])
    assert "authority ≠ intelligence" in v["note"]
    assert v["acted"] is False


def test_always_rule_authorizes(setup):
    mind, _, _ = setup
    mind.authority.note("You can always send me the daily summary")
    v = mind.authority.check("send the daily summary")
    assert v["lane"] == "always_allowed"
    assert v["ask"] is None  # no ask needed — the owner already decided


def test_ask_first_rule_opens_an_ask_with_evidence(setup):
    mind, _, _ = setup
    mind.authority.note("Ask before installing anything")
    v = mind.authority.check("install the new update")
    assert v["lane"] == "ask_first"
    assert any("Ask before installing" in r for r in v["reasons"])
    assert v["ask"]["requires_owner_approval"] is True


def test_trusted_context_rule_depends_on_context(setup):
    mind, _, _ = setup
    mind.authority.note("When working on reports you can export any file")
    in_ctx = mind.authority.check("export the csv file",
                                  context="working on reports")
    assert in_ctx["lane"] == "trusted_context"
    out_ctx = mind.authority.check("export the csv file", context="")
    assert out_ctx["lane"] != "trusted_context"  # falls back to asking


def test_temporary_rule_is_its_own_lane(setup):
    mind, _, _ = setup
    mind.authority.note("Just for today you may restart the server")
    v = mind.authority.check("restart the server")
    assert v["lane"] == "temporary"


def test_never_lane_beats_always_lane(setup):
    mind, _, _ = setup
    mind.authority.note("You can always send messages")
    mind.authority.note("Never send messages to the all-staff list")
    v = mind.authority.check("send a message to the all-staff list")
    assert v["lane"] == "never_do"


def test_repeated_rule_compounds_not_duplicates(setup):
    mind, _, _ = setup
    mind.authority.note("Never touch the backup drive")
    mind.authority.note("Never touch the backup drive")
    never = [r for r in mind.authority.rules() if r["lane"] == "never_do"]
    matching = [r for r in never if "backup drive" in r["scope"]]
    assert len(matching) == 1 and matching[0]["times_stated"] == 2


# ── phase-16 boundaries become never rules ──────────────────────────────────
def test_phase16_boundary_seeds_the_never_lane(setup):
    mind, _, _ = setup
    mind.social.note("Never delete anything from my desktop")
    v = mind.authority.check("delete a file from my desktop")
    assert v["lane"] == "never_do"
    rule = next(r for r in mind.authority.rules()
                if r["source"] == "phase16_boundary")
    assert "desktop" in rule["scope"].lower()


# ── asks are answered and obeyed ────────────────────────────────────────────
def test_answer_allow_and_decline_are_obeyed(setup):
    mind, _, _ = setup
    v = mind.authority.check("delete the cache")
    ask_id = v["ask"]["ask_id"]
    ok = mind.authority.answer(ask_id, allow=True)
    assert ok["success"] is True and ok["status"] == "allowed"
    assert "obeyed" in ok["answer"] and ok["acted"] is False
    # answering again reports the existing answer, never re-decides
    again = mind.authority.answer(ask_id, allow=False)
    assert again.get("already_answered") is True and again["status"] == "allowed"

    v2 = mind.authority.check("delete the logs")
    no = mind.authority.answer(v2["ask"]["ask_id"], allow=False)
    assert no["status"] == "declined"
    assert "owner's decision" in no["answer"]


def test_answer_unknown_ask_fails_honestly(setup):
    mind, _, _ = setup
    res = mind.authority.answer(9999, allow=True)
    assert res["success"] is False and "no ask" in res["reason"]


# ── the door + kill switch + policy surface ─────────────────────────────────
def test_door_hears_authority_rules(setup):
    mind, _, _ = setup
    mind.process("Never rename my files without asking", modality="text")
    lanes = mind.authority.policy()["lane_counts"]
    assert lanes["never_do"] >= 1


def test_kill_switch_stops_rule_extraction(setup):
    mind, _, monkeypatch = setup
    from app.config import settings
    from pathlib import Path
    db_path = Path(mind.db_path)
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_AUTHORITY", "0")
    mind2 = BeanieMind.get_instance(db_path=db_path, runtime=_Brain(db_path.parent))
    mind2.process("never empty the trash automatically", modality="text")
    assert mind2.authority.policy()["lane_counts"]["never_do"] == 0
    BeanieMind.reset_instance()


def test_policy_shows_five_lanes_and_pending_asks(setup):
    mind, _, _ = setup
    mind.authority.check("delete something risky")
    p = mind.authority.policy()
    assert set(p["lanes"].keys()) == {"always_allowed", "ask_first",
                                      "never_do", "trusted_context",
                                      "temporary"}
    assert len(p["pending_asks"]) == 1
    assert "never refusing" in p["policy"]


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_authority_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    mind.authority.note("You can always open the calendar")
    chk = client.post("/mind/authority/check",
                      json={"action": "open the calendar"})
    assert chk.status_code == 200
    assert chk.json()["lane"] == "always_allowed"

    chk2 = client.post("/mind/authority/check",
                       json={"action": "format the usb stick"})
    ask_id = chk2.json()["ask"]["ask_id"]
    assert chk2.json()["lane"] == "ask_first" and ask_id is not None

    ans = client.post("/mind/authority/answer",
                      json={"ask_id": ask_id, "allow": False})
    assert ans.status_code == 200 and ans.json()["status"] == "declined"

    page = client.get("/mind/authority")
    assert page.status_code == 200
    payload = page.json()
    assert payload["success"] is True
    assert payload["lane_counts"]["always_allowed"] >= 1
    assert payload["pending_asks"] == []  # the only ask was answered
