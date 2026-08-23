"""The authoritative runtime exposes live evidence-backed self-knowledge."""

from unittest.mock import patch

from app.cognition.runtime import CognitiveRuntime
from app.main import (
    ExplicitCommitmentRequest,
    create_explicit_commitment_endpoint,
    self_awareness_endpoint,
    self_agency_history_endpoint,
    self_commitments_endpoint,
)


def test_runtime_seeds_live_self_knowledge(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "runtime.db"))

    snapshot = runtime.refresh_self_knowledge()["snapshot"]
    claims = {item["predicate"]: item for item in snapshot["claims"]}

    assert claims["capabilities.registered_tool_count"]["value"] >= 100
    assert claims["capabilities.registered_tool_count"]["source_type"] == "capability_probe"
    assert claims["authority.owner_policy"]["evidence"]
    assert claims["consciousness.evidence_available"]["value"] is False
    assert all(item["evidence"] for item in snapshot["claims"])


def test_self_awareness_api_is_grounded_and_disclaimed(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "runtime.db"))
    runtime.self_knowledge.attribute_change(
        "Unverified nearby event", execution_id="exec-x",
        execution_attempted=True, evidence=["timestamp"],
    )

    with patch("app.cognition.runtime.CognitiveRuntime.get_instance", return_value=runtime):
        report = self_awareness_endpoint(refresh=False)
        agency = self_agency_history_endpoint(limit=10)
        created = create_explicit_commitment_endpoint(
            ExplicitCommitmentRequest(title="Finish owner review", source_id="review-1")
        )
        commitments = self_commitments_endpoint(
            refresh=False, status_filter="active", limit=10
        )

    assert report["success"] is True
    assert report["self_knowledge"]["claims"]
    assert "does not demonstrate consciousness" in report["disclaimer"]
    assert agency["attributions"][0]["cause_type"] == "unknown"
    assert created["commitment"]["source_type"] == "explicit_owner"
    assert commitments["commitments"][0]["title"] == "Finish owner review"
