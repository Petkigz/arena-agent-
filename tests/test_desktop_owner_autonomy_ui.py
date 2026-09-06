"""Desktop parity for the newest owner surfaces: transports and native UI.

Client tests verify the exact HTTP calls. The widget test runs OFFSCREEN with a
recording fake client (skipped automatically when PySide6 is not installed, so
clean CI is unaffected) and verifies the new autonomy tab controls actually
drive the client with authority boundaries intact.
"""
import json

import httpx
import pytest

from desktop.backend_client import ArenaBackendClient


def recording_client():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        return httpx.Response(200, json={"success": True})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    return client, calls


def test_preemption_and_timeline_transports():
    client, calls = recording_client()
    client.autonomy_cycle_timeline("cycle/1")
    client.plan_step_reconciliations("plan/9")
    client.allocation_preview()
    client.preemptions()
    client.create_preemption("exec/1", "goal/2", plan_id="plan/3")
    client.refresh_preemption("pm/4")
    client.reconcile_preemption("pm/4")
    client.request_preemption_resume("pm/4")
    client.owner_decisions()
    client.issue_owner_decision(["provider_model_changed"], note="14B")
    client.revoke_owner_decision("od/7")
    client.close()

    by_path = {(m, p): body for m, p, body in calls}
    assert ("GET", "/owner-control/autonomy-runs/cycle/1/timeline") in by_path
    assert ("GET", "/owner-control/plans/plan/9/step-reconciliations") in by_path
    assert ("GET", "/owner-control/autonomous-goals/allocation-preview") in by_path
    assert ("GET", "/owner-control/preemptions") in by_path
    assert ("GET", "/owner-control/owner-decisions") in by_path
    assert by_path[("POST", "/owner-control/preemptions")] == {
        "execution_id": "exec/1", "urgent_goal_id": "goal/2",
        "reason": "Urgent owner priority", "plan_id": "plan/3",
    }
    assert ("POST", "/owner-control/preemptions/pm/4/refresh") in by_path
    assert ("POST", "/owner-control/preemptions/pm/4/reconcile") in by_path
    assert ("POST", "/owner-control/preemptions/pm/4/request-resume") in by_path
    assert by_path[("POST", "/owner-control/owner-decisions")] == {
        "decision_type": "expected_identity_change",
        "expected_change_types": ["provider_model_changed"],
        "note": "14B",
    }
    assert ("POST", "/owner-control/owner-decisions/od/7/revoke") in by_path


class FakeClient:
    """Recording stand-in for ArenaBackendClient used by the widget tests."""

    def __init__(self):
        self.calls = []
        self.goals_list = [{"goal_id": "g1", "title": "Daily report", "status": "pending_decision", "priority": "high"}]
        self.run_events = [{"cycle_id": "cyc_1", "stage": "executed", "created_at": "2026-08-24T10:00:00+00:00"}]
        self.preemption_list = [{"preemption_id": "pm_1", "status": "resume_ready", "reason": "urgent"}]
        self.decision_list = [{"decision_id": "od_1", "status": "active", "payload": {"expected_change_types": ["provider_model_changed"]}}]

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return {"success": True}

    # existing surfaces used by refresh()
    def owner_control(self): return {"policy": {"mode": "bounded_autonomy", "paused": False, "max_autonomous_level": 2}}
    def adaptive_autonomy(self): return {"profile": {"owner_max_exploration_goals": 2}}
    def pending_approvals(self): return {"approvals": []}
    def active_authorizations(self): return {"authorizations": []}
    def reviewed_plans(self): return {"plans": []}
    def controlled_executions(self): return {"executions": []}

    # new surfaces
    def autonomous_goals(self): self.calls.append(("autonomous_goals", (), {})); return {"goals": self.goals_list}
    def autonomy_run_events(self, limit=200): self.calls.append(("autonomy_run_events", (limit,), {})); return {"events": self.run_events}
    def autonomy_envelope(self): return {"envelope": {"cycles_enabled": True, "limits_enabled": False}}
    # Recording matters: the widget tests assert the refresh call ORDER
    # after actions like _execute_next_goal — a fake method that returns
    # data without recording makes those calls invisible to named_calls
    # and the assertion unsatisfiable (owner run 2026-09-02: the test
    # failed demanding 'preemptions'/'owner_decisions' refreshes that
    # HAD happened — page.preemptions.count() == 1 passed above).
    def preemptions(self):
        self.calls.append(("preemptions", (), {}))
        return {"preemptions": self.preemption_list}
    def concurrency_budget(self): return {"budget": {"workers_granted": 6, "configured_budget": 6, "physical_thread_cap": 32, "reasons": []}}
    def owner_decisions(self, limit=200):
        self.calls.append(("owner_decisions", (limit,), {}))
        return {"decisions": self.decision_list}
    def decide_autonomous_goal(self, goal_id, approved): return self._record("decide_autonomous_goal", goal_id, approved)
    def defer_autonomous_goal(self, goal_id): return self._record("defer_autonomous_goal", goal_id)
    def execute_next_autonomous_goal(self): return self._record("execute_next_autonomous_goal")
    def allocation_preview(self): return self._record("allocation_preview")
    def create_autonomous_goal(self, title, description, priority): return self._record("create_autonomous_goal", title, description, priority)
    def create_scheduled_directive(self, title, run_at, recurrence="none", tz="UTC"): return self._record("create_scheduled_directive", title, run_at, recurrence, tz)
    def autonomy_cycle_timeline(self, cycle_id): return self._record("autonomy_cycle_timeline", cycle_id)
    def update_autonomy_envelope(self, patch): return self._record("update_autonomy_envelope", patch)
    def create_preemption(self, execution_id, urgent_goal_id, plan_id=None): return self._record("create_preemption", execution_id, urgent_goal_id, plan_id)
    def refresh_preemption(self, preemption_id): return self._record("refresh_preemption", preemption_id)
    def reconcile_preemption(self, preemption_id):
        self._record("reconcile_preemption", preemption_id)
        return {"reconciliation": {"resume_recommendation": "wait_for_evidence"},
                "step_status_update": {"status": "unknown_pending_evidence"}}
    def request_preemption_resume(self, preemption_id): return self._record("request_preemption_resume", preemption_id)
    def set_concurrency_budget(self, enabled=None, max_workers=None): return self._record("set_concurrency_budget", enabled, max_workers)
    def concurrency_receipts(self, limit=20): return self._record("concurrency_receipts", limit)
    def issue_owner_decision(self, types, note=""): return self._record("issue_owner_decision", types, note)
    def revoke_owner_decision(self, decision_id): return self._record("revoke_owner_decision", decision_id)
    # cognition surfaces
    def owner_charter(self): return {"charter": {"mission": "full owner sovereignty", "revision": 2,
                                                 "priorities": ["stability"], "standing_directives": []}}
    def update_owner_charter(self, patch): return self._record("update_owner_charter", patch) or {"charter": {"revision": 3}}
    def owner_questions(self, status="pending"):
        return {"questions": [{"question_id": "oq_1", "action_type": "search_files",
                               "question_text": "30% confident — proceed?", "calibrated_confidence": 0.3}]}
    def answer_owner_question(self, question_id, answer, note=""):
        self._record("answer_owner_question", question_id, answer)
        return {"approval_action_id": "act_7"} if answer == "approve" else {}
    def induced_skills(self, status="pending"):
        return {"candidates": [{"candidate_id": "isk_1", "skill_name": "induced_copy_compress",
                                "occurrences": 4, "action_sequence": ["copy_file_verified", "compress_files"]}]}
    def scan_induced_skills(self): return self._record("scan_induced_skills") or {"candidates_created": 0, "plans_scanned": 3}
    def accept_induced_skill(self, candidate_id): return self._record("accept_induced_skill", candidate_id)
    def reject_induced_skill(self, candidate_id): return self._record("reject_induced_skill", candidate_id)
    def learning_progress(self):
        return {"targets": [{"action_type": "browser_upload", "status": "improving", "learning_value": 0.42}]}
    def owner_model_report(self):
        return {"consistently_approves": ["create_backup"], "consistently_denies": [], "peak_activity_hours_utc": []}


def named_calls(fake):
    return [c[0] for c in fake.calls]


@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
    except Exception as exc:  # missing system GL/Qt runtime libs
        pytest.skip(f"Qt GUI runtime unavailable: {exc}")
    yield app


def test_owner_control_page_compiles_without_qt():
    """The page module must stay syntactically valid even where PySide6 is absent."""
    import ast
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "desktop" / "pages" / "owner_control.py"
    ast.parse(source.read_text(encoding="utf-8"))


def test_owner_control_page_autonomy_tabs_offscreen(qapp):
    pytest.importorskip("PySide6")
    from desktop.pages.owner_control import OwnerControlPage

    fake = FakeClient()
    page = OwnerControlPage(fake)
    try:
        # Refresh populated the new tabs from the newest owner surfaces.
        assert "autonomous_goals" in named_calls(fake)
        assert "autonomy_run_events" in named_calls(fake)
        assert page.goals.count() == 1
        assert page.runs.count() == 1
        assert page.preemptions.count() == 1
        assert page.decisions.count() == 1
        assert "6 granted" in page.budget_label.text()

        # Goal decision: authorizes planning only; status says so.
        page.goals.setCurrentRow(0)
        page._decide_goal(True)
        assert ("decide_autonomous_goal", ("g1", True), {}) in fake.calls

        # Execute-next is an explicit separate action.
        fake.calls.clear()
        page._execute_next_goal()
        assert named_calls(fake) == ["execute_next_autonomous_goal", "autonomous_goals", "autonomy_run_events", "preemptions", "owner_decisions"]

        # Run timeline loads with commitment/recovery links.
        fake.calls.clear()
        page._show_run_timeline(page.runs.item(0))
        assert ("autonomy_cycle_timeline", ("cyc_1",), {}) in fake.calls

        # Directive creation requires a title.
        page._create_goal()
        assert "required" in page.status.text()
        page.goal_title.setText("Weekly backup review")
        # Select the priority EXPLICITLY: the combo defaults to its first
        # item ('critical' — owner run 2026-09-03 caught this line asserting
        # 'high' against a default it had never run against; the wiring,
        # not the default, is what this test must pin).
        page.goal_priority.setCurrentText("high")
        page._create_goal()
        assert ("create_autonomous_goal", ("Weekly backup review", "", "high"), {}) in fake.calls

        # Schedule creation passes recurrence and timezone.
        # _create_goal deliberately CLEARS the title field after a
        # successful create (form-reset UX) and _create_schedule
        # shares that field (owner run 2026-09-03: this assertion had
        # never executed before and assumed the title survived).
        # Prove the required-guard fires on the cleared title first,
        # then create with the title re-set.
        page.schedule_run_at.setText("2026-08-25T09:00:00")
        page._create_schedule()
        assert "required" in page.status.text()
        assert not any(c[0] == "create_scheduled_directive" for c in fake.calls)
        page.goal_title.setText("Weekly backup review")
        page._create_schedule()
        assert any(c[0] == "create_scheduled_directive" and c[1][2] == "none" and c[1][3] == "Africa/Kampala" for c in fake.calls)

        # Preemption lifecycle from the executions the owner selects.
        page.preemptions.setCurrentRow(0)
        page._reconcile_preemption()
        assert any(c[0] == "reconcile_preemption" and "unknown_pending_evidence" in page.status.text() for c in fake.calls)
        page._request_preemption_resume()
        assert ("request_preemption_resume", ("pm_1",), {}) in fake.calls

        # Budget override requires the explicit checkbox first.
        page._apply_budget()
        assert "Check" in page.status.text()
        page.budget_override.setChecked(True)
        page.budget_workers.setValue(8)
        page._apply_budget()
        assert ("set_concurrency_budget", (True, 8), {}) in fake.calls
        page._reset_budget()
        assert ("set_concurrency_budget", (True, None), {}) in fake.calls

        # Owner decisions: issue with parsed types, revoke selected.
        page.decision_types.setText("provider_model_changed, capability_count_decreased")
        page._issue_decision()
        assert any(c[0] == "issue_owner_decision" and c[1][0] == ["provider_model_changed", "capability_count_decreased"] for c in fake.calls)
        page.decisions.setCurrentRow(0)
        page._revoke_decision()
        assert ("revoke_owner_decision", ("od_1",), {}) in fake.calls
    finally:
        page.deleteLater()


def test_desktop_cognition_client_transports():
    calls = []

    def handler(request):
        url = str(request.url)  # full URL including query string
        calls.append((request.method, url, json.loads(request.content) if request.content else None))
        return httpx.Response(200, json={"success": True})

    c = ArenaBackendClient(); c._client = httpx.Client(transport=httpx.MockTransport(handler))
    c.owner_charter()
    c.update_owner_charter({"mission": "full sovereignty"})
    c.owner_questions()
    c.answer_owner_question("oq/1", "approve", "ok")
    c.induced_skills()
    c.scan_induced_skills()
    c.accept_induced_skill("isk 1")
    c.reject_induced_skill("isk 1")
    c.learning_progress()
    c.owner_model_report()
    c.close()

    base = calls[0][1].rsplit("/owner-control", 1)[0]  # scheme+host prefix
    by_path = {(m, url[len(base):] if url.startswith(base) else url): b for m, url, b in calls}
    assert ("GET", "/owner-control/charter") in by_path
    assert by_path[("PUT", "/owner-control/charter")] == {"mission": "full sovereignty"}
    assert ("GET", "/owner-control/questions?status=pending") in by_path
    assert by_path[("POST", "/owner-control/questions/oq%2F1/answer")] == {"answer": "approve", "note": "ok"}
    assert ("GET", "/owner-control/induced-skills?status=pending") in by_path
    assert ("POST", "/owner-control/induced-skills/scan") in by_path
    assert ("POST", "/owner-control/induced-skills/isk%201/accept") in by_path
    assert ("POST", "/owner-control/induced-skills/isk%201/reject") in by_path
    assert ("GET", "/owner-control/learning-progress") in by_path
    assert ("GET", "/owner-control/owner-model") in by_path


def test_owner_control_page_cognition_tab_offscreen(qapp):
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from desktop.pages.owner_control import OwnerControlPage
    except Exception as exc:
        pytest.skip(f"Qt GUI runtime unavailable: {exc}")

    fake = FakeClient()
    page = OwnerControlPage(fake)
    try:
        # The cognition tab populated from the fake owner surfaces.
        assert "revision" in page.charter_label.text()
        assert page.questions.count() == 1
        assert page.induced.count() == 1
        assert "browser_upload" in page.learning_label.text()

        page.questions.setCurrentRow(0)
        fake.calls.clear()
        page._answer_question("approve")
        assert any(c[0] == "answer_owner_question" and c[1][1] == "approve" for c in fake.calls)
        assert "nothing executed" in page.status.text()

        page.induced.setCurrentRow(0)
        page._decide_induced_skill(True)
        assert any(c[0] == "accept_induced_skill" for c in fake.calls)
        assert "still passes all gates" in page.status.text()

        page._save_charter()
        assert any(c[0] == "update_owner_charter" for c in fake.calls)
        assert "grants no authority" in page.status.text()
    finally:
        page.deleteLater()


def test_live_theme_switch_actually_repaints(qapp):
    """apply_theme('light') must change what pages render (G4 regression).

    Pages rebuild stylesheets from `from desktop.theme import ...` names bound
    at import time; desktop.theme.apply_theme now rebinds those importer
    copies, so a live switch repaints the real palette instead of silently
    re-applying the stale dark one.
    """
    from desktop import theme
    from desktop.pages.owner_control import OwnerControlPage

    page = OwnerControlPage(FakeClient())
    try:
        theme.apply_theme("light")
        page.refresh_theme()
        title_css = page.title.styleSheet()
        assert theme.THEME_COLORS["light"]["TEXT_PRIMARY"] in title_css
        assert theme.THEME_COLORS["dark"]["TEXT_PRIMARY"] not in title_css
        # Fresh stylesheet helpers follow the switch too.
        from desktop.styles import _input_style

        assert theme.THEME_COLORS["light"]["BG_SECONDARY"] in _input_style()
    finally:
        theme.apply_theme("dark")
        page.deleteLater()
