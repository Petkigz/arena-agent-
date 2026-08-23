"""Static contracts for Android Owner Control when Android SDK is unavailable."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = (ROOT / "android/app/src/main/java/com/arena/voice/api/ApiClient.kt").read_text()
SETTINGS = (ROOT / "android/app/src/main/java/com/arena/voice/ui/screens/SettingsScreen.kt").read_text()


def test_android_api_exposes_stage_specific_owner_control_routes():
    required = [
        'call("/owner-control")',
        '"/owner-control", "PUT"',
        'call("/owner-control/pause", "POST"',
        '"/owner-control/approvals/${segment(actionId)}/decision"',
        '"/owner-control/plans/${segment(planId)}/decision"',
        '"/owner-control/plans/${segment(planId)}/execute"',
        '"/owner-control/executions/${segment(executionId)}/cancel"',
        '"/owner-control/executions/${segment(executionId)}/request-rollback"',
    ]
    for marker in required:
        assert marker in API
    assert '"PUT" -> builder.put(requestBody)' in API


def test_android_ui_states_that_decision_is_not_execution():
    assert "Approval authorizes only the exact recommendation. It does not execute it." in SETTINGS
    assert 'Text("Authorize only")' in SETTINGS
    assert 'Text("Execute approved plan separately")' in SETTINGS
    assert '"Exact action authorized; nothing executed"' in SETTINGS
    assert '"Plan decision recorded; nothing executed"' in SETTINGS
    assert '"Rollback compensation added to approvals; not executed"' in SETTINGS


def test_approval_and_plan_decision_functions_do_not_call_execution_routes():
    approval_block = SETTINGS.split("fun decideApproval", 1)[1].split("fun decidePlan", 1)[0]
    plan_block = SETTINGS.split("fun decidePlan", 1)[1].split("fun executePlan", 1)[0]
    assert "executeApprovedPlan" not in approval_block
    assert "executeApprovedPlan" not in plan_block
    assert "api.decideApproval" in approval_block
    assert "api.decidePlan" in plan_block
