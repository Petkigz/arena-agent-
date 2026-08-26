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
        'call("/owner-control/authorizations")',
        '"/owner-control/execute-authorized"',
        '"/owner-control/authorizations/${segment(authorizationId)}", "DELETE"',
        '"/owner-control/plans/${segment(planId)}", "PUT"',
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
    assert 'Text("Execute exact scope")' in SETTINGS
    assert 'Text("Execute approved plan separately")' in SETTINGS
    assert 'Text("Save as new unapproved revision")' in SETTINGS
    assert '"Exact action authorized; nothing executed"' in SETTINGS
    assert '"Plan decision recorded; nothing executed"' in SETTINGS
    assert '"Rollback compensation added to approvals; not executed"' in SETTINGS


def test_approval_and_plan_decision_functions_do_not_call_execution_routes():
    approval_block = SETTINGS.split("fun decideApproval", 1)[1].split("fun executeAuthorization", 1)[0]
    plan_block = SETTINGS.split("fun decidePlan", 1)[1].split("fun executePlan", 1)[0]
    assert "executeAuthorized" not in approval_block
    assert "executeApprovedPlan" not in approval_block
    assert "executeApprovedPlan" not in plan_block
    assert "api.decideApproval" in approval_block
    assert "api.decidePlan" in plan_block


def test_android_api_exposes_autonomy_operations_routes():
    required = [
        'call("/owner-control/autonomous-goals")',
        '"/owner-control/autonomous-goals", "POST"',
        '"/owner-control/autonomous-goals/${segment(goalId)}/decision"',
        '"/owner-control/autonomous-goals/${segment(goalId)}/defer"',
        '"/owner-control/autonomous-goals/${segment(goalId)}/priority", "PUT"',
        '"/owner-control/autonomous-goals/execute-next"',
        '"/owner-control/autonomous-goals/allocation-preview"',
        'call("/owner-control/autonomy-schedule")',
        '"/owner-control/autonomy-schedule", "POST"',
        '"/owner-control/autonomy-schedule/${segment(scheduleId)}/status"',
        '"/owner-control/autonomy-runs?limit=$limit"',
        '"/owner-control/autonomy-runs/${segment(cycleId)}/timeline"',
        'call("/owner-control/autonomy-envelope")',
        '"/owner-control/autonomy-envelope", "PUT"',
    ]
    for marker in required:
        assert marker in API


def test_android_api_exposes_preemptions_budgets_decisions_and_groundings():
    required = [
        'call("/owner-control/preemptions")',
        '"/owner-control/preemptions", "POST"',
        '"/owner-control/preemptions/${segment(preemptionId)}/refresh"',
        '"/owner-control/preemptions/${segment(preemptionId)}/reconcile"',
        '"/owner-control/preemptions/${segment(preemptionId)}/request-resume"',
        '"/owner-control/plans/${segment(planId)}/step-reconciliations"',
        'call("/owner-control/concurrency-budget")',
        '"/owner-control/concurrency-budget", "PUT"',
        'call("/owner-control/concurrency-budget/receipts?limit=20")',
        'call("/owner-control/owner-decisions")',
        '"/owner-control/owner-decisions", "POST"',
        '"/owner-control/owner-decisions/${segment(decisionId)}/revoke"',
        'call("/os-grounding")',
        'call("/os-grounding/accessibility/status")',
        'call("/os-grounding/browser-tabs")',
    ]
    for marker in required:
        assert marker in API
    # The sensitive-autonomy switch is an explicit owner policy field.
    assert '"allow_sensitive_autonomy", allowSensitiveAutonomy' in API


def test_android_ui_states_autonomy_authority_boundaries():
    markers = [
        '"Goal decision recorded; planning only — execution stays separate"',
        '"Directive created; it authorizes planning only"',
        '"Reconciled; step now $step (nothing executed)"',
        '"Resume requested; separately execute the approved plan"',
        '"Owner worker budget updated (clamped to physical threads)"',
        '"Decision issued (single-use); pass its ID to the identity checkpoint"',
        'Text("Delegate sensitive (Level 3) autonomy", fontWeight',
        'Text("Safety ceiling 0–3")',
    ]
    for marker in markers:
        assert marker in SETTINGS


def test_android_goal_decision_does_not_execute_and_ceiling_allows_level_three():
    goal_block = SETTINGS.split("fun decideAutonomousGoal", 1)[1].split("fun executeNextAutonomousGoal", 1)[0]
    assert "api.decideAutonomousGoal" in goal_block
    assert "executeNextAutonomousGoal" not in goal_block
    assert "api.executeNextAutonomousGoal" not in goal_block
    save_block = SETTINGS.split("fun saveOwnerPolicy", 1)[1].split("fun toggleEmergencyPause", 1)[0]
    assert "coerceIn(0, 3)" in save_block  # Level 3 reachable only with the sensitive switch
    assert "allowSensitiveAutonomy" in save_block


def test_android_api_exposes_cognition_surfaces():
    required = [
        'call("/owner-control/charter")',
        '"/owner-control/charter", "PUT"',
        'call("/owner-control/questions?status=pending")',
        '"/owner-control/questions/${segment(questionId)}/answer"',
        'call("/owner-control/induced-skills?status=pending")',
        '"/owner-control/induced-skills/${segment(candidateId)}/accept"',
        '"/owner-control/induced-skills/${segment(candidateId)}/reject"',
        'call("/owner-control/learning-progress")',
        'call("/owner-control/owner-model")',
    ]
    for marker in required:
        assert marker in API


def test_android_ui_states_cognition_authority_boundaries():
    markers = [
        '"Exact approval created; nothing executed"',
        '"Skill accepted; execution still passes all gates"',
        '"Charter saved; it informs every cycle and grants no authority"',
        'Text("Approve exactly")',
        'Text("Accept skill")',
        'data class OwnerQuestion(',
        'data class InducedSkill(',
    ]
    for marker in markers:
        assert marker in SETTINGS


def test_android_cognition_answers_never_execute():
    question_block = SETTINGS.split("fun answerQuestion", 1)[1].split("fun decideInducedSkill", 1)[0]
    assert "api.answerOwnerQuestion" in question_block
    assert "execute" not in question_block.replace("nothing executed", "")
