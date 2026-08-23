"""The authoritative runtime exposes live evidence-backed self-knowledge."""

from unittest.mock import patch

from app.cognition.runtime import CognitiveRuntime
from app.main import (
    ExplicitCommitmentRequest,
    create_explicit_commitment_endpoint,
    self_awareness_endpoint,
    self_agency_history_endpoint,
    self_belief_revisions_endpoint,
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
    boundary = runtime.embodied_boundary.snapshot()
    ids = {item["interface_id"] for item in boundary["interfaces"]}
    assert {"desktop_screen", "desktop_pointer", "local_camera", "android_phone"} <= ids


def test_self_awareness_api_is_grounded_and_disclaimed(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "runtime.db"))
    runtime.self_knowledge.attribute_change(
        "Unverified nearby event", execution_id="exec-x",
        execution_attempted=True, evidence=["timestamp"],
    )
    runtime.self_knowledge.assert_claim(
        "capabilities.registered_tool_count", 999,
        source_type="capability_probe", evidence=["test changed probe"],
        confidence=1.0,
    )

    with patch("app.cognition.runtime.CognitiveRuntime.get_instance", return_value=runtime):
        report = self_awareness_endpoint(refresh=False)
        agency = self_agency_history_endpoint(limit=10)
        revisions = self_belief_revisions_endpoint(
            predicate="capabilities.registered_tool_count", limit=10
        )
        created = create_explicit_commitment_endpoint(
            ExplicitCommitmentRequest(title="Finish owner review", source_id="review-1")
        )
        commitments = self_commitments_endpoint(
            refresh=False, status_filter="active", limit=10
        )

    assert report["success"] is True
    assert report["self_knowledge"]["claims"]
    assert "competence_calibration" in report
    assert "does not demonstrate consciousness" in report["disclaimer"]
    assert revisions["revisions"][0]["change_type"] == "contradiction"
    assert agency["attributions"][0]["cause_type"] == "unknown"
    assert created["commitment"]["source_type"] == "explicit_owner"
    assert commitments["commitments"][0]["title"] == "Finish owner review"
