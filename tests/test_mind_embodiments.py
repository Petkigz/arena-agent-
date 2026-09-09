"""Phase 23 (Beanie AGI roadmap) — desktop + Android as embodiments.

"Both are clients of the same Mind. Not two separate assistants."
Contracts pinned here:
- bodies come from a FIXED vocabulary (desktop/android/web) — unknown
  kinds are refused, never invented;
- aliveness is DERIVED from heartbeats against a TTL — never assumed;
- one mind, one message: the SAME presence event goes to every alive
  body; silent bodies are skipped honestly, deliveries never faked;
- bodies pull their queue and acknowledge delivery themselves;
- execution provenance names WHICH body's hands acted — hands, never
  brains;
- the door broadcasts the settled presence state to alive bodies after
  a verified cycle.
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


# ── the vocabulary is fixed; bodies are never invented ──────────────────────
def test_unknown_body_kinds_are_refused(setup):
    mind, _, _ = setup
    res = mind.embodiments.announce("toaster", "kitchen")
    assert res["success"] is False and "never invented" in res["reason"]
    assert mind.embodiments.bodies() == []


def test_announce_registers_a_body_of_the_one_mind(setup):
    mind, _, _ = setup
    res = mind.embodiments.announce("desktop", "owner-desktop",
                                    capabilities=["screen", "audio"])
    assert res["success"] is True and res["body_id"] >= 1
    assert "ONE" in res["statement"] and "not a separate assistant" in res["statement"]
    bodies = mind.embodiments.bodies()
    assert len(bodies) == 1 and bodies[0]["state"] == "active"
    assert bodies[0]["capabilities"] == ["audio", "screen"]


def test_reannounce_updates_not_duplicates(setup):
    mind, _, _ = setup
    first = mind.embodiments.announce("android", "owner-phone")
    second = mind.embodiments.announce("android", "owner-phone")
    assert first["body_id"] == second["body_id"]
    assert second["reannounced"] is True
    assert len(mind.embodiments.bodies()) == 1


# ── aliveness is derived from heartbeats ────────────────────────────────────
def test_heartbeat_refreshes_and_unknown_beats_nothing(setup):
    mind, _, _ = setup
    bid = mind.embodiments.announce("desktop", "owner-desktop")["body_id"]
    beat = mind.embodiments.heartbeat(bid)
    assert beat["success"] is True and beat["state"] == "active"
    lost = mind.embodiments.heartbeat(999)
    assert lost["success"] is False and "nothing beats" in lost["reason"]


def test_silence_is_derived_never_assumed(setup, monkeypatch):
    mind, _, _ = setup
    bid = mind.embodiments.announce("desktop", "owner-desktop")["body_id"]
    assert mind.embodiments.alive(), "freshly announced body beats"
    # the window closes: the same body is now silent
    monkeypatch.setattr("app.mind.embodiments.BODY_TTL_S", -1.0)
    bodies = mind.embodiments.bodies()
    assert bodies[0]["state"] == "silent" and bodies[0]["body_id"] == bid
    assert mind.embodiments.alive() == []
    # a heartbeat brings it back
    monkeypatch.setattr("app.mind.embodiments.BODY_TTL_S", 60.0)
    mind.embodiments.heartbeat(bid)
    assert len(mind.embodiments.alive()) == 1


# ── one mind, one message ───────────────────────────────────────────────────
def test_broadcast_reaches_every_alive_body_identically(setup):
    mind, _, _ = setup
    d = mind.embodiments.announce("desktop", "owner-desktop")["body_id"]
    a = mind.embodiments.announce("android", "owner-phone")["body_id"]
    res = mind.embodiments.broadcast_presence("success", detail="verified")
    assert res["success"] is True and res["acted"] is True
    assert len(res["planned"]) == 2 and res["skipped"] == []
    payloads = []
    for bid in (d, a):
        events = mind.embodiments.events(bid)
        assert len(events) == 1
        payloads.append(events[0]["payload"])
    assert payloads[0] == payloads[1], "the same words to every body"
    assert payloads[0]["state"] == "success"


def test_broadcast_skips_silent_bodies_honestly(setup, monkeypatch):
    mind, _, _ = setup
    mind.embodiments.announce("desktop", "owner-desktop")
    alive = mind.embodiments.announce("android", "owner-phone")["body_id"]
    # make the desktop silent by closing its window selectively: rewind
    # only its last_seen
    import sqlite3
    with sqlite3.connect(mind.embodiments.db_path) as conn:
        conn.execute("UPDATE beanie_bodies SET last_seen='2000-01-01T00:00:00+00:00'"
                     " WHERE kind='desktop'")
        conn.commit()
    res = mind.embodiments.broadcast_presence("speaking")
    assert len(res["planned"]) == 1
    assert len(res["skipped"]) == 1 and "silent" in res["skipped"][0]["reason"]
    assert mind.embodiments.events(alive)


def test_broadcast_with_no_bodies_is_an_honest_noop(setup):
    mind, _, _ = setup
    res = mind.embodiments.broadcast_presence("idle")
    assert res["success"] is True and res["acted"] is False
    assert res["planned"] == [] and "nothing was faked" in res["statement"]


# ── pull queue + acknowledgement ────────────────────────────────────────────
def test_acknowledge_is_the_bodys_own_word(setup):
    mind, _, _ = setup
    bid = mind.embodiments.announce("desktop", "owner-desktop")["body_id"]
    mind.embodiments.broadcast_presence("thinking")
    event = mind.embodiments.events(bid)[0]
    ack = mind.embodiments.acknowledge(bid, event["event_id"])
    assert ack["success"] is True and "body itself" in ack["statement"]
    assert mind.embodiments.events(bid) == [], "acknowledged leaves the queue"
    assert len(mind.embodiments.events(bid, include_acknowledged=True)) == 1
    foreign = mind.embodiments.acknowledge(999, event["event_id"])
    assert foreign["success"] is False and "never queued" in foreign["reason"]


# ── provenance: hands, never brains ─────────────────────────────────────────
def test_execution_provenance_names_the_body(setup):
    mind, _, _ = setup
    bid = mind.embodiments.announce("android", "owner-phone")["body_id"]
    res = mind.embodiments.note_execution(bid, "opened the camera app")
    assert res["success"] is True
    assert "hands, never brains" in res["statement"]
    events = mind.embodiments.events(bid)
    assert events[0]["kind"] == "execution"
    assert events[0]["payload"]["body"] == "owner-phone"
    ghost = mind.embodiments.note_execution(4242, "something")
    assert ghost["success"] is False and "known body" in ghost["reason"]


# ── the door: background presence for every alive body ──────────────────────
class _VerifyingBrain(_Brain):
    def __init__(self, tmp_path, verified):
        super().__init__(tmp_path)
        self._verified = verified

    def process_cognitive_cycle(self, user_text, **kwargs):
        return {"success": True, "assistant_reply": "ok",
                "goal_verified": self._verified,
                "goal_lifecycle_state": "completed"}


def test_door_broadcasts_to_alive_bodies(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    BeanieMind.reset_instance()
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path, True))
    d = mind.embodiments.announce("desktop", "owner-desktop")["body_id"]
    a = mind.embodiments.announce("android", "owner-phone")["body_id"]
    mind.process("file the invoices", modality="text")
    for bid in (d, a):
        events = mind.embodiments.events(bid)
        assert len(events) == 1, "both bodies hear the same mind"
        assert events[0]["payload"]["state"] == "success"
    BeanieMind.reset_instance()


def test_kill_switch_stops_the_broadcast(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tools.manifest.get_tool_manifest", lambda: {})
    monkeypatch.setattr(
        "app.cognition.parked_goal_recheck.collect_parked_goals",
        lambda limit=5: [])
    from app.config import settings
    BeanieMind.reset_instance()
    monkeypatch.setattr(settings, "ARENA_EMBODIMENTS", "0")
    mind = BeanieMind.get_instance(db_path=tmp_path / "arena.db",
                                   runtime=_VerifyingBrain(tmp_path, True))
    bid = mind.embodiments.announce("desktop", "owner-desktop")["body_id"]
    mind.process("file the invoices", modality="text")
    assert mind.embodiments.events(bid) == []
    BeanieMind.reset_instance()


# ── surfaces ────────────────────────────────────────────────────────────────
def test_stats_and_snapshot(setup):
    mind, _, _ = setup
    mind.embodiments.announce("desktop", "owner-desktop")
    mind.embodiments.announce("android", "owner-phone")
    stats = mind.embodiments.stats()
    assert stats["bodies"] == 2 and stats["alive"] == 2
    assert stats["by_kind"]["desktop"] == 1 and stats["by_kind"]["android"] == 1
    assert "SAME mind" in stats["policy"]
    snap = mind.embodiments.snapshot()
    assert snap["organ"] == "embodiments" and len(snap["bodies"]) == 2


# ── owner surface ───────────────────────────────────────────────────────────
def test_api_embodiments_contract(setup):
    mind, _, _ = setup
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.mind import router as mind_router

    app = FastAPI()
    app.include_router(mind_router)
    client = TestClient(app)

    ann = client.post("/mind/embodiments/announce",
                      json={"kind": "android", "name": "owner-phone",
                            "capabilities": ["notify"]})
    assert ann.status_code == 200
    bid = ann.json()["body_id"]

    bad = client.post("/mind/embodiments/announce",
                      json={"kind": "fridge", "name": "kitchen"})
    assert bad.json()["success"] is False

    beat = client.post("/mind/embodiments/heartbeat", json={"body_id": bid})
    assert beat.json()["state"] == "active"

    mind.embodiments.broadcast_presence("listening")
    events = client.get(f"/mind/embodiments/events?body_id={bid}").json()
    assert events["success"] is True and len(events["events"]) == 1
    eid = events["events"][0]["event_id"]

    ack = client.post("/mind/embodiments/acknowledge",
                      json={"body_id": bid, "event_id": eid})
    assert ack.json()["success"] is True

    ex = client.post("/mind/embodiments/execution",
                     json={"body_id": bid, "action": "showed a notification"})
    assert "hands, never brains" in ex.json()["statement"]

    page = client.get("/mind/embodiments")
    payload = page.json()
    assert payload["success"] is True and payload["bodies"] == 1
    assert payload["alive"] == 1 and len(payload["stream"]) == 1
