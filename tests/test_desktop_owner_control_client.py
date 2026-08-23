"""Desktop Owner Control calls preserve stage-specific API boundaries."""

import json

import httpx

from desktop.backend_client import ArenaBackendClient


def test_desktop_owner_control_uses_separate_decision_and_execution_routes():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        if request.url.path == "/owner-control":
            return httpx.Response(200, json={"policy": {"mode": "suggest_only"}})
        return httpx.Response(200, json={"success": True})

    client = ArenaBackendClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=1)

    client.owner_control()
    client.update_owner_control({"mode": "approve_every_action"})
    client.set_emergency_pause(True)
    client.decide_approval("action/1", True, "reviewed")
    client.active_authorizations()
    client.execute_authorized("grant/1", "create_note", {"title": "Exact"})
    client.revoke_authorization("grant/2")
    client.edit_plan("plan/1", 4, [{"step_id": "step-1"}])
    client.decide_plan("plan/1", 4, True, "reviewed")
    client.execute_plan("plan/1")
    client.cancel_execution("exec/1")
    client.request_rollback("exec/1")
    client.set_exploration_budget(2)
    client.close()

    assert requests == [
        ("GET", "/owner-control", None),
        ("PUT", "/owner-control", {"mode": "approve_every_action"}),
        ("POST", "/owner-control/pause", {"paused": True}),
        ("POST", "/owner-control/approvals/action/1/decision", {"approved": True, "note": "reviewed", "ttl_seconds": 300}),
        ("GET", "/owner-control/authorizations", None),
        ("POST", "/owner-control/execute-authorized", {
            "authorization_id": "grant/1", "action_type": "create_note",
            "payload": {"title": "Exact"}, "user_text": "Desktop owner-authorized action",
            "complexity": "fast", "plan_id": None,
        }),
        ("DELETE", "/owner-control/authorizations/grant/2", None),
        ("PUT", "/owner-control/plans/plan/1", {"expected_revision": 4, "steps": [{"step_id": "step-1"}]}),
        ("POST", "/owner-control/plans/plan/1/decision", {"expected_revision": 4, "approved": True, "note": "reviewed"}),
        ("POST", "/owner-control/plans/plan/1/execute", {}),
        ("POST", "/owner-control/executions/exec/1/cancel", {}),
        ("POST", "/owner-control/executions/exec/1/request-rollback", {}),
        ("PUT", "/owner-control/adaptive-autonomy/exploration-budget", {"max_exploration_goals": 2}),
    ]
