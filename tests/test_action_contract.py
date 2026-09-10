"""Phase 4 — action, authority, and verification contracts (owner plan 2026-09-10).

Pins the owner's exit criteria:
  * "Open RichST TV" either launches the exact matched app and reports
    verified process evidence, or names the concrete blocker;
  * no reply claims "I see you opened it" without observed evidence;
  * a clear, allowed request executes — the owner never repeats "do it";
  * authority questions are specific and actionable;
  * the launch process-verification override is now a GENERAL pattern
    (receipts), and the pinned launch behavior is unchanged.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.cognition.action_contract import (
    ActionContract,
    ExecutionReceipt,
    apply_receipt_to_verification,
    build_contract,
    can_claim_observed,
    capability_available,
    receipt_from_execution,
    verify_execution,
)
from app.cognition.action_proposal import ActionProposal
from app.cognition.world_model import WorldModel


@pytest.fixture
def world(tmp_path):
    w = WorldModel(db_path=str(tmp_path / "world.sqlite3"))
    tv = w.upsert_entity(name="RichST TV", entity_type="application")
    w.add_alias(tv.id, "richst tv", source="owner")
    return w


@pytest.fixture
def ambiguous_world(tmp_path):
    w = WorldModel(db_path=str(tmp_path / "world.sqlite3"))
    w.upsert_entity(name="RichST TV", entity_type="application")
    w.upsert_entity(name="RichST Radio", entity_type="application")
    return w


def _launch_proposal(app_name):
    return ActionProposal(action_type="open_application",
                          payload={"app_name": app_name})


def _verification():
    return SimpleNamespace(verified_success=False, is_unknown=True,
                           met_conditions=[], verification_reason="")


# ── the seven facts ───────────────────────────────────────────────────────


class TestSevenFacts:
    def test_contract_separates_all_seven_facts(self, world):
        c = build_contract(_launch_proposal("richst tv"), "open richst tv", world=world)
        assert c.capability["available"] is True
        assert c.target["status"] == "resolved"
        assert c.target["name"] == "RichST TV"
        assert c.authority["allowed"] is True
        assert c.expectation["effect"] == "the application's process is running"
        assert c.verification["method"] == "process_probe"
        assert c.reversibility["reversible"] is True
        assert c.reversibility["undo"]

    def test_clear_allowed_request_goes_straight_to_execution(self, world):
        # Exit criterion: the owner never has to repeat "do it".
        c = build_contract(_launch_proposal("richst tv"), "open richst tv", world=world)
        assert c.decision == "act"
        assert c.question == ""

    def test_unknown_capability_is_a_concrete_blocker(self, world):
        c = build_contract(ActionProposal(action_type="teleport_cat", payload={}),
                           "teleport the cat", world=world)
        assert c.decision == "blocked"
        assert "teleport_cat" in c.blocker

    def test_ambiguous_target_asks_one_focused_question(self, ambiguous_world):
        c = build_contract(_launch_proposal("richst"), "open richst", world=ambiguous_world)
        assert c.decision == "ask_target"
        assert "RichST TV" in c.question and "RichST Radio" in c.question

    def test_authority_question_is_specific_and_actionable(self, monkeypatch):
        monkeypatch.setattr(
            "app.policy.PolicyEvaluator.evaluate_action",
            staticmethod(lambda a, d: (False, "Sensitive action requires approval", 3)))
        c = build_contract(_launch_proposal("RichST TV"), "open RichST TV")
        assert c.decision == "ask_approval"
        assert "open application" in c.question
        assert "RichST TV" in c.question
        assert "level 3" in c.question
        assert "approve" in c.question
        # and it parks with the typed authorization reason (round-5 taxonomy)
        from app.cognition.goal_lifecycle import (
            PARK_AUTHORIZATION_REQUIRED, classify_park_reason)
        assert classify_park_reason({"assistant_reply": c.question}) == PARK_AUTHORIZATION_REQUIRED


# ── fact 7: receipts and probes ───────────────────────────────────────────


class TestReceipts:
    RESULT_VERIFIED = {"success": True, "app_name": "RichST TV",
                       "process_verified": True, "pid": 4242,
                       "process_name": "RichSTTV.exe", "already_running": True}

    def test_receipt_carries_process_evidence(self):
        r = receipt_from_execution(
            _launch_proposal("richst tv"),
            {"outputs": {"launch_res": self.RESULT_VERIFIED}, "success": True})
        assert r.verified is True
        assert r.evidence[0]["kind"] == "process"
        assert r.evidence[0]["pid"] == 4242
        assert r.evidence[0]["source"] == "psutil_scan"

    def test_negative_evidence_is_recorded_not_hidden(self):
        res = dict(self.RESULT_VERIFIED, process_verified=False, pid=None)
        r = receipt_from_execution(
            _launch_proposal("richst tv"),
            {"outputs": {"launch_res": res}, "success": True})
        assert r.verified is False  # observed-and-false, never None-as-true

    def test_receipt_names_the_concrete_blocker(self):
        r = receipt_from_execution(
            _launch_proposal("foo"),
            {"outputs": {"launch_res": {
                "success": False,
                "error": "No installed application matches 'foo' (inventory re-scanned just now)"}},
             "success": False})
        assert r.success is False
        assert "No installed application matches 'foo'" in r.blocker

    def test_receipt_teaches_the_world_model(self, world):
        receipt_from_execution(
            _launch_proposal("richst tv"),
            {"outputs": {"launch_res": self.RESULT_VERIFIED}, "success": True},
            world=world)
        status = world.entity_state_status("RichST TV", "process_state", max_age_hours=1.0)
        assert status["status"] == "current"
        assert status["value"] == "running"
        assert status["source"] == "execution_receipt"


class TestProbes:
    def test_process_probe_runs_when_result_carries_nothing(self, monkeypatch):
        monkeypatch.setattr(
            "app.tools.app_inventory.SystemAppInventory.verify_app_running",
            classmethod(lambda cls, q, e="", **k: {
                "process_verified": True, "pid": 7, "process_name": "vlc.exe"}))
        v = verify_execution("open_application", {}, "VLC")
        assert v["verified"] is True
        assert v["evidence"][0]["pid"] == 7

    def test_file_probe(self, tmp_path):
        f = tmp_path / "made.txt"
        f.write_text("x")
        assert verify_execution("create_file", {"file_path": str(f)})["verified"] is True
        assert verify_execution("create_file", {"file_path": str(tmp_path / "nope.txt")})["verified"] is False

    def test_no_probe_declared_is_honest(self):
        v = verify_execution("web_search", {})
        assert v["method"] == "none"
        assert v["verified"] is None  # never silently "success"

    def test_probe_failure_fails_open(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("psutil exploded")
        monkeypatch.setattr(
            "app.tools.app_inventory.SystemAppInventory.verify_app_running",
            classmethod(boom))
        v = verify_execution("open_application", {}, "VLC")
        assert v["verified"] is None
        assert v["evidence"][0]["kind"] == "probe_error"


# ── the generalized truth override ────────────────────────────────────────


class TestGeneralizedOverride:
    def test_receipt_overrides_verification_for_any_action(self):
        # The launch-only patch, generalized: a FILE receipt works too.
        receipt = ExecutionReceipt(action_type="create_file", target_name="made.txt",
                                   success=True, verified=True,
                                   verification_method="file_exists",
                                   evidence=[{"kind": "file", "path": "/tmp/made.txt",
                                              "exists": True}])
        ver = _verification()
        assert apply_receipt_to_verification(ver, receipt) is True
        assert ver.verified_success is True
        assert "file probe" in ver.met_conditions[0]

    def test_never_fires_without_evidence(self):
        ver = _verification()
        assert apply_receipt_to_verification(
            ver, ExecutionReceipt(verified=None, evidence=[])) is False
        assert apply_receipt_to_verification(ver, None) is False
        assert ver.verified_success is False

    def test_runtime_launch_behavior_unchanged(self):
        # The three behaviors pinned since 2026-09-08 must survive verbatim.
        from app.cognition.runtime import _apply_launch_truth_override
        ver = _verification()
        assert _apply_launch_truth_override(ver, "launch_app", {
            "outputs": {"launch_res": {"process_verified": True, "app_name": "x",
                                       "pid": 1, "process_name": "x.exe"}}}) is True
        assert _apply_launch_truth_override(_verification(), "launch_app",
                                            {"outputs": {"launch_res": {}}}) is False
        assert _apply_launch_truth_override(_verification(), "search_files",
                                            {"outputs": {}}) is False

    def test_runtime_generalizes_via_receipt(self):
        from app.cognition.runtime import _apply_launch_truth_override
        receipt = ExecutionReceipt(action_type="create_file", success=True,
                                   verified=True, verification_method="file_exists",
                                   evidence=[{"kind": "file", "path": "/tmp/m.txt",
                                              "exists": True}])
        ver = _verification()
        assert _apply_launch_truth_override(
            ver, "create_file", {"outputs": {"receipt": receipt.to_dict()}}) is True
        assert ver.verified_success is True

    def test_kill_switch_restores_launch_only(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.ARENA_ACTION_CONTRACT", "0")
        from app.cognition.runtime import _apply_launch_truth_override
        receipt = ExecutionReceipt(action_type="create_file", success=True,
                                   verified=True, verification_method="file_exists",
                                   evidence=[{"kind": "file", "path": "/tmp/m.txt",
                                              "exists": True}])
        assert _apply_launch_truth_override(
            _verification(), "create_file",
            {"outputs": {"receipt": receipt.to_dict()}}) is False


# ── the honesty gate ──────────────────────────────────────────────────────


class TestHonestyGate:
    def test_claim_requires_observed_evidence(self):
        good = ExecutionReceipt(verified=True, evidence=[{"kind": "process", "running": True}])
        assert can_claim_observed(good) is True
        assert can_claim_observed(ExecutionReceipt(verified=False, evidence=[{"kind": "process"}])) is False
        assert can_claim_observed(ExecutionReceipt(verified=None, evidence=[])) is False
        assert can_claim_observed(None) is False


# ── the launch seam end-to-end ────────────────────────────────────────────


def _run_launch(world, app_name, inventory_result):
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
            _launch_proposal(app_name), f"open {app_name}", world_model=world)
    return result, calls


class TestLaunchSeam:
    VERIFIED_RESULT = {"success": True, "app_name": "RichST TV",
                       "executable_path": "C:/RichST.exe",
                       "process_verified": True, "pid": 4242,
                       "process_name": "RichSTTV.exe"}

    def test_exact_app_launched_with_verified_evidence(self, world):
        # Exit criterion 1: launches the exact matched app AND reports
        # verified process evidence.
        result, calls = _run_launch(world, "richst tv", self.VERIFIED_RESULT)
        assert calls == ["RichST TV"]
        assert "process verified: RichSTTV.exe, pid 4242" in result.assistant_reply
        receipt = result.outputs["receipt"]
        assert receipt["verified"] is True

    def test_unobserved_launch_is_never_claimed_as_seen(self, world):
        # Exit criterion 2: no "I see you opened it" without observation.
        res = dict(self.VERIFIED_RESULT, process_verified=False, pid=None,
                   process_name="")
        result, _ = _run_launch(world, "richst tv", res)
        assert "NOT observed" in result.assistant_reply
        assert can_claim_observed(
            ExecutionReceipt(**{k: result.outputs["receipt"][k]
                                for k in ExecutionReceipt.__dataclass_fields__
                                if k in result.outputs["receipt"]})) is False

    def test_approval_required_produces_one_specific_question(self, world, monkeypatch):
        # Exit criteria 3+4: one actionable question, no launch attempt.
        monkeypatch.setattr(
            "app.policy.PolicyEvaluator.evaluate_action",
            staticmethod(lambda a, d: (False, "Sensitive action requires approval", 3)))
        result, calls = _run_launch(world, "richst tv", self.VERIFIED_RESULT)
        assert calls == []
        out = result.outputs["launch_res"]
        assert out["clarification_required"] is True
        assert "approve" in result.assistant_reply
        assert "RichST TV" in result.assistant_reply

    def test_contract_failure_fails_open(self, world, monkeypatch):
        monkeypatch.setattr("app.cognition.action_contract.build_contract",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        result, calls = _run_launch(world, "richst tv", self.VERIFIED_RESULT)
        assert calls == ["RichST TV"]  # degraded, not blocked

    def test_kill_switch_restores_pre_phase4_path(self, world, monkeypatch):
        monkeypatch.setattr("app.config.settings.ARENA_ACTION_CONTRACT", "0")
        monkeypatch.setattr(
            "app.policy.PolicyEvaluator.evaluate_action",
            staticmethod(lambda a, d: (False, "Sensitive action requires approval", 3)))
        result, calls = _run_launch(world, "richst tv", self.VERIFIED_RESULT)
        # no contract pre-flight: the launcher's own policy check is the guard
        assert calls == ["RichST TV"]


def test_wiring_is_in_place():
    import inspect

    import app.agents.master_agent as ma
    import app.cognition.runtime as rt

    assert "build_contract" in inspect.getsource(ma)
    assert "receipt_from_execution" in inspect.getsource(ma)
    assert "apply_receipt_to_verification" in inspect.getsource(rt)
    from app.config import settings
    assert hasattr(settings, "ARENA_ACTION_CONTRACT")
