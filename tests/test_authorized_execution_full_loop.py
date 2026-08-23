"""Authorized actions must return through observation, verification, and learning."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.cognition.action_proposal import ActionProposal, GateResult
from app.cognition.goal_lifecycle import GoalLifecycleState
from app.cognition.runtime import CognitiveRuntime


class _Prediction:
    confidence = 0.8
    expected_changes = {"artifact": "created"}


class _PredictionEngine:
    def predict_action(self, action_type, payload):
        return _Prediction()

    def evaluate_surprisal(self, prediction, actual_state):
        return 0.2


class _Recorder:
    def __init__(self):
        self.calls = []

    def record_outcome(self, **kwargs):
        self.calls.append(kwargs)

    def extract_lesson(self, **kwargs):
        self.calls.append(kwargs)

    def learn_from_surprisal(self, **kwargs):
        self.calls.append(kwargs)

    def learn_from_execution(self, **kwargs):
        self.calls.append(kwargs)


class _Learning:
    def __init__(self):
        self.calls = []

    def process_outcome_reflection(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content="verified lesson")


def _runtime():
    runtime = object.__new__(CognitiveRuntime)
    runtime.memory = object()
    runtime.world = object()
    runtime.registry = object()
    runtime.prediction = _PredictionEngine()
    runtime.world_ingest = Mock()
    runtime.causal_inference = _Recorder()
    runtime.learning = _Learning()
    runtime.outcomes = _Recorder()
    runtime.lessons = _Recorder()
    runtime.events = Mock()
    runtime.capture_observed_world_state = Mock(return_value={
        "entities": [],
        "observations": {"artifact": {"value": "created", "source": "filesystem_probe"}},
    })
    runtime._integrate_phase_modules = Mock()
    return runtime


def _goal():
    return SimpleNamespace(
        primary_intent_type="action_intent",
        target_domain="filesystem",
        goal="create artifact",
        entities=[],
        success_conditions=["artifact_created = true"],
        failure_conditions=[],
    )


def test_authorized_execution_runs_observation_verification_and_learning():
    runtime = _runtime()
    proposal = ActionProposal(
        action_type="create_note",
        payload={"query": "Create a verified artifact", "title": "x"},
        authorization_id="auth_exact",
    )
    execution = {
        "success": True,
        "executed_actions": ["Created artifact"],
        "assistant_reply": "Artifact created",
        "model_used": "fast",
    }

    def verified(*args, **kwargs):
        tracker = kwargs["tracker"]
        tracker.transition(GoalLifecycleState.VERIFYING, "checking")
        tracker.transition(GoalLifecycleState.ACHIEVED, "observed")
        return SimpleNamespace(
            verified_success=True,
            failed_conditions=[],
            met_conditions=["artifact_created = true"],
            verification_reason="Observed artifact through filesystem probe",
        )

    execute = Mock(return_value=execution)
    observe = Mock(return_value=[SimpleNamespace(source="filesystem_probe")])
    fake_agent_module = SimpleNamespace(
        MasterAgentOrchestrator=SimpleNamespace(execute_proposal=execute)
    )
    fake_perception_module = SimpleNamespace(
        ObservationCollector=SimpleNamespace(collect_and_ingest_observations=observe)
    )

    with (
        patch.dict(sys.modules, {
            "app.agents.master_agent": fake_agent_module,
            "app.cognition.perception": fake_perception_module,
        }),
        patch(
            "app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal",
            return_value=_goal(),
        ),
        patch(
            "app.cognition.action_proposal.ActionGate.evaluate_proposal",
            return_value=GateResult(True, "passed_all_gates", "authorized", decision_stage="authorized"),
        ),
        patch("app.cognition.runtime.GoalVerifier.verify_goal_achievement", side_effect=verified) as verify,
        patch("app.cognition.runtime.CognitiveTrace.finalize") as finalize,
        patch("app.cognition.runtime.db.create_audit_log") as audit,
    ):
        result = runtime.execute_authorized_proposal(
            proposal,
            user_text="Create a verified artifact",
        )

    assert result["request_success"] is True
    assert result["execution_success"] is True
    assert result["goal_verified"] is True
    assert result["goal_lifecycle_state"] == "achieved"
    assert result["replan_performed"] is False
    execute.assert_called_once()
    observe.assert_called_once()
    verify.assert_called_once()
    finalize.assert_called_once()
    audit.assert_called_once()
    assert runtime.outcomes.calls and runtime.lessons.calls
    assert runtime.learning.calls and runtime.causal_inference.calls
    runtime._integrate_phase_modules.assert_called_once()


def test_authorized_execution_reports_tool_success_separately_from_unknown_goal():
    runtime = _runtime()
    proposal = ActionProposal(
        action_type="create_note",
        payload={"query": "Create something that needs external confirmation"},
        authorization_id="auth_exact",
    )

    def unknown(*args, **kwargs):
        tracker = kwargs["tracker"]
        tracker.transition(GoalLifecycleState.VERIFYING, "checking")
        tracker.transition(GoalLifecycleState.WAITING_FOR_EVIDENCE, "missing external evidence")
        return SimpleNamespace(
            verified_success=False,
            failed_conditions=[],
            met_conditions=[],
            verification_reason="External confirmation unavailable",
        )

    execute = Mock(return_value={
        "success": True,
        "executed_actions": ["Tool reported success"],
        "assistant_reply": "Done",
    })
    observe = Mock(return_value=[])
    fake_agent_module = SimpleNamespace(
        MasterAgentOrchestrator=SimpleNamespace(execute_proposal=execute)
    )
    fake_perception_module = SimpleNamespace(
        ObservationCollector=SimpleNamespace(collect_and_ingest_observations=observe)
    )

    with (
        patch.dict(sys.modules, {
            "app.agents.master_agent": fake_agent_module,
            "app.cognition.perception": fake_perception_module,
        }),
        patch(
            "app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal",
            return_value=_goal(),
        ),
        patch(
            "app.cognition.action_proposal.ActionGate.evaluate_proposal",
            return_value=GateResult(True, "passed_all_gates", "authorized", decision_stage="authorized"),
        ),
        patch("app.cognition.runtime.GoalVerifier.verify_goal_achievement", side_effect=unknown),
        patch("app.cognition.runtime.CognitiveTrace.finalize"),
        patch("app.cognition.runtime.db.create_audit_log"),
    ):
        result = runtime.execute_authorized_proposal(proposal, "Create it")

    assert result["execution_success"] is True
    assert result["goal_verified"] is False
    assert result["verification_unknown"] is True
    assert result["requires_new_authorization_for_retry"] is True


def test_gate_failure_never_reaches_interpreter_or_capability_execution():
    runtime = _runtime()
    proposal = ActionProposal(
        action_type="send_email",
        payload={"to": "owner@example.test"},
        authorization_id="expired",
    )
    execute = Mock()
    fake_agent_module = SimpleNamespace(
        MasterAgentOrchestrator=SimpleNamespace(execute_proposal=execute)
    )

    with (
        patch.dict(sys.modules, {"app.agents.master_agent": fake_agent_module}),
        patch(
            "app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal",
            return_value=_goal(),
        ) as interpret,
        patch(
            "app.cognition.action_proposal.ActionGate.evaluate_proposal",
            return_value=GateResult(
                False,
                "authorization_gate",
                "Authorization expired",
                requires_approval=True,
                decision_stage="rejected",
            ),
        ),
        patch("app.cognition.runtime.CognitiveTrace.finalize"),
    ):
        result = runtime.execute_authorized_proposal(proposal, "Send it")

    assert result["success"] is False
    assert result["execution_success"] is False
    assert result["gate"] == "authorization_gate"
    interpret.assert_not_called()
    execute.assert_not_called()


def test_observation_only_reconciliation_never_calls_capability_layer():
    runtime = _runtime()
    proposal = ActionProposal(
        action_type="open_application",
        payload={"query": "Open editor", "app_name": "editor"},
    )
    observe = Mock(return_value=[SimpleNamespace(source="process_probe")])
    fake_perception_module = SimpleNamespace(
        ObservationCollector=SimpleNamespace(collect_and_ingest_observations=observe)
    )
    execute = Mock()
    fake_agent_module = SimpleNamespace(
        MasterAgentOrchestrator=SimpleNamespace(execute_proposal=execute)
    )

    def verified(*args, **kwargs):
        tracker = kwargs["tracker"]
        tracker.transition(GoalLifecycleState.VERIFYING, "checking again")
        tracker.transition(GoalLifecycleState.ACHIEVED, "process now observed")
        return SimpleNamespace(
            verified_success=True,
            final_state=GoalLifecycleState.ACHIEVED,
            is_unknown=False,
            failed_conditions=[],
            met_conditions=["process_running = true"],
            unknown_conditions=[],
            verification_reason="Direct process probe",
        )

    with (
        patch.dict(sys.modules, {
            "app.cognition.perception": fake_perception_module,
            "app.agents.master_agent": fake_agent_module,
        }),
        patch(
            "app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal",
            return_value=_goal(),
        ),
        patch("app.cognition.runtime.GoalVerifier.verify_goal_achievement", side_effect=verified),
        patch(
            "app.cognition.owner_control.owner_control_store.get_policy",
            return_value=SimpleNamespace(paused=False),
        ),
    ):
        result = runtime.verify_existing_proposal_outcome(
            proposal,
            "Open editor",
            {
                "execution_success": True,
                "executed_actions": ["Prior launch command"],
                "assistant_reply": "Launch command succeeded",
                "trace_id": "trace-prior",
            },
        )

    assert result["goal_verified"] is True
    assert result["reconciliation"] is True
    assert result["reexecuted"] is False
    observe.assert_called_once()
    execute.assert_not_called()


def test_interpretation_failure_returns_typed_result_after_grant_consumption():
    runtime = _runtime()
    proposal = ActionProposal(
        action_type="create_note",
        payload={"query": "Create note"},
        authorization_id="auth_exact",
    )

    with (
        patch(
            "app.cognition.action_proposal.ActionGate.evaluate_proposal",
            return_value=GateResult(True, "passed_all_gates", "authorized", decision_stage="authorized"),
        ),
        patch(
            "app.cognition.goal_interpreter.SemanticGoalInterpreter.interpret_goal",
            side_effect=RuntimeError("interpreter unavailable"),
        ),
        patch("app.cognition.runtime.CognitiveTrace.finalize"),
    ):
        result = runtime.execute_authorized_proposal(proposal, "Create note")

    assert result["success"] is False
    assert result["request_success"] is True
    assert result["execution_success"] is False
    assert result["authorization_consumed"] is True
    assert result["requires_new_authorization_for_retry"] is True
    assert "interpreter unavailable" in result["reason"]
