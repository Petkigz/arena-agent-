"""
Naming/safety consistency guards: the tool manifest's safety_level must be the
authoritative source the ActionGate uses, and every manifest handler must accept
a payload dict (the zero-arg classmethod bug).
"""

import inspect
from unittest.mock import patch
import pytest

from app.cognition.action_proposal import ActionGate, ActionProposal
from app.cognition.owner_control import OwnerControlStore
from app.tools.manifest import get_tool_manifest

@pytest.fixture(autouse=True)
def conservative_owner_policy(tmp_path):
    store=OwnerControlStore(tmp_path/'owner.json')
    with patch('app.cognition.action_proposal.owner_control_store',store):
        yield


def test_manifest_is_authoritative_for_safety():
    """Level 0-2 manifest tools must NOT be gated; Level 3 tools must require approval."""
    # Harmless read → allowed autonomously (was previously falling to 'unknown → Level 3').
    prop = ActionProposal(action_type="list_notes", payload={})
    res = ActionGate.evaluate_proposal(prop)
    assert res.allowed is True, f"list_notes should be allowed, got: {res.reason}"
    assert prop.safety_level == 0

    # Level 1 draft tool → allowed.
    prop2 = ActionProposal(action_type="create_note", payload={"title": "x"})
    res2 = ActionGate.evaluate_proposal(prop2)
    assert res2.allowed is True
    assert prop2.safety_level == 1

    # Level 3 sensitive → requires approval.
    prop3 = ActionProposal(action_type="send_email", payload={"to": "a@b.com"})
    res3 = ActionGate.evaluate_proposal(prop3)
    assert res3.allowed is False
    assert res3.requires_approval is True

    # Other Level 3 tools must also gate.
    for level3 in ("phone_sms", "phone_call", "git_rollback", "lab_scan", "system_update", "trigger_webhook"):
        p = ActionProposal(action_type=level3, payload={})
        r = ActionGate.evaluate_proposal(p)
        assert r.allowed is False, f"{level3} should require approval"
        assert r.requires_approval is True


def test_all_manifest_handlers_accept_payload():
    """Every manifest handler must take exactly one payload-dict argument."""
    bad = []
    for action, entry in get_tool_manifest().items():
        try:
            params = list(inspect.signature(entry["handler"]).parameters)
            if len(params) != 1 or params[0] not in ("payload", "p"):
                bad.append((action, params))
        except (ValueError, TypeError) as e:
            bad.append((action, str(e)))
    assert bad == [], f"handlers with wrong signature: {bad}"


def test_zero_arg_tools_execute_with_empty_payload():
    """Previously-broken zero-arg tools must execute with an empty payload."""
    m = get_tool_manifest()
    for action in ("list_notes", "list_apps", "list_workspace", "list_events",
                   "due_reminders", "list_windows", "read_inbox"):
        result = m[action]["handler"]({})
        # These return a list or dict; just assert no exception.
        assert isinstance(result, (list, dict)), f"{action} returned {type(result)}"
