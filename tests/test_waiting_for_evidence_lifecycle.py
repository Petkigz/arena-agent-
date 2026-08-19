"""
P1 Regression: WAITING_FOR_EVIDENCE lifecycle state.

Verifies that when goal conditions are UNKNOWN (missing perception evidence,
no explicit failures), the lifecycle enters WAITING_FOR_EVIDENCE rather than
being forced into FAILED or DEFERRED.

This closes the gap between the verifier's tri-state evaluation
(SATISFIED/FAILED/UNKNOWN) and the lifecycle state machine.
"""

import pytest
from app.cognition.goal_lifecycle import (
    GoalLifecycleState, GoalTracker, InvalidStateTransitionError
)
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_verifier import GoalVerifier, GoalVerificationResult


# ── State existence and transitions ───────────────────────────────────


class TestWaitingForEvidenceState:

    def test_state_exists_in_enum(self):
        assert GoalLifecycleState.WAITING_FOR_EVIDENCE.value == "waiting_for_evidence"

    def test_verifying_to_waiting_for_evidence_is_valid(self):
        tracker = GoalTracker("Open Photoshop")
        tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
        tracker.transition(GoalLifecycleState.PLANNED, "Planned")
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing")
        tracker.transition(GoalLifecycleState.VERIFYING, "Verifying")
        tracker.transition(GoalLifecycleState.WAITING_FOR_EVIDENCE, "Missing perception evidence")
        assert tracker.current_state == GoalLifecycleState.WAITING_FOR_EVIDENCE

    def test_waiting_for_evidence_to_reassessing_is_valid(self):
        tracker = GoalTracker("Open Photoshop")
        tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
        tracker.transition(GoalLifecycleState.PLANNED, "Planned")
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing")
        tracker.transition(GoalLifecycleState.VERIFYING, "Verifying")
        tracker.transition(GoalLifecycleState.WAITING_FOR_EVIDENCE, "Unknown conditions")
        tracker.transition(GoalLifecycleState.REASSESSING, "Re-observing environment")
        assert tracker.current_state == GoalLifecycleState.REASSESSING

    def test_waiting_for_evidence_to_replan_is_valid(self):
        tracker = GoalTracker("test")
        tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
        tracker.transition(GoalLifecycleState.PLANNED, "Planned")
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing")
        tracker.transition(GoalLifecycleState.VERIFYING, "Verifying")
        tracker.transition(GoalLifecycleState.WAITING_FOR_EVIDENCE, "Unknown")
        tracker.transition(GoalLifecycleState.REPLAN, "Investigate")
        assert tracker.current_state == GoalLifecycleState.REPLAN

    def test_waiting_for_evidence_to_executing_is_valid(self):
        """After gathering evidence, can return to executing."""
        tracker = GoalTracker("test")
        tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
        tracker.transition(GoalLifecycleState.PLANNED, "Planned")
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing")
        tracker.transition(GoalLifecycleState.VERIFYING, "Verifying")
        tracker.transition(GoalLifecycleState.WAITING_FOR_EVIDENCE, "Unknown")
        tracker.transition(GoalLifecycleState.EXECUTING, "Evidence gathered, retrying")
        assert tracker.current_state == GoalLifecycleState.EXECUTING

    def test_waiting_for_evidence_to_deferred_is_valid(self):
        tracker = GoalTracker("test")
        tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
        tracker.transition(GoalLifecycleState.PLANNED, "Planned")
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing")
        tracker.transition(GoalLifecycleState.VERIFYING, "Verifying")
        tracker.transition(GoalLifecycleState.WAITING_FOR_EVIDENCE, "Unknown")
        tracker.transition(GoalLifecycleState.DEFERRED, "Need owner input")
        assert tracker.current_state == GoalLifecycleState.DEFERRED

    def test_created_to_waiting_for_evidence_is_invalid(self):
        tracker = GoalTracker("test")
        with pytest.raises(InvalidStateTransitionError):
            tracker.transition(GoalLifecycleState.WAITING_FOR_EVIDENCE, "Too early")


# ── Verifier integration ──────────────────────────────────────────────


class TestVerifierProducesWaitingForEvidence:

    def test_unknown_conditions_produce_waiting_for_evidence(self):
        goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
        tracker = GoalTracker("Open Photoshop")
        tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
        tracker.transition(GoalLifecycleState.PLANNED, "Planned")
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing")

        # No observations → all conditions UNKNOWN
        result = GoalVerifier.verify_goal_achievement(
            goal_rep,
            executed_actions=["Launched Photoshop"],
            assistant_reply="Done.",
            tracker=tracker,
            observed_state={"entities": [], "observations": {}}
        )

        assert result.verified_success is False
        assert result.is_unknown is True
        assert result.final_state == GoalLifecycleState.WAITING_FOR_EVIDENCE
        assert tracker.current_state == GoalLifecycleState.WAITING_FOR_EVIDENCE

    def test_explicit_failure_still_produces_failed_not_waiting(self):
        """Explicit environmental failure → FAILED, not WAITING_FOR_EVIDENCE."""
        goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")
        tracker = GoalTracker("Open Photoshop")
        tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
        tracker.transition(GoalLifecycleState.PLANNED, "Planned")
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing")

        # Reply contains crash indicator → explicit failure condition
        result = GoalVerifier.verify_goal_achievement(
            goal_rep,
            executed_actions=["Launched Photoshop"],
            assistant_reply="Photoshop process crashed on startup.",
            tracker=tracker,
            observed_state={"entities": [], "observations": {}}
        )

        assert result.verified_success is False
        assert result.final_state == GoalLifecycleState.FAILED

    def test_achieved_still_produces_achieved(self):
        goal_rep = SemanticGoalInterpreter.interpret_goal("Open Photoshop")

        result = GoalVerifier.verify_goal_achievement(
            goal_rep,
            executed_actions=["Launched Photoshop"],
            assistant_reply="Running.",
            observed_state={
                "entities": [{"name": "photoshop.exe", "status": "running",
                              "source": "os_process_probe", "observation_type": "direct",
                              "confidence": 1.0}],
                "observations": {"photoshop.status": {
                    "value": "running", "source": "os_process_probe",
                    "confidence": 1.0, "observation_type": "direct"
                }}
            }
        )

        assert result.verified_success is True
        assert result.final_state == GoalLifecycleState.ACHIEVED
