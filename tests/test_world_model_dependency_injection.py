from unittest.mock import MagicMock, patch
from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal
from app.cognition.perception import ObservationCollector
from app.cognition.environment_grounding import EnvironmentGroundingEngine
from app.memory.semantic_rag import SemanticRAGEngine


def test_execute_proposal_and_observation_collector_use_injected_world_model():
    """
    P1 Fix Verification:
    Verify that execute_proposal and ObservationCollector accept and use the injected
    WorldModel instance, rather than instantiating a new WorldModel(DB_PATH).
    """
    mock_wm = MagicMock()
    proposal = ActionProposal(
        action_type="open_application",
        payload={"app_name": "photoshop"}
    )

    with patch("app.tools.app_inventory.SystemAppInventory.launch_any_app", return_value={"success": True, "app_name": "photoshop"}):
        res = MasterAgentOrchestrator.execute_proposal(
            proposal, user_text="Open Photoshop", world_model=mock_wm
        )
        assert res["success"] is True

        ObservationCollector.collect_and_ingest_observations(
            proposal, res, world_model=mock_wm
        )

        # Injected mock WorldModel MUST be used directly
        assert mock_wm.observe.call_count >= 1
        assert mock_wm.upsert_entity.call_count >= 1


def test_environment_grounding_uses_injected_world_model():
    """
    Verify EnvironmentGroundingEngine uses injected WorldModel instance.
    """
    mock_wm = MagicMock()
    EnvironmentGroundingEngine.probe_complete_environment(world_model=mock_wm)

    assert mock_wm.upsert_entity.call_count >= 1
    assert mock_wm.observe.call_count >= 1


def test_semantic_rag_uses_injected_world_model():
    """
    Verify SemanticRAGEngine uses injected WorldModel instance.
    """
    mock_wm = MagicMock()

    class _FakeEntity:
        name = "photoshop"
        entity_type = "app"

    mock_wm.find_entities.return_value = [_FakeEntity()]

    ctx = SemanticRAGEngine.build_rag_context("photoshop", limit=1, world_model=mock_wm)

    assert mock_wm.find_entities.call_count == 1
    assert "photoshop" in ctx.lower()
    # The injected world model must be used (not a fresh WorldModel instantiation).
    assert mock_wm.find_entities.call_args[1].get("name") == "photoshop"
