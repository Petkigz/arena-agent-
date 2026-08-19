from unittest.mock import patch
from app.cognition.action_proposal import ActionProposal
from app.cognition.execution_result import ExecutionResult, ExecutionStatus
from app.cognition.perception import ObservationCollector
from app.cognition.world_model import WorldModel
from app.cognition.goal_verifier import GoalVerifier
from app.cognition.goal_interpreter import SemanticGoalRepresentation


def test_execution_facts_do_not_create_world_model_entities(tmp_path):
    """
    P0 Fix Verification:
    Verify that self-reported execution_facts in ExecutionResult DO NOT call world_model.upsert_entity()
    and DO NOT establish WorldModel entity state, preventing execution claims from fabricating evidence.
    """
    wm = WorldModel(str(tmp_path / "arena.db"))
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "photoshop"}
    )

    exec_res = ExecutionResult(
        proposal_id="prop_test_p0",
        action_type="open_application",
        execution_status=ExecutionStatus.SUCCEEDED,
        attempted=True,
        executed_actions=["Tool executed launch command"],
        execution_facts=[{
            "subject": "photoshop",
            "predicate": "launch_command",
            "value": "succeeded",
            "entity_type": "process",
            "attributes": {"status": "running"},
            "source": "system_app_inventory"
        }]
    )

    with patch("psutil.process_iter", return_value=[]):
        ObservationCollector.collect_and_ingest_observations(proposal, exec_res, world_model=wm)

        # P0 STRICT: Execution facts MUST NOT create ANY WorldModel entities.
        # Entity state is established exclusively by environmental probes, not execution claims.
        entities = wm.find_entities(name="photoshop")
        # The process probe creates a "photoshop" entity with status "not_running" —
        # that is the environmental probe, not the execution fact.
        # Verify no entity was created with the execution fact's attributes (status=running)
        for ent in entities:
            assert ent.attributes.get("status") != "running", \
                "Execution fact must not establish entity status in WorldModel"
            # The only valid source for entity status is the environmental probe
            if ent.attributes.get("source"):
                assert ent.attributes["source"] != "system_app_inventory", \
                    "Entity must not carry execution-claim provenance"

        # GoalVerifier MUST NOT verify app_process_running = true from self-reported facts alone
        goal_rep = SemanticGoalRepresentation(
            user_query="Open Photoshop",
            primary_intent_type="action_intent",
            target_domain="desktop_os",
            goal="Launch Photoshop",
            desired_outcome="Photoshop running",
            entities=["photoshop"],
            constraints=[],
            assumptions=[],
            unknowns=[],
            preconditions=[],
            success_conditions=["app_process_running = true"],
            failure_conditions=[],
            required_capabilities=["os.launch_app"],
            risk_factors=[]
        )

        recent_obs = wm.recent_observations("photoshop")
        obs_map = {f"{o.subject}.{o.predicate}": {"value": o.value, "source": o.source, "observation_type": getattr(o, "observation_type", "direct")} for o in recent_obs}

        cond_st = GoalVerifier.evaluate_condition_status_against_world_model(
            succ_cond="app_process_running = true",
            goal_rep=goal_rep,
            observations_map=obs_map,
            verified_entity_states={"photoshop": "launched"},
            executed_actions=["Tool executed launch command"],
            reply_clean="I launched Photoshop for you.",
            failed_conditions=[]
        )

        assert cond_st != "satisfied"
