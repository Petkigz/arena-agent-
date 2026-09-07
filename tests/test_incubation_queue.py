import sqlite3

import pytest

from app.cognition.incubation_queue import IncubationQueue, IncubationQueueError
from app.cognition.owner_decisions import OwnerDecisionStore


def decision(store, *operations):
    return store.issue(
        "incubation_authorization",
        {"expected_change_types": list(operations)},
        note="test incubation authorization",
    )


def test_incubation_requires_owner_enablement_and_persists_traceable_results(tmp_path):
    owners = OwnerDecisionStore(tmp_path / "owners.db")
    queue = IncubationQueue(tmp_path / "incubation.db", owner_decisions=owners)

    assert queue.policy().enabled is False
    with pytest.raises(PermissionError, match="owner authorization"):
        queue.enqueue("owner_question", "Clarify retention", {"question": "retain?"})

    enable = decision(owners, "configure_incubation")
    policy = queue.set_policy(
        enabled=True,
        max_items_per_slice=2,
        max_seconds_per_slice=15,
        owner_decision_id=enable.decision_id,
    )
    assert policy.enabled is True

    item = queue.enqueue(
        "unresolved_hypothesis",
        "Revisit the competing explanation",
        {"hypotheses": ["A", "B"]},
        priority=2,
    )
    claimed = queue.claim_next()
    assert claimed is not None
    assert claimed.item_id == item.item_id
    assert claimed.status == "running"
    assert claimed.attempts == 1

    completed = queue.complete(
        item.item_id,
        result_type="generated_hypothesis",
        result={"hypothesis": "A remains unresolved", "requires_evidence": True},
        trace_id="trace-incubation-1",
        evidence_ids=["evidence:prior-observation"],
        resume_token="cursor:1",
    )
    assert completed.status == "completed"
    assert completed.result_type == "generated_hypothesis"
    assert completed.resume_token == "cursor:1"
    assert completed.last_trace_id == "trace-incubation-1"
    assert queue.history(item.item_id)[-1]["trace_id"] == "trace-incubation-1"

    reopened = IncubationQueue(tmp_path / "incubation.db", owner_decisions=owners)
    assert reopened.get(item.item_id).to_dict() == completed.to_dict()
    assert reopened.policy().enabled is True


def test_incubation_budgeted_slice_is_non_executing_and_resumable(tmp_path):
    owners = OwnerDecisionStore(tmp_path / "owners.db")
    queue = IncubationQueue(tmp_path / "incubation.db", owner_decisions=owners)
    queue.set_policy(
        enabled=True,
        max_items_per_slice=1,
        max_seconds_per_slice=10,
        owner_decision_id=decision(owners, "configure_incubation").decision_id,
    )
    first = queue.enqueue("failed_strategy", "Review failed search", {"action": "search_files"})
    second = queue.enqueue("stale_belief", "Review stale state", {"belief_id": "b-1"})

    def processor(item):
        return {
            "result_type": "revised_belief",
            "result": {"item": item.item_id, "changed": True},
            "trace_id": f"trace:{item.item_id}",
            "evidence_ids": [f"evidence:{item.item_id}"],
            "resume_token": "next:1",
        }

    result = queue.run_slice(processor)
    assert result["processed"] == 1
    assert result["execution_performed"] is False
    assert queue.get(first.item_id).status == "completed"
    assert queue.get(second.item_id).status == "queued"

    resumed = queue.resume(first.item_id)
    assert resumed.status == "queued"
    assert resumed.resume_token == "next:1"
    assert resumed.last_trace_id == f"trace:{first.item_id}"


def test_running_incubation_can_be_cancelled_and_cannot_claim_success(tmp_path):
    owners = OwnerDecisionStore(tmp_path / "owners.db")
    queue = IncubationQueue(tmp_path / "incubation.db", owner_decisions=owners)
    queue.set_policy(enabled=True, owner_decision_id=decision(owners, "configure_incubation").decision_id)
    item = queue.enqueue("owner_question", "Pending owner question", {"question": "approve?"})
    assert queue.claim_next().item_id == item.item_id

    requested = queue.cancel(item.item_id, reason="foreground work resumed")
    assert requested.cancel_requested is True
    assert requested.status == "running"
    cancelled = queue.complete(
        item.item_id,
        result_type="new_observation",
        result={"observation": "should not be committed"},
        trace_id="trace-cancelled",
        evidence_ids=["evidence:cancel-check"],
    )
    assert cancelled.status == "cancelled"
    assert cancelled.result_type is None
    assert queue.history(item.item_id)[-1]["event_type"] == "cancelled"


def test_owner_control_exposes_incubation_queue_contract():
    from app.main import app

    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}
    assert ("/owner-control/incubation", "GET") in routes
    assert ("/owner-control/incubation/policy", "PUT") in routes
    assert ("/owner-control/incubation/items", "POST") in routes
    assert ("/owner-control/incubation/items/{item_id}/cancel", "POST") in routes
    assert ("/owner-control/incubation/items/{item_id}/resume", "POST") in routes


def test_ambiguous_or_unsupported_incubation_inputs_fail_closed(tmp_path):
    owners = OwnerDecisionStore(tmp_path / "owners.db")
    queue = IncubationQueue(tmp_path / "incubation.db", owner_decisions=owners)
    with pytest.raises(IncubationQueueError, match="unsupported incubation kind"):
        queue.enqueue("execute_action", "Never execute", {})
    with pytest.raises(IncubationQueueError, match="trace_id"):
        queue.complete(
            "missing",
            result_type="unknown",
            result={},
            trace_id="",
            evidence_ids=["evidence:x"],
        )

    with sqlite3.connect(tmp_path / "unsupported.db") as conn:
        conn.execute(
            "CREATE TABLE incubation_meta "
            "(singleton INTEGER PRIMARY KEY, storage_schema_version INTEGER NOT NULL, enabled INTEGER NOT NULL, "
            "max_items_per_slice INTEGER NOT NULL, max_seconds_per_slice INTEGER NOT NULL, updated_at TEXT NOT NULL, decision_id TEXT)"
        )
        conn.execute("INSERT INTO incubation_meta VALUES (1, 99, 0, 3, 30, 'now', NULL)")
    with pytest.raises(IncubationQueueError, match="unsupported incubation store"):
        IncubationQueue(tmp_path / "unsupported.db", owner_decisions=owners)
