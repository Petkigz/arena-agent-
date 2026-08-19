"""
Finding #6 Regression Tests: Primitive Observation Provenance Enforcement.

Verifies that primitive (non-dict) observation values are NOT treated as
authoritative evidence. Both positive ("running") and negative ("crashed")
primitive values resolve to UNKNOWN, requiring structured provenance metadata
(source, observation_type, confidence) to satisfy or fail conditions.

Also verifies the secondary loophole is closed: entity states stored as
primitive strings are NOT wrapped in fabricated provenance dicts.
"""

import pytest
from app.cognition.goal_interpreter import SemanticGoalRepresentation
from app.cognition.goal_verifier import GoalVerifier, ConditionStatus
from app.cognition.goal_lifecycle import GoalLifecycleState


def _make_process_goal(entity="photoshop"):
    return SemanticGoalRepresentation(
        user_query=f"Open {entity.title()}",
        primary_intent_type="action_intent",
        target_domain="desktop_os",
        goal=f"Launch {entity.title()}",
        desired_outcome=f"{entity.title()} running",
        entities=[entity],
        constraints=[],
        assumptions=[],
        unknowns=[],
        preconditions=[],
        success_conditions=["app_process_running = true"],
        failure_conditions=[],
        required_capabilities=["os.launch_app"],
        risk_factors=[]
    )


def _make_filesystem_goal(entity="report.pdf"):
    return SemanticGoalRepresentation(
        user_query=f"Find {entity}",
        primary_intent_type="search_intent",
        target_domain="filesystem",
        goal=f"Locate {entity}",
        desired_outcome=f"{entity} found",
        entities=[entity],
        constraints=[],
        assumptions=[],
        unknowns=[],
        preconditions=[],
        success_conditions=["file_path_identified = true"],
        failure_conditions=[],
        required_capabilities=["fs.search"],
        risk_factors=[]
    )


# ── Primitive positive values ──────────────────────────────────────────


class TestPrimitivePositiveObservations:
    """Primitive positive values like 'running' must NOT satisfy conditions."""

    def test_primitive_running_does_not_satisfy_process_condition(self):
        goal_rep = _make_process_goal()
        obs_map = {"photoshop.status": "running"}
        entity_states = {"photoshop": "running"}

        result = GoalVerifier.evaluate_condition_against_world_model(
            succ_cond="app_process_running = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states=entity_states,
            executed_actions=["Launched Photoshop"],
            reply_clean="Done.",
            failed_conditions=[]
        )
        assert result is False, "Primitive 'running' must not satisfy process condition"

    def test_primitive_active_does_not_satisfy_process_condition(self):
        goal_rep = _make_process_goal()
        obs_map = {"photoshop.status": "active"}

        result = GoalVerifier.evaluate_condition_against_world_model(
            succ_cond="app_process_running = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states={"photoshop": "active"},
            executed_actions=["Launched Photoshop"],
            reply_clean="Done.",
            failed_conditions=[]
        )
        assert result is False, "Primitive 'active' must not satisfy process condition"

    def test_primitive_true_bool_does_not_satisfy(self):
        goal_rep = _make_process_goal()
        obs_map = {"photoshop.status": True}

        result = GoalVerifier.evaluate_condition_against_world_model(
            succ_cond="app_process_running = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states={},
            executed_actions=["Launched Photoshop"],
            reply_clean="Done.",
            failed_conditions=[]
        )
        assert result is False, "Primitive True must not satisfy process condition"


# ── Primitive negative values ──────────────────────────────────────────


class TestPrimitiveNegativeObservations:
    """Primitive negative values like 'crashed' resolve to UNKNOWN, not FAILED."""

    def test_primitive_crashed_status_returns_unknown_not_failed(self):
        goal_rep = _make_process_goal()
        obs_map = {"photoshop.status": "crashed"}

        status = GoalVerifier.evaluate_condition_status_against_world_model(
            succ_cond="app_process_running = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states={"photoshop": "crashed"},
            executed_actions=["Launched Photoshop"],
            reply_clean="Done.",
            failed_conditions=[]
        )
        # Without provenance, primitive "crashed" is UNKNOWN, not FAILED
        assert status == ConditionStatus.UNKNOWN, \
            "Primitive 'crashed' without provenance should be UNKNOWN"

    def test_primitive_not_found_filesystem_returns_unknown(self):
        goal_rep = _make_filesystem_goal()
        obs_map = {"filesystem.file_path": "not_found"}

        status = GoalVerifier.evaluate_condition_status_against_world_model(
            succ_cond="file_path_identified = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states={},
            executed_actions=["Searched filesystem"],
            reply_clean="Done.",
            failed_conditions=[]
        )
        # Primitive "not_found" without provenance → UNKNOWN (requires structured evidence)
        assert status == ConditionStatus.UNKNOWN, \
            "Primitive 'not_found' without provenance should be UNKNOWN"


# ── Structured provenance still works ──────────────────────────────────


class TestStructuredProvenanceSatisfies:
    """Structured observations with valid provenance still satisfy conditions."""

    def test_structured_direct_process_probe_satisfies(self):
        goal_rep = _make_process_goal()
        obs_map = {
            "photoshop.status": {
                "value": "running",
                "source": "os_process_probe",
                "confidence": 1.0,
                "observation_type": "direct"
            }
        }

        result = GoalVerifier.evaluate_condition_against_world_model(
            succ_cond="app_process_running = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states={"photoshop": {
                "status": "running", "source": "os_process_probe",
                "confidence": 1.0, "observation_type": "direct"
            }},
            executed_actions=["Launched Photoshop"],
            reply_clean="Done.",
            failed_conditions=[]
        )
        assert result is True, "Structured direct provenance must satisfy"

    def test_structured_direct_negative_fails_condition(self):
        goal_rep = _make_process_goal()
        obs_map = {
            "photoshop.status": {
                "value": "crashed",
                "source": "os_process_probe",
                "confidence": 1.0,
                "observation_type": "direct"
            }
        }

        status = GoalVerifier.evaluate_condition_status_against_world_model(
            succ_cond="app_process_running = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states={"photoshop": {
                "status": "crashed", "source": "os_process_probe",
                "confidence": 1.0, "observation_type": "direct"
            }},
            executed_actions=["Launched Photoshop"],
            reply_clean="Done.",
            failed_conditions=[]
        )
        assert status == ConditionStatus.FAILED, \
            "Structured direct negative evidence must FAIL"

    def test_structured_filesystem_probe_satisfies(self):
        goal_rep = _make_filesystem_goal()
        obs_map = {
            "report.pdf.file_path": {
                "value": "/home/user/report.pdf",
                "source": "filesystem_probe",
                "confidence": 1.0,
                "observation_type": "direct"
            }
        }

        result = GoalVerifier.evaluate_condition_against_world_model(
            succ_cond="file_path_identified = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states={"report.pdf": {
                "status": "identified", "source": "filesystem_probe",
                "confidence": 1.0, "observation_type": "direct"
            }},
            executed_actions=["Searched filesystem"],
            reply_clean="Found it.",
            failed_conditions=[]
        )
        assert result is True, "Structured filesystem provenance must satisfy"


# ── Entity state provenance loophole ───────────────────────────────────


class TestEntityStateProvenanceLoophole:
    """Primitive entity states must NOT be wrapped in fabricated provenance."""

    def test_primitive_entity_state_does_not_satisfy(self):
        goal_rep = _make_process_goal()
        # No observations at all — only primitive entity state
        obs_map = {}
        entity_states = {"photoshop": "running"}

        result = GoalVerifier.evaluate_condition_against_world_model(
            succ_cond="app_process_running = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states=entity_states,
            executed_actions=["Launched Photoshop"],
            reply_clean="Done.",
            failed_conditions=[]
        )
        assert result is False, "Primitive entity state must not satisfy without provenance"

    def test_structured_entity_state_satisfies(self):
        goal_rep = _make_process_goal()
        obs_map = {}
        entity_states = {"photoshop": {
            "status": "running",
            "source": "os_process_probe",
            "confidence": 1.0,
            "observation_type": "direct"
        }}

        result = GoalVerifier.evaluate_condition_against_world_model(
            succ_cond="app_process_running = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states=entity_states,
            executed_actions=["Launched Photoshop"],
            reply_clean="Done.",
            failed_conditions=[]
        )
        assert result is True, "Structured entity state with provenance must satisfy"


# ── is_direct_provenance_evidence direct tests ────────────────────────


class TestIsDirectProvenanceEvidence:
    """Direct unit tests for the provenance enforcement function."""

    def test_primitive_string_returns_not_authorized(self):
        is_auth, val = GoalVerifier.is_direct_provenance_evidence("running")
        assert is_auth is False
        assert val == "running"

    def test_primitive_bool_returns_not_authorized(self):
        is_auth, val = GoalVerifier.is_direct_provenance_evidence(True)
        assert is_auth is False

    def test_primitive_int_returns_not_authorized(self):
        is_auth, val = GoalVerifier.is_direct_provenance_evidence(42)
        assert is_auth is False

    def test_primitive_none_returns_not_authorized(self):
        is_auth, val = GoalVerifier.is_direct_provenance_evidence(None)
        assert is_auth is False

    def test_structured_direct_probe_is_authorized(self):
        obs = {
            "value": "running",
            "source": "os_process_probe",
            "confidence": 1.0,
            "observation_type": "direct"
        }
        is_auth, val = GoalVerifier.is_direct_provenance_evidence(obs)
        assert is_auth is True
        assert val == "running"

    def test_structured_self_reported_is_not_authorized(self):
        obs = {
            "value": "running",
            "source": "execution_result",
            "confidence": 0.9,
            "observation_type": "self_reported"
        }
        is_auth, val = GoalVerifier.is_direct_provenance_evidence(obs)
        assert is_auth is False

    def test_structured_low_confidence_is_not_authorized(self):
        obs = {
            "value": "running",
            "source": "os_process_probe",
            "confidence": 0.3,
            "observation_type": "direct"
        }
        is_auth, val = GoalVerifier.is_direct_provenance_evidence(obs)
        assert is_auth is False

    def test_structured_filesystem_probe_is_authorized(self):
        obs = {
            "value": "/home/user/report.pdf",
            "source": "filesystem_probe",
            "confidence": 1.0,
            "observation_type": "direct"
        }
        is_auth, val = GoalVerifier.is_direct_provenance_evidence(obs)
        assert is_auth is True

    def test_structured_missing_observation_type_defaults_to_direct(self):
        """Dict without observation_type defaults to 'direct' — passes if source is valid."""
        obs = {
            "status": "running",
            "source": "os_process_probe",
            "confidence": 1.0
        }
        is_auth, val = GoalVerifier.is_direct_provenance_evidence(obs)
        assert is_auth is True
        assert val == "running"

    def test_external_adb_probe_is_authorized(self):
        obs = {
            "value": "device_online",
            "source": "system_probe",
            "confidence": 0.95,
            "observation_type": "environmental"
        }
        is_auth, val = GoalVerifier.is_direct_provenance_evidence(
            obs, allowed_types=["direct", "environmental"]
        )
        assert is_auth is True


# ── Full verification integration ──────────────────────────────────────


class TestFullVerificationIntegration:
    """End-to-end: primitive observations produce UNKNOWN in full verify_goal_achievement."""

    def test_primitive_observations_produce_unknown_lifecycle(self):
        from app.cognition.goal_lifecycle import GoalTracker
        goal_rep = _make_process_goal()
        tracker = GoalTracker("Open Photoshop")
        tracker.transition(GoalLifecycleState.UNDERSTOOD, "Parsed")
        tracker.transition(GoalLifecycleState.PLANNED, "Planned")
        tracker.transition(GoalLifecycleState.EXECUTING, "Executing")

        obs_state = {
            "entities": [{"name": "photoshop.exe", "type": "process", "status": "running"}],
            "observations": {"photoshop.status": "running"}
        }

        result = GoalVerifier.verify_goal_achievement(
            goal_rep,
            executed_actions=["Launched Photoshop"],
            assistant_reply="Done.",
            tracker=tracker,
            observed_state=obs_state
        )

        assert result.verified_success is False
        assert result.is_unknown is True, \
            "Primitive observations should produce UNKNOWN, not FAILED"
        assert len(result.unknown_conditions) > 0

    def test_structured_observations_produce_achieved(self):
        goal_rep = _make_process_goal()
        obs_state = {
            "entities": [{
                "name": "photoshop.exe", "type": "process", "status": "running",
                "source": "os_process_probe", "observation_type": "direct", "confidence": 1.0
            }],
            "observations": {"photoshop.status": {
                "value": "running", "source": "os_process_probe",
                "confidence": 1.0, "observation_type": "direct"
            }}
        }

        result = GoalVerifier.verify_goal_achievement(
            goal_rep,
            executed_actions=["Launched Photoshop"],
            assistant_reply="Photoshop is running.",
            observed_state=obs_state
        )

        assert result.verified_success is True
        assert result.final_state == GoalLifecycleState.ACHIEVED
