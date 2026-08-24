"""Owner authority: consideration, recommendation, authorization, execution stay separate."""

from unittest.mock import patch

import pytest

from app.cognition.action_planner import ActionPlanner
from app.cognition.action_proposal import ActionGate, ActionProposal


@pytest.fixture(autouse=True)
def hermetic_default_owner_policy(monkeypatch):
    """Pin the ambient owner-control singleton to defaults so stage-separation
    tests do not depend on the developer machine's live owner policy file."""
    from app.cognition.owner_control import OwnerControlPolicy, owner_control_store
    monkeypatch.setattr(owner_control_store, "_policy", OwnerControlPolicy())


class _ResourceManager:
    def get_usage_report(self):
        return {"budgets": {}}


def _plan_with_restricted_alternative() -> ActionProposal:
    # Keep this unit test focused on stage separation rather than loading every
    # optional tool handler in the full manifest.
    manifest = {
        "read_file": {"safety_level": 0},
        "send_email": {"safety_level": 3},
    }
    with patch("app.tools.manifest.get_tool_manifest", return_value=manifest):
        return ActionPlanner.plan_and_evaluate_action(
            "Compare ways to communicate the result",
            candidates=[
                {
                    "name": "Inspect a local draft",
                    "action_type": "read_file",
                    "payload": {"file_path": "README.md"},
                },
                {
                    "name": "Send the result externally",
                    "action_type": "send_email",
                    "payload": {"to": "owner@example.test", "body": "result"},
                },
            ],
            hardware_self_model={},
            resource_manager=_ResourceManager(),
        )


def test_planner_preserves_ranked_restricted_alternatives():
    proposal = _plan_with_restricted_alternative()

    assert proposal.decision_stage == "recommendation"
    assert len(proposal.alternatives_considered) == 2
    assert [a["rank"] for a in proposal.alternatives_considered] == [1, 2]

    send = next(a for a in proposal.alternatives_considered if a["action_type"] == "send_email")
    assert send["authorization_requirement"] == "explicit_owner_approval"
    assert set(send["consequences"]) >= {
        "expected_benefit", "risk", "uncertainty", "reversible", "predicted_state_change"
    }


def test_restricted_alternative_does_not_block_selected_safe_recommendation():
    proposal = _plan_with_restricted_alternative()
    # The safe branch is first on an equal utility score and is recommended.
    assert proposal.action_type == "read_file"
    assert any(
        a["authorization_requirement"] == "explicit_owner_approval"
        for a in proposal.alternatives_considered
    )

    with (
        patch(
            "app.cognition.action_proposal.HardwareMonitor.get_hardware_stats",
            return_value={"ram_used_percent": 20.0},
        ),
        patch(
            "app.tools.manifest.get_tool_manifest",
            return_value={"read_file": {"safety_level": 0}},
        ),
    ):
        result = ActionGate.evaluate_proposal(proposal)

    assert result.allowed is True
    assert result.decision_stage == "authorized"
    assert proposal.decision_stage == "authorized"


def test_recommending_restricted_action_does_not_authorize_it():
    proposal = ActionProposal(
        action_type="send_email",
        payload={"to": "owner@example.test", "body": "result"},
        recommendation_reason="Useful because it delivers the result immediately.",
    )

    with patch(
        "app.tools.manifest.get_tool_manifest",
        return_value={"send_email": {"safety_level": 3}},
    ):
        result = ActionGate.evaluate_proposal(proposal)

    assert result.allowed is False
    assert result.requires_approval is True
    assert result.decision_stage == "awaiting_authorization"
    assert proposal.decision_stage == "awaiting_authorization"
