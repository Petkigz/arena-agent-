"""Phase 2 — authoritative world-model identity resolution (owner plan 2026-09-10).

Pins the owner's exit criteria:
  * app-name matching creates candidates with confidence and evidence;
  * ambiguity produces a focused selection question (never a guess);
  * apps can be referenced by stable identity ACROSS sessions;
  * stale data is not treated as current fact;
  * each world claim has a "why do you believe this?" evidence trail;
  * the launch executor resolves persistent targets BEFORE the inventory/
    fuzzy fallback, and fails open (legacy matcher) on any problem or when
    ARENA_APP_IDENTITY=0.
"""

from unittest.mock import patch

import pytest

from app.cognition.world_model import WorldModel
from app.mind.app_identity import (
    record_process_state,
    remember_app,
    resolve_app_target,
)


@pytest.fixture
def world(tmp_path):
    return WorldModel(db_path=str(tmp_path / "world.sqlite3"))


@pytest.fixture
def richst_world(world):
    """The owner's live case: 'richst' spoken for 'RichST TV', plus a
    genuinely confusable neighbour so ambiguity is reachable."""
    tv = world.upsert_entity(
        name="RichST TV", entity_type="application",
        attributes={"executable": "C:/Apps/RichST/RichSTTV.exe"})
    world.add_alias(tv.id, "richst tv", source="owner")
    world.add_alias(tv.id, "the tv app", source="owner")
    world.upsert_entity(name="RichST Radio", entity_type="application")
    world.upsert_entity(name="Rich Text Editor", entity_type="application")
    return world


# ── exit criterion 1: candidates with confidence + evidence ──────────────


class TestCandidates:
    def test_alias_hit_carries_confidence_and_evidence(self, richst_world):
        # 'the tv app' matches NO name — only the learned alias can hit.
        ranked = richst_world.resolve_candidates("the tv app", entity_type="application")
        assert ranked, "alias must produce a candidate"
        top = ranked[0]
        assert top["entity"].name == "RichST TV"
        assert top["confidence"] >= 0.9
        assert "alias" in top["evidence"].lower()
        assert top["matched_via"] == "alias"

    def test_exact_name_beats_fuzzy_neighbours(self, world):
        world.upsert_entity(name="Firefox", entity_type="application")
        world.upsert_entity(name="Firewall App", entity_type="application")
        ranked = world.resolve_candidates("firefox", entity_type="application")
        assert ranked[0]["entity"].name == "Firefox"
        # exact matches cap at 0.999 — certainty is never absolute
        assert ranked[0]["confidence"] >= 0.99
        assert "exact" in ranked[0]["evidence"]

    def test_competing_hypotheses_are_all_returned(self, richst_world):
        ranked = richst_world.resolve_candidates("richst", entity_type="application")
        names = [c["entity"].name for c in ranked]
        assert "RichST TV" in names and "RichST Radio" in names
        assert all(0.0 <= c["confidence"] <= 1.0 for c in ranked)
        assert all(c["evidence"] for c in ranked)

    def test_type_filter_is_honored(self, world):
        world.upsert_entity(name="Notepad", entity_type="application")
        world.upsert_entity(name="Notepad Notes", entity_type="concept")
        ranked = world.resolve_candidates("notepad", entity_type="application")
        assert [c["entity"].name for c in ranked] == ["Notepad"]


# ── exit criterion 2: ambiguity → focused selection question ─────────────


class TestAmbiguity:
    def test_tie_produces_focused_question(self, richst_world):
        verdict = resolve_app_target("richst", richst_world)
        assert verdict["status"] == "ambiguous"
        q = verdict["question"]
        assert "RichST TV" in q and "RichST Radio" in q
        assert "Which one did you mean?" in q
        # the word that types the park reason downstream (round-5 taxonomy)
        assert "ambiguous" in q.lower()

    def test_clear_winner_resolves(self, richst_world):
        verdict = resolve_app_target("richst tv", richst_world)
        assert verdict["status"] == "resolved"
        assert verdict["name"] == "RichST TV"
        assert verdict["confidence"] >= 0.9

    def test_ambiguous_question_parks_as_target_ambiguous(self, richst_world):
        from app.cognition.goal_lifecycle import (
            PARK_TARGET_AMBIGUOUS,
            classify_park_reason,
        )
        verdict = resolve_app_target("richst", richst_world)
        reason = classify_park_reason({"assistant_reply": verdict["question"]})
        assert reason == PARK_TARGET_AMBIGUOUS


# ── exit criterion 3: stable identity across sessions ────────────────────


class TestStableIdentity:
    def test_alias_binding_survives_a_new_session(self, tmp_path):
        db = str(tmp_path / "world.sqlite3")
        session_a = WorldModel(db_path=db)
        eid = remember_app("RichST TV", session_a,
                           executable="C:/Apps/RichST/RichSTTV.exe",
                           alias="richst")
        assert eid
        session_b = WorldModel(db_path=db)  # fresh process-like instance
        verdict = resolve_app_target("richst", session_b)
        assert verdict["status"] == "resolved"
        assert verdict["entity_id"] == eid
        assert verdict["name"] == "RichST TV"

    def test_remembered_app_is_findable_by_type(self, world):
        remember_app("VLC media player", world, source="app_inventory_scan")
        found = world.find_entities(entity_type="application")
        assert [e.name for e in found] == ["VLC media player"]


# ── exit criterion 4: stale data is never current fact ───────────────────


class TestFreshness:
    def test_old_process_state_is_not_current(self, world):
        from datetime import datetime, timedelta, timezone

        from app.cognition.world_model import Observation
        from uuid import uuid4
        remember_app("RichST TV", world)
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        world.observe(Observation(
            id=uuid4().hex, subject="RichST TV", predicate="process_state",
            value="running", source="psutil_scan", observed_at=old))
        status = world.entity_state_status("RichST TV", "process_state",
                                           max_age_hours=1.0)
        assert status["status"] == "stale"
        assert status["currently_unobserved"] is True

    def test_fresh_process_state_is_current(self, world):
        remember_app("RichST TV", world)
        assert record_process_state("RichST TV", True, world) is True
        status = world.entity_state_status("RichST TV", "process_state",
                                           max_age_hours=1.0)
        assert status["status"] == "current"
        assert status["value"] == "running"


# ── exit criterion 5: evidence trail ("why do you believe this?") ────────


class TestEvidenceTrail:
    def test_why_lists_sources_and_provenance(self, world):
        eid = remember_app("RichST TV", world,
                           executable="C:/Apps/RichST/RichSTTV.exe",
                           alias="richst", source="app_inventory_scan")
        record_process_state("RichST TV", True, world, source="psutil_scan")
        trail = world.why(eid)
        assert trail["known"] is True
        assert "richst" in trail["aliases"]
        preds = {e["predicate"]: e for e in trail["evidence"]}
        assert preds["installed"]["source"] == "app_inventory_scan"
        assert preds["process_state"]["source"] == "psutil_scan"
        assert preds["alias"]["source"] == "app_inventory_scan"
        assert all(e["observed_at"] for e in trail["evidence"])

    def test_why_is_honest_about_unknowns(self, world):
        assert world.why("nonexistent-id")["known"] is False


# ── the launch seam: persistent resolution before the fallback ───────────


def _proposal(app_name):
    from app.cognition.action_proposal import ActionProposal
    return ActionProposal(action_type="open_application",
                          payload={"app_name": app_name})


def _run_launch(world, app_name, inventory_result):
    """Run the real execute_proposal with the inventory + LLM stubbed."""
    from app.agents.master_agent import MasterAgentOrchestrator

    calls = []

    def fake_launch(query):
        calls.append(query)
        return dict(inventory_result)

    with patch("app.tools.app_inventory.SystemAppInventory.launch_any_app",
               side_effect=fake_launch), \
         patch("app.agents.master_agent.llm_client.generate_chat_completion",
               return_value={"error": "provider offline in test"}):
        result = MasterAgentOrchestrator.execute_proposal(
            _proposal(app_name), f"open {app_name}", world_model=world)
    return result, calls


class TestLaunchSeam:
    SUCCESS = {"success": True, "app_name": "RichST TV",
               "executable_path": "C:/Apps/RichST/RichSTTV.exe"}

    def test_spoken_form_resolves_to_canonical_before_inventory(self, richst_world):
        result, calls = _run_launch(richst_world, "richst tv", self.SUCCESS)
        # the inventory matcher received the CANONICAL name, not the guess
        assert calls == ["RichST TV"]
        assert "Launched application 'Richst Tv'" in " ".join(result.executed_actions)

    def test_launch_binds_the_spoken_alias_permanently(self, richst_world, tmp_path):
        fresh = WorldModel(db_path=str(tmp_path / "fresh.sqlite3"))
        eid = remember_app("Notepad++", fresh, executable="C:/npp.exe")
        res, calls = _run_launch(fresh, "notepad plus plus",
                                 {"success": True, "app_name": "Notepad++",
                                  "executable_path": "C:/npp.exe"})
        assert calls == ["notepad plus plus"]  # unknown → legacy matcher used the raw query
        # ...and the successful launch TAUGHT the binding:
        verdict = resolve_app_target("notepad plus plus", fresh)
        assert verdict["status"] == "resolved"
        assert verdict["entity_id"] == eid

    def test_ambiguity_asks_instead_of_launching(self, richst_world):
        result, calls = _run_launch(richst_world, "richst", self.SUCCESS)
        assert calls == []  # NEVER launched a guess
        out = result.outputs.get("launch_res", {})
        assert out.get("clarification_required") is True
        assert "ambiguous" in str(out.get("error", "")).lower()
        assert "RichST TV" in result.assistant_reply
        assert "Which one did you mean?" in result.assistant_reply

    def test_unknown_target_falls_back_to_inventory(self, world):
        result, calls = _run_launch(world, "someapp", self.SUCCESS)
        assert calls == ["someapp"]
        assert result.execution_status.value == "succeeded" or "Launched" in result.assistant_reply

    def test_kill_switch_restores_legacy_path(self, richst_world, monkeypatch):
        monkeypatch.setattr("app.config.settings.ARENA_APP_IDENTITY", "0")
        result, calls = _run_launch(richst_world, "richst", self.SUCCESS)
        # legacy behavior: the raw query goes straight to the matcher
        assert calls == ["richst"]

    def test_broken_world_model_fails_open(self):
        class BrokenWorld:
            def resolve_candidates(self, *a, **k):
                raise RuntimeError("db locked")

        result, calls = _run_launch(BrokenWorld(), "richst", self.SUCCESS)
        assert calls == ["richst"]  # degraded, not failed


def test_wiring_is_in_place():
    import inspect

    import app.agents.master_agent as ma
    import app.mind.app_identity as ai

    src = inspect.getsource(ma)
    assert "resolve_app_target" in src
    assert "remember_app" in src
    assert "app_identity" in src
    from app.config import settings
    assert hasattr(settings, "ARENA_APP_IDENTITY")
    assert ai.RESOLVE_CONFIDENT > ai.AMBIGUOUS_FLOOR
