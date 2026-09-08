"""Phase 15 (Beanie AGI roadmap) — motivation and goals.

needs, curiosity, unfinished goals, owner goals, environment opportunities,
learning opportunities → candidate goals → evaluate relevance → prioritize
→ propose. Contracts pinned here:
- goals come from EVIDENCE only — an empty mind yields zero goals (never
  randomly generated tasks);
- the six sources are real ledgers: open unknowns, parked goals, goal-shaped
  owner speech, attention's important-change/anomaly verdicts, verified
  failures, learned-rhythm anticipations;
- relevance is a sum of NAMED contributions (source base / recurrence /
  recency / task overlap) — inspectable, not vibes;
- repeated evidence compounds recurrence instead of duplicating goals;
- propose() builds the ask from the goal's own evidence and never acts
  (acted: False); declined goals are never re-proposed;
- the door refresh honors the kill switch and never fails the task.
"""

from __future__ import annotations

import pytest

from app.cognition.confidence_calibrator import ConfidenceCalibrator
from app.cognition.memory import MemoryStore
from app.mind import BeanieMind
from app.mind.motivation import AUTO_PROPOSE_COOLDOWN, AUTO_PROPOSE_SCORE


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
    # hermetic: parked goals live in the shared runtime db; in tests the
    # source is stubbed (its real path is exercised in its own test)
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    brain = _Brain(tmp_path)
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db", runtime=brain)
    yield mind, brain, monkeypatch
    BeanieMind.reset_instance()


def test_parked_goals_are_unfinished_goal_candidates(setup):
    mind, _, monkeypatch = setup
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [{"trace_id": "t1", "conversation_id": "c",
                          "goal": "send the weekly digest",
                          "created_at": "2026-09-08T10:00:00+00:00"}])
    mind.motivation.gather()
    unfinished = [g for g in mind.motivation.prioritize()
                  if g["source"] == "unfinished_goal"]
    assert unfinished and unfinished[0]["title"] == "send the weekly digest"
    assert "waiting for evidence" in unfinished[0]["evidence"]


# ── goals from evidence only ────────────────────────────────────────────────
def test_empty_mind_has_no_goals(setup):
    mind, _, _ = setup
    assert mind.motivation.gather() == []
    assert mind.motivation.prioritize() == []
    bad = mind.motivation.propose()
    assert bad["success"] is False and "nothing honest" in bad["reason"]


def test_curiosity_unknowns_become_candidates(setup):
    mind, _, _ = setup
    mind.curiosity.register("why the printer drops offline", source="test")
    mind.curiosity.register("why the printer drops offline", source="test")
    mind.motivation.gather()
    ranked = mind.motivation.prioritize()
    assert len(ranked) == 1  # recurrence compounds, no duplicate goal
    goal = ranked[0]
    assert goal["source"] == "curiosity"
    assert goal["recurrence"] == 2
    assert "encountered 2" in goal["evidence"]


def test_owner_goal_speech_is_recognized(setup):
    mind, _, _ = setup
    # owner speech enters through the door; goal-shaped phrasing is picked up
    mind.process("I want you to organize the project files", modality="text")
    mind.motivation.gather()
    ranked = mind.motivation.prioritize()
    sources = {g["source"] for g in ranked}
    assert "owner_goal" in sources
    goal = next(g for g in ranked if g["source"] == "owner_goal")
    assert "organize the project files" in goal["title"]
    assert "owner said" in goal["evidence"]


def test_attention_verdicts_become_environment_goals(setup):
    mind, _, _ = setup
    mind.perception.perceive(
        "environment", "the build server crashed and is now offline", urgent=True)
    mind.attention.review(task="writing code")
    mind.motivation.gather()
    env = [g for g in mind.motivation.prioritize() if g["source"] == "environment"]
    assert env and "attention verdict: important_change" in env[0]["evidence"]


def test_verified_failures_become_learning_goals(setup):
    mind, _, _ = setup
    mind.learn({"kind": "action", "content": "export the csv report",
                "source": "cycle:text", "success": False})
    mind.motivation.gather()
    learning = [g for g in mind.motivation.prioritize() if g["source"] == "learning"]
    assert learning and "verified false" in learning[0]["evidence"]
    # unverified (success=None) is NOT a learning opportunity — honesty
    mind.learn({"kind": "action", "content": "another task maybe",
                "source": "cycle:text", "success": None})
    mind.motivation.gather()
    titles = [g["title"] for g in mind.motivation.prioritize()
              if g["source"] == "learning"]
    assert all("another task maybe" not in t for t in titles)


# ── relevance is named contributions ────────────────────────────────────────
def test_relevance_reasons_are_named(setup):
    mind, _, _ = setup
    mind.curiosity.register("why backups fail at night", source="test")
    mind.curiosity.register("why backups fail at night", source="test")
    mind.motivation.gather()
    goal = mind.motivation.prioritize()[0]
    assert any("base" in r for r in goal["reasons"])
    assert any("recurrence" in r for r in goal["reasons"])
    assert any("recent" in r for r in goal["reasons"])
    assert goal["score"] > 3.0


def test_task_overlap_boosts_relevance(setup):
    mind, _, _ = setup
    base, why_plain = mind.motivation.evaluate(
        "environment", "the printer spooler restarted", 1, None, task="")
    boosted, why_task = mind.motivation.evaluate(
        "environment", "the printer spooler restarted", 1, None,
        task="fix the printer spooler")
    assert boosted == base + 1.0
    assert any("current task" in r for r in why_task)


def test_prioritize_orders_by_score(setup):
    mind, _, _ = setup
    mind.curiosity.register("mild open question", source="test")
    mind.curiosity.register("burning recurring mystery", source="test")
    mind.curiosity.register("burning recurring mystery", source="test")
    mind.curiosity.register("burning recurring mystery", source="test")
    mind.motivation.gather()
    ranked = mind.motivation.prioritize()
    assert ranked[0]["title"] == "burning recurring mystery"
    scores = [g["score"] for g in ranked]
    assert scores == sorted(scores, reverse=True)


# ── propose / decide ────────────────────────────────────────────────────────
def test_propose_builds_the_ask_from_evidence_and_never_acts(setup):
    mind, _, _ = setup
    mind.process("please remind me to file the invoices", modality="text")
    mind.motivation.gather()
    goal = next(g for g in mind.motivation.prioritize()
                if g["source"] == "owner_goal")
    res = mind.motivation.propose(goal["goal_id"])
    assert res["success"] is True and res["acted"] is False
    assert res["epistemic_kind"] == "goal_proposal"
    assert "file the invoices" in res["ask"]
    # proposing twice returns the existing proposal — no duplicate asks
    again = mind.motivation.propose(goal["goal_id"])
    assert again.get("already_proposed") is True


def test_declined_goals_are_never_reproposed(setup):
    mind, _, _ = setup
    mind.curiosity.register("what eats the disk space", source="test")
    mind.motivation.gather()
    goal = mind.motivation.prioritize()[0]
    res = mind.motivation.decide(goal["goal_id"], accept=False)
    assert res["success"] is True and res["status"] == "declined"
    assert "never" in res["note"].lower() or "not" in res["note"].lower()
    assert mind.motivation.prioritize() == []  # declined leaves the queue
    fresh = mind.motivation.propose()
    assert fresh["success"] is False  # nothing honest left to ask


def test_accepted_goal_stays_on_the_books_without_acting(setup):
    mind, _, _ = setup
    mind.curiosity.register("why the sync job stalls", source="test")
    mind.motivation.gather()
    goal = mind.motivation.prioritize()[0]
    res = mind.motivation.decide(goal["goal_id"], accept=True)
    assert res["status"] == "accepted" and res["acted"] is False
    assert "normal door" in res["note"]
    stored = next(g for g in mind.motivation.goals()
                  if g["goal_id"] == goal["goal_id"])
    assert stored["status"] == "accepted"


# ── the door: refresh, auto-proposal guard, kill switch ─────────────────────
def test_refresh_auto_proposes_only_when_earned_and_cooled(setup):
    mind, _, _ = setup
    # a strong candidate: recurring unknown + recent evidence
    for _ in range(4):
        mind.curiosity.register("why the nightly backup fails", source="test")
    r1 = mind.motivation.refresh(task="check the backup")
    top = mind.motivation.prioritize()[0]
    assert top["score"] >= AUTO_PROPOSE_SCORE
    assert r1["proposed"] is True and r1["proposal"]["acted"] is False
    # gather again, refresh immediately: cooldown blocks a second proposal
    r2 = mind.motivation.refresh(task="check the backup")
    assert r2["proposed"] is False
    # after the cooldown, an already-proposed goal is not re-proposed either
    mind.motivation._interactions += AUTO_PROPOSE_COOLDOWN
    r3 = mind.motivation.refresh(task="check the backup")
    assert r3["proposed"] is False


def test_door_process_runs_motivation_and_kill_switch_stops_it(setup):
    mind, _, monkeypatch = setup
    mind.curiosity.register("why reports render slowly", source="test")
    mind.process("summarize my week", modality="text")
    assert mind.motivation.stats()["goals"] >= 1
    assert mind.motivation._interactions >= 1  # the door ran refresh

    from app.config import settings
    from pathlib import Path
    db_path = Path(mind.db_path)
    tmp_root = db_path.parent
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_MOTIVATION", "0")
    mind2 = BeanieMind.get_instance(db_path=db_path, runtime=_Brain(tmp_root))
    mind2.process("summarize my week again", modality="text")
    assert mind2.motivation._interactions == 0  # refresh never ran
    monkeypatch.setattr(settings, "ARENA_MOTIVATION", "1")
    BeanieMind.reset_instance()


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_goals_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    mind.curiosity.register("why the kettle wifi drops", source="test")
    mind.motivation.refresh()
    page = client.get("/mind/goals")
    assert page.status_code == 200
    payload = page.json()
    assert payload["success"] is True and payload["goals"] >= 1
    assert payload["prioritized"][0]["source"] == "curiosity"

    propose = client.post(
        "/mind/goals/propose",
        params={"goal_id": payload["prioritized"][0]["goal_id"]})
    assert propose.status_code == 200
    body = propose.json()
    assert body["acted"] is False and "kettle wifi" in body["ask"]

    decide = client.post("/mind/goals/decide",
                         params={"goal_id": body["goal_id"], "accept": False})
    assert decide.status_code == 200 and decide.json()["status"] == "declined"
