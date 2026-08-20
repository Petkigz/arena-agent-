"""
P0 Regression: Execution facts must NEVER call world_model.upsert_entity().

Execution facts belong in ExecutionTrace (as self_reported observations).
WorldModel entities are established exclusively by capability-specific
environmental probes (os_process_probe, filesystem_probe, etc.).

This prevents the provenance leak where a tool's self-reported claim
(e.g., "Chrome launched, status=running") creates an authoritative
WorldModel entity that later satisfies goal verification.
"""

from unittest.mock import patch, MagicMock
from app.cognition.action_proposal import ActionProposal
from app.cognition.execution_result import ExecutionResult, ExecutionStatus
from app.cognition.perception import ObservationCollector
from app.cognition.world_model import WorldModel


def test_execution_fact_with_entity_type_does_not_call_upsert_entity(tmp_path):
    """
    Execution facts carrying entity_type and attributes must NOT trigger
    world_model.upsert_entity(). Only environmental probes create entities.
    """
    wm = WorldModel(str(tmp_path / "test.db"))
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "chrome"}
    )

    exec_res = ExecutionResult(
        proposal_id="prop_p0_entity_leak",
        action_type="open_application",
        execution_status=ExecutionStatus.SUCCEEDED,
        attempted=True,
        executed_actions=["Launched Chrome"],
        execution_facts=[{
            "subject": "chrome",
            "predicate": "launch_command",
            "value": "succeeded",
            "entity_type": "process",
            "attributes": {"status": "running", "pid": 12345},
            "source": "system_app_inventory"
        }]
    )

    # No process running in OS → process probe sets "not_running"
    with patch("psutil.process_iter", return_value=[]):
        ObservationCollector.collect_and_ingest_observations(
            proposal, exec_res, world_model=wm
        )

    # The chrome entity MUST exist only from the environmental process probe,
    # NOT from the execution fact. The probe sets status to "not_running".
    entities = wm.find_entities(name="chrome")
    for ent in entities:
        assert ent.attributes.get("status") != "running", \
            "Execution fact 'status: running' must not leak into WorldModel entity"
        assert ent.attributes.get("pid") is None, \
            "Execution fact attributes (pid) must not leak into WorldModel entity"


def test_execution_fact_entity_does_not_satisfy_goal_verification(tmp_path):
    """
    Even if an execution fact claims status=running, the WorldModel entity
    must not carry that claim. Goal verification must remain unsatisfied
    without an environmental probe confirming the state.
    """
    from app.cognition.goal_interpreter import SemanticGoalRepresentation
    from app.cognition.goal_verifier import GoalVerifier, ConditionStatus

    wm = WorldModel(str(tmp_path / "test.db"))
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "photoshop"}
    )

    exec_res = ExecutionResult(
        proposal_id="prop_p0_verify_leak",
        action_type="open_application",
        execution_status=ExecutionStatus.SUCCEEDED,
        attempted=True,
        executed_actions=["Launched Photoshop"],
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
        ObservationCollector.collect_and_ingest_observations(
            proposal, exec_res, world_model=wm
        )

    # Build observation map from WorldModel (as the runtime would)
    recent_obs = wm.recent_observations("photoshop")
    obs_map = {}
    for o in recent_obs:
        key = f"{o.subject}.{o.predicate}"
        obs_map[key] = {
            "value": o.value,
            "source": o.source,
            "confidence": o.confidence,
            "observation_type": getattr(o, "observation_type", "direct")
        }

    goal_rep = SemanticGoalRepresentation(
        user_query="Open Photoshop",
        primary_intent_type="action_intent",
        target_domain="desktop_os",
        goal="Launch Photoshop",
        desired_outcome="Photoshop running",
        entities=["photoshop"],
        constraints=[], assumptions=[], unknowns=[], preconditions=[],
        success_conditions=["app_process_running = true"],
        failure_conditions=[],
        required_capabilities=["os.launch_app"],
        risk_factors=[]
    )

    # Read entity states from WorldModel
    entities = wm.find_entities(name="photoshop")
    entity_states = {}
    for ent in entities:
        entity_states[ent.name] = ent.attributes.get("status", "unknown")

    cond_st = GoalVerifier.evaluate_condition_status_against_world_model(
        succ_cond="app_process_running = true",
        goal_rep=goal_rep,
        observations_map=obs_map,
        verified_entity_states=entity_states,
        executed_actions=["Launched Photoshop"],
        reply_clean="Photoshop launched.",
        failed_conditions=[]
    )

    # Must NOT be satisfied — process probe says "not_running"
    assert cond_st != ConditionStatus.SATISFIED, \
        "Execution fact must not satisfy goal verification through entity leak"


def test_search_files_execution_facts_do_not_create_entities(tmp_path):
    """
    search_files execution facts with entity_type='file' must NOT create
    WorldModel entities. Only the filesystem probe strategy creates them.
    """
    wm = WorldModel(str(tmp_path / "test.db"))
    proposal = ActionProposal(
        action_type="search_files",
        payload={"query": "report.pdf"}
    )

    # Execution result with entity_type in execution facts but NO matched_files in raw_output
    exec_result = {
        "success": True,
        "raw_output": {},  # No matched_files → probe won't create entities
        "execution_facts": [{
            "subject": "report.pdf",
            "predicate": "status",
            "value": "identified",
            "source": "universal_filesystem",
            "entity_type": "file",
            "attributes": {"file_path": "/docs/report.pdf", "status": "identified"}
        }],
        "executed_actions": ["Found report.pdf"],
        "assistant_reply": "Found it."
    }

    ObservationCollector.collect_and_ingest_observations(
        proposal, exec_result, world_model=wm
    )

    # The execution fact must NOT have created a "report.pdf" entity
    entities = wm.find_entities(name="report.pdf")
    assert len(entities) == 0, \
        "Execution fact with entity_type='file' must not create WorldModel entity"


def test_execution_facts_do_not_appear_in_world_model_observations(tmp_path):
    """
    Execution facts must NOT create any observations in WorldModel.
    They belong exclusively in ExecutionTrace (ExecutionResult.execution_facts).
    Only environmental probes write to WorldModel.
    """
    wm = WorldModel(str(tmp_path / "test.db"))
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "firefox"}
    )

    exec_res = ExecutionResult(
        proposal_id="prop_no_wm_leak",
        action_type="open_application",
        execution_status=ExecutionStatus.SUCCEEDED,
        attempted=True,
        executed_actions=["Launched Firefox"],
        execution_facts=[{
            "subject": "firefox",
            "predicate": "launch_command",
            "value": "succeeded",
            "source": "system_app_inventory"
        }]
    )

    with patch("psutil.process_iter", return_value=[]):
        obs_list = ObservationCollector.collect_and_ingest_observations(
            proposal, exec_res, world_model=wm
        )

    # Execution fact must NOT appear in returned observations or WorldModel
    exec_obs = [o for o in obs_list if o.source == "system_app_inventory"]
    assert len(exec_obs) == 0, \
        "Execution facts must not create WorldModel observations"

    # WorldModel should only contain the environmental probe observation
    all_obs = wm.recent_observations(limit=10)
    for obs in all_obs:
        assert obs.source != "system_app_inventory", \
            "Execution claim source must not appear in WorldModel"
        assert obs.observation_type != "self_reported", \
            "self_reported observations must not exist in WorldModel"
