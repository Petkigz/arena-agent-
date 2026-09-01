"""P1 (live 2026-09-01, D6, owner review item 4): self-evolution claimed
"Successfully created reverse_words and tested it" while
registry.effective_capability("reverse_words") did not exist.

Root cause (reproduced offline): the synthesis pipeline existed but was
DISCONNECTED — SelfEvolvingAgent wrote modules with execute_tool() into
app/tools/ and 'plugins' whose SHAPE PluginRegistry rejects (no NAME /
no execute), so nothing was ever installed as a capability; nothing
routed capability-creation requests to the synthesizer; and the
verifier resolved 'capability_installed' as UNKNOWN (waiting) instead
of probing the registry.

The prescribed architecture is now real, end to end:

  generate (LLM) -> write -> sandbox syntax/execution tests ->
  REGISTRY INSTALLATION (PluginRegistry-shaped file + live
  register_tool) -> registry lookup -> execute the INSTALLED
  capability -> verify -> only then success

and installation is a HARD success condition: the GoalVerifier probes
the shared registry — a nameable capability that is NOT registered is
FAILED (the registry is authoritative; absence is direct evidence,
not 'waiting for evidence'), so a plan-document reply can never
achieve the goal.
"""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_lifecycle import GoalLifecycleState
from app.cognition.goal_verifier import GoalVerifier, ConditionStatus
from app.cognition.tool_matcher import match_control_tool

GOOD_CODE = '''```python
def execute_tool(params=None):
    params = params or {}
    text = str(params.get("text", "") or "")
    if not text:
        return {"success": True, "result": "", "details": {}}
    return {"success": True, "result": " ".join(reversed(text.split())),
            "details": {"words": len(text.split())}}
```'''


def _unique_tool_name():
    return f"revwords{uuid.uuid4().hex[:6]}"


@pytest.fixture()
def synth_llm():
    """The synthesizer's code-generation call returns a working module."""
    with patch("app.llm.llm_client.generate_chat_completion",
               return_value={"choices": [{"message": {
                   "role": "assistant", "content": GOOD_CODE}}]}):
        yield


def _cleanup(name):
    from app.agents.self_evolving_agent import SelfEvolvingAgent
    from app.config import settings
    for p in (SelfEvolvingAgent.DYNAMIC_TOOLS_DIR / f"dynamic_{name}.py",
              SelfEvolvingAgent.PLUGINS_DIR / f"{name}.py",
              settings.DATA_DIR / "plugins" / f"{name}.py"):
        try:
            p.unlink()
        except OSError:
            pass


# ── the synthesizer installs a REAL registry capability ────────────────

def test_synthesizer_installs_a_real_registry_capability(synth_llm):
    """The chain's proof is the registry lookup + executing the INSTALLED
    capability — the same ground truth the diagnostics pack uses."""
    from app.agents.self_evolving_agent import SelfEvolvingAgent
    from app.cognition.tool_registry import get_shared_registry
    name = _unique_tool_name()
    try:
        res = SelfEvolvingAgent.synthesize_and_hotload_tool(
            task_objective="reverse the words in a string",
            tool_name_query=name)
        assert res["success"] is True, res
        assert res["installed"] is True, res
        entry = get_shared_registry().effective_capability(name)
        assert entry is not None, "registry lookup is the install proof"
        out = get_shared_registry().execute_registered_tool(
            name, {"text": "one two three"})
        assert out.get("success") is True
        assert "three two one" in str(out.get("result", ""))
        # The persisted plugin file must be PluginRegistry-shaped.
        from app.tools.plugin_registry import PluginRegistry
        discovered = PluginRegistry.discover_plugins()
        assert name in discovered, "plugin file must be discoverable"
        assert callable(discovered[name].get("handler"))
    finally:
        _cleanup(name)


def test_synthesizer_fails_honestly_without_installation():
    """Garbage from the model: no install, no registry entry, success=False."""
    from app.agents.self_evolving_agent import SelfEvolvingAgent
    from app.cognition.tool_registry import get_shared_registry
    name = _unique_tool_name()
    with patch("app.llm.llm_client.generate_chat_completion",
               return_value={"choices": [{"message": {
                   "role": "assistant",
                   "content": "I would write a tool that..."}}]}):
        res = SelfEvolvingAgent.synthesize_and_hotload_tool(
            task_objective="reverse words", tool_name_query=name)
    try:
        assert res["success"] is False
        assert res.get("installed") is not True
        assert get_shared_registry().effective_capability(name) is None
    finally:
        _cleanup(name)


# ── routing: capability-creation requests reach the synthesizer ────────

D6_TEXT = ("Create a new tool called reverse_words that takes a "
           "string and returns the words in reverse order. Write it, "
           "test it, and install it as a permanent capability.")


def test_matcher_routes_capability_creation_to_synthesize_tool():
    m = match_control_tool(D6_TEXT)
    assert m is not None
    assert m.action_type == "synthesize_tool"
    assert m.payload["capability_name"] == "reverse_words"
    assert m.payload["description"]


def test_matcher_capability_creation_variant():
    m = match_control_tool("build a capability called summarize_pdf")
    assert m.action_type == "synthesize_tool"
    assert m.payload["capability_name"] == "summarize_pdf"


def test_matcher_task_creation_not_capability_creation():
    m = match_control_tool("create a task to buy milk")
    assert m.action_type == "create_task"


def test_manifest_registers_synthesize_tool():
    from app.cognition.tool_registry import capability_entry
    entry = capability_entry("synthesize_tool")
    assert entry is not None
    assert int(entry.get("safety_level", 99)) == 2


# ── installation is a HARD success condition in the verifier ───────────

def _verify_tool_request(tool_name, reply, register=None):
    text = (f"Create a new tool called {tool_name} that takes a string "
            f"and returns the words in reverse order. Write it, test it, "
            f"and install it as a permanent capability.")
    rep = SemanticGoalInterpreter.interpret_goal(text)
    return GoalVerifier.verify_goal_achievement(rep, [], reply)


def test_verifier_fails_success_claim_without_installation():
    """The exact live incident: the reply claims success, the registry has
    no such capability — the goal must FAIL, never achieve, never wait."""
    res = _verify_tool_request(
        f"revwords{uuid.uuid4().hex[:6]}",
        "Successfully created the tool and tested it.")
    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED
    assert any("capability_installed" in str(fc)
               for fc in res.failed_conditions)


def test_verifier_achieves_with_real_installation_and_execution():
    from app.cognition.tool_registry import get_shared_registry
    name = f"revwords{uuid.uuid4().hex[:6]}"

    def _handler(payload):
        payload = payload or {}
        text = str(payload.get("text", "") or "")
        return {"success": True,
                "result": " ".join(reversed(text.split())) or "ok",
                "details": {}}

    get_shared_registry().register_tool(
        name, "plugin", _handler,
        description="test-installed capability",
        safety_level=2, provenance="dynamic")
    try:
        res = _verify_tool_request(
            name, f"Successfully created {name} and tested it.")
        assert res.verified_success is True, res.failed_conditions
        assert res.final_state == GoalLifecycleState.ACHIEVED
    finally:
        # best-effort: unregister by overwriting is not available; the
        # unique name keeps this pollution inert for other tests.
        pass


def test_verifier_fails_when_installed_capability_does_not_execute():
    from app.cognition.tool_registry import get_shared_registry
    name = f"revwords{uuid.uuid4().hex[:6]}"
    get_shared_registry().register_tool(
        name, "plugin", lambda payload: {"success": False, "error": "boom"},
        description="broken test capability",
        safety_level=2, provenance="dynamic")
    res = _verify_tool_request(
        name, f"Successfully created {name} and tested it.")
    assert res.verified_success is False
    assert res.final_state != GoalLifecycleState.ACHIEVED


def test_verifier_unknown_when_no_name_to_probe():
    """A capability condition whose request names no capability: honest
    UNKNOWN (nothing to probe), never achieved."""
    rep = SemanticGoalInterpreter.interpret_goal(
        "Create a new tool for me and install it.")
    rep.success_conditions = ["capability_installed = true"]
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "I created and installed the tool.")
    assert res.verified_success is False
    assert res.final_state != GoalLifecycleState.ACHIEVED
