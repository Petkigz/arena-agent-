"""Phase 17 (Beanie AGI roadmap) — personality development.

"Don't hard-code the personality forever. Start with a basic identity.
Then: interactions → experiences → preferences → communication patterns →
values learned from owner → personality development." Contracts pinned:
- the profile is DERIVED from her real ledgers — an empty life yields the
  basic identity and the honest statement that no traits formed yet;
- traits carry evidence and observation counts; no trait without evidence;
- her own replies are sampled at the door; reply style needs >=5 samples,
  an early-vs-late trend needs >=10;
- values come ONLY from the owner's explicit statements (owner's values
  only — never system morals);
- derive() snapshots and diffs: changes() is the verifiable record of
  'Beanie has changed';
- describing herself performs nothing (acted: False).
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
        return {"success": True, "assistant_reply": "Understood — noted."}


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


# ── basic identity first, nothing invented ──────────────────────────────────
def test_empty_life_is_basic_identity_only(setup):
    mind, _, _ = setup
    res = mind.personality.derive()
    assert res["success"] is True and res["acted"] is False
    profile = res["profile"]
    assert profile["traits"] == {} and profile["trait_names"] == []
    assert profile["identity"].get("name") == "Beanie"
    assert res["changed"] is False  # first snapshot — nothing to compare


def test_unmarked_speech_yields_no_values(setup):
    mind, _, _ = setup
    assert mind.personality.note("what's the weather") == []
    assert mind.personality.values() == []


# ── values: the owner's values only ─────────────────────────────────────────
def test_owner_value_statements_become_values(setup):
    mind, _, _ = setup
    found = mind.personality.note("It's important to me that you're always honest")
    assert len(found) == 1 and found[0]["facet"] == "value"
    again = mind.personality.note("seriously, honesty is what matters to me most")
    assert again and again[0]["times_heard"] >= 1
    vals = mind.personality.values()
    assert vals and all(v["times_heard"] >= 1 for v in vals)


def test_values_form_a_trait(setup):
    mind, _, _ = setup
    mind.personality.note("I value privacy — privacy matters to me")
    profile = mind.personality.derive()["profile"]
    assert "values_from_owner" in profile["traits"]
    trait = profile["traits"]["values_from_owner"]
    assert trait["observations"] >= 1 and trait["evidence"]


# ── her own communication pattern ───────────────────────────────────────────
def test_reply_pattern_needs_enough_samples(setup):
    mind, _, _ = setup
    for i in range(4):
        mind.personality.record_reply(f"reply number {i}")
    assert mind.personality.communication_patterns()["known"] is False
    mind.personality.record_reply("reply number five")
    p = mind.personality.communication_patterns()
    assert p["known"] is True and p["measured"] == 5
    assert p["summary"] in ("terse", "conversational", "expansive")


def test_reply_trend_measured_when_enough_history(setup):
    mind, _, _ = setup
    for i in range(6):
        mind.personality.record_reply("short")
    for i in range(6):
        mind.personality.record_reply("a considerably longer answer " * 8)
    p = mind.personality.communication_patterns()
    assert p.get("trend") == "lengthening" and p["trend_drift"] > 0.15
    profile = mind.personality.derive()["profile"]
    assert "communication_pattern" in profile["traits"]


def test_empty_reply_is_not_sampled(setup):
    mind, _, _ = setup
    assert mind.personality.record_reply("") is None
    assert mind.personality.record_reply(None) is None


# ── traits from her real ledgers ────────────────────────────────────────────
def test_experience_trait_forms_from_the_learning_ledger(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "did a thing",
                "source": "cycle:text", "success": True})
    profile = mind.personality.derive()["profile"]
    assert "experience" in profile["traits"]
    assert profile["traits"]["experience"]["observations"] >= 1


def test_calibration_trait_forms_from_verified_reality(setup):
    mind, _, _ = setup
    ok = mind.imagination.compare("send_email", True, source="test")
    assert ok["success"] is True
    mind.imagination.compare("delete_file", False, source="test")
    profile = mind.personality.derive()["profile"]
    trait = profile["traits"].get("epistemic_calibration")
    assert trait is not None
    assert trait["evidence"]["confirmed"] >= 1 and trait["evidence"]["refuted"] >= 1


def test_curiosity_trait_forms_from_unknowns(setup):
    mind, _, _ = setup
    mind.curiosity.register("why the kettle wifi drops", source="test")
    profile = mind.personality.derive()["profile"]
    assert "curiosity_stance" in profile["traits"]


def test_adaptation_trait_forms_from_owner_style(setup):
    mind, _, _ = setup
    for i in range(12):
        mind._record_entry("text", None, "quick one please")
    profile = mind.personality.derive()["profile"]
    assert "adaptation" in profile["traits"]
    assert "terse" in profile["traits"]["adaptation"]["description"]


# ── 'Beanie has changed' — verifiable ───────────────────────────────────────
def test_changes_track_trait_formation(setup):
    mind, _, _ = setup
    first = mind.personality.derive()
    assert first["changed"] is False
    mind.learn({"kind": "action", "content": "did a thing",
                "source": "cycle:text", "success": True})
    second = mind.personality.derive()
    assert second["changed"] is True
    assert any("experience" in c for c in second["changes"])
    history = mind.personality.changes()
    assert history and any("trait formed: experience" in c
                           for entry in history for c in entry["changes"])
    # deriving again with no new evidence reports no change
    third = mind.personality.derive()
    assert third["changed"] is False


# ── the door + kill switch + state room ─────────────────────────────────────
def test_door_samples_her_reply_and_hears_values(setup):
    mind, _, _ = setup
    mind.process("It's important to me that you double-check before sending",
                 modality="text")
    assert mind.personality.values(), "value heard at the door"
    assert mind.personality.communication_patterns()["known"] is False
    for _ in range(5):
        mind.process("another task", modality="text")
    assert mind.personality.communication_patterns()["known"] is True


def test_kill_switch_stops_the_personality_pass(setup):
    mind, _, monkeypatch = setup
    from app.config import settings
    from pathlib import Path
    db_path = Path(mind.db_path)
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_PERSONALITY", "0")
    mind2 = BeanieMind.get_instance(db_path=db_path, runtime=_Brain(db_path.parent))
    mind2.process("honesty is what matters to me most", modality="text")
    assert mind2.personality.values() == []
    assert mind2.personality.communication_patterns()["known"] is False
    BeanieMind.reset_instance()


def test_self_room_gains_the_personality_surface(setup):
    mind, _, _ = setup
    mind.personality.note("never lie to me — always be honest")
    room = mind.state()["self"]
    assert room["status"] == "ok"
    assert room["data"]["identity"]["name"] == "Beanie"  # Phase-1 pin kept
    assert "values" in room["data"]["personality"]
    assert room["data"]["personality"]["values"]


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_personality_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    mind.personality.note("I care about keeping things simple")
    derive = client.post("/mind/personality/derive")
    assert derive.status_code == 200 and derive.json()["success"] is True

    page = client.get("/mind/personality")
    assert page.status_code == 200
    payload = page.json()
    assert payload["success"] is True
    assert payload["profile"]["identity"]["name"] == "Beanie"
    assert any(v["key"] for v in payload["values"])
    assert payload["profile"]["traits"].get("values_from_owner") is not None
