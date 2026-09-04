"""The manifest-execution bridge in MasterAgentOrchestrator.execute_proposal.

D6 live failure (owner run 2026-09-04): the forced synthesize_tool
proposal — routed correctly by the manifest-first matcher — died in
execute_proposal's 'unsupported capability' dead end (no elif branch, no
dynamic registration), and the replanner papered over the gap with a
conversational answer while the tool was never installed. The manifest
is the authority for what EXISTS: a gated-and-approved action with a
manifest handler must execute through it, succeed or fail honestly."""

from types import SimpleNamespace

from app.agents.master_agent import MasterAgentOrchestrator
from app.tools.manifest import get_tool_manifest


def _bridge_entry(handler):
    return {
        "name": "test_bridge_tool",
        "category": "test",
        "safety_level": 0,
        "description": "test bridge handler",
        "handler": handler,
        "availability": None,
    }


def test_manifest_handler_success_reaches_the_action_record(monkeypatch):
    manifest = get_tool_manifest()
    seen = {}

    def handler(payload):
        seen.update(payload)
        return {"success": True, "installed": payload.get("capability_name")}

    monkeypatch.setitem(manifest, "test_bridge_tool", _bridge_entry(handler))
    result = MasterAgentOrchestrator.execute_proposal(
        SimpleNamespace(action_type="test_bridge_tool",
                        payload={"capability_name": "reverse_words"},
                        proposal_id="prop_bridge_1"),
        "Create a new tool called reverse_words.",
    )
    assert result.execution_status.value == "succeeded", result.to_dict()
    assert seen.get("capability_name") == "reverse_words", (
        "the payload must actually reach the manifest handler")
    # The dispatcher may reach the handler via the shared registry (which
    # seeds/falls back to the manifest) or via the direct manifest bridge —
    # what matters is the handler RAN and the action was recorded.
    assert any("test_bridge_tool" in str(a) and "Executed" in str(a)
               for a in result.executed_actions), result.executed_actions


def test_manifest_handler_failure_is_honest_not_conversational(monkeypatch):
    """A failing manifest handler must surface its error as a FAILED
    execution — not silently fall through to a formulated answer, which
    is exactly how D6's 'tool NOT installed' masqueraded as progress."""
    manifest = get_tool_manifest()

    def handler(payload):
        return {"success": False, "error": "sandbox verification rejected the code"}

    monkeypatch.setitem(manifest, "test_bridge_tool", _bridge_entry(handler))
    result = MasterAgentOrchestrator.execute_proposal(
        SimpleNamespace(action_type="test_bridge_tool",
                        payload={"capability_name": "reverse_words"},
                        proposal_id="prop_bridge_2"),
        "Create a new tool called reverse_words.",
    )
    assert result.execution_status.value == "failed", result.to_dict()
    assert "sandbox verification rejected" in str(result.to_dict().get("error", "")), (
        result.to_dict())


def test_truly_unknown_action_stays_unsupported(monkeypatch):
    """The bridge must not turn the honest 'unsupported' answer into a
    blanket manifest miss: an action with NO manifest entry and NO
    registration still fails as unsupported."""
    manifest = get_tool_manifest()
    monkeypatch.delitem(manifest, "test_bridge_tool", raising=False)
    result = MasterAgentOrchestrator.execute_proposal(
        SimpleNamespace(action_type="no_such_capability_anywhere",
                        payload={}, proposal_id="prop_bridge_3"),
        "Do something impossible.",
    )
    assert result.execution_status.value == "failed"
    assert "unsupported" in str(result.to_dict().get("error", "")).lower()
