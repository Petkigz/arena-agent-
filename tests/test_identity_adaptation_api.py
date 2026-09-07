"""Owner-control API wiring for Phase 8 identity adaptation."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.cognition.identity_adaptation import IdentityAdaptationStore
from app.cognition.runtime import CognitiveRuntime


class _OwnerDecisions:
    def validate(self, decision_id, *, decision_type, claimed_change_types, consume=True):
        if not str(decision_id).startswith("owner-"):
            return {"valid": False, "reasons": ["unknown_decision"]}
        return {"valid": True, "reasons": [], "single_use_consumed": consume}


def test_identity_adaptation_owner_routes_are_wired_and_owner_visible(tmp_path, monkeypatch):
    from app.main import app

    store = IdentityAdaptationStore(
        tmp_path / "identity.db",
        owner_decisions=_OwnerDecisions(),
    )
    runtime = SimpleNamespace(identity_adaptation=store)
    monkeypatch.setattr(
        CognitiveRuntime,
        "get_instance",
        classmethod(lambda cls: runtime),
    )
    monkeypatch.setenv("ARENA_API_KEY", "phase8-test-key")
    client = TestClient(app)
    headers = {"X-API-Key": "phase8-test-key"}

    for index, feedback in enumerate(("not_helpful", "partially_helpful", "not_helpful")):
        response = client.post(
            "/owner-control/identity-style/feedback",
            headers=headers,
            json={
                "feedback": feedback,
                "trace_id": f"trace-feedback-{index}",
                "evidence_ids": [f"feedback:{index}"],
            },
        )
        assert response.status_code == 200
        assert response.json()["adaptation_automatic"] is False

    suggestion = client.post(
        "/owner-control/identity-style/suggest",
        headers=headers,
        json={
            "candidate_patch": {"verbosity": "concise"},
            "reason": "repeated feedback requested shorter responses",
            "trace_id": "trace-style-suggestion",
            "evidence_ids": ["feedback:0", "feedback:1", "feedback:2"],
        },
    )
    assert suggestion.status_code == 200
    assert suggestion.json()["suggestion"]["status"] == "proposal_created"
    assert suggestion.json()["suggestion"]["requires_owner_decision"] is True

    metrics = client.get("/owner-control/identity-style/metrics", headers=headers)
    assert metrics.status_code == 200
    assert metrics.json()["metrics"]["known_feedback_count"] == 3

    purpose = client.post(
        "/owner-control/purpose-proposals",
        headers=headers,
        json={
            "title": "Explore recovery evidence",
            "description": "Propose a bounded recovery-evidence review.",
            "provenance": "exploratory_proposal",
            "sandbox": False,
            "trace_id": "trace-purpose",
            "evidence_ids": ["purpose:evidence"],
        },
    )
    assert purpose.status_code == 200
    purpose_body = purpose.json()
    proposal = purpose_body["proposal"]
    assert purpose_body["execution_authority"] == "none"
    assert proposal["sandbox"] is True

    listed = client.get("/owner-control/purpose-proposals", headers=headers)
    assert listed.status_code == 200
    assert any(item["proposal_id"] == proposal["proposal_id"] for item in listed.json()["proposals"])

    adopted = client.post(
        f"/owner-control/purpose-proposals/{proposal['proposal_id']}/adopt",
        headers=headers,
        json={"owner_decision_id": "owner-purpose"},
    )
    assert adopted.status_code == 200
    assert adopted.json()["proposal"]["status"] == "adopted"
    assert adopted.json()["execution_authority"] == "none"

    policy = client.get("/owner-control/shutdown-policy", headers=headers)
    assert policy.status_code == 200
    assert policy.json()["shutdown_execution_authority"] == "none"

    assessment = client.post(
        "/owner-control/shutdown-assessment",
        headers=headers,
        json={
            "requested": True,
            "completion_observed": True,
            "trace_id": "trace-shutdown-api",
            "evidence_ids": ["shutdown:receipt"],
        },
    )
    assert assessment.status_code == 200
    assert assessment.json()["assessment"]["status"] == "verified_cooperative"
