"""
"One brain, thin agents" tests:

1. CognitiveRuntime.__init__ registers the process-wide singleton, so
   get_instance() returns the SAME instance the server constructs (no second
   divergent brain).
2. The coding agent records outcomes into the injected runtime (memory + outcome
   store + lesson store) and uses hardware-aware complexity selection.
"""

from unittest.mock import MagicMock, patch

from app.cognition.runtime import CognitiveRuntime
from app.agents.coding_agent import CodingAgent


def test_runtime_constructor_registers_singleton(tmp_path):
    CognitiveRuntime._instance = None
    rt = CognitiveRuntime(db_path=str(tmp_path / "a.db"))
    assert CognitiveRuntime.get_instance() is rt


def _one_reply(text):
    def gen(**kw):
        return {"choices": [{"message": {"content": text}}]}
    return gen


def test_agent_records_outcomes_into_runtime(tmp_path):
    rt = CognitiveRuntime(db_path=str(tmp_path / "brain.db"))
    agent = CodingAgent(workdir=str(tmp_path), runtime=rt, checkpoint_enabled=False)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _one_reply("def f(): pass")

    with patch.object(agent, "_run_tests", return_value={"success": True}):
        res = agent.run(task="write f", target_file="f.py", test_command="pytest")

    assert res["success"] is True
    # The brain now has an episodic memory + a recorded outcome.
    mems = rt.memory.search("coding task", limit=5)
    assert any("coding task" in m.content for m in mems)


def test_agent_uses_runtime_complexity(tmp_path):
    rt = CognitiveRuntime(db_path=str(tmp_path / "cx.db"))
    agent = CodingAgent(workdir=str(tmp_path), runtime=rt, checkpoint_enabled=False)
    # Under memory pressure, the runtime downgrades 'main' → 'fast'.
    rt.hardware_self_model = {"live": {"ram_percent": 95.0}, "recommendation": {"downgrade_to_fast_when_ram_above": 80.0}}
    assert agent._select_complexity() == "fast"


def test_agent_without_runtime_still_works(tmp_path):
    """A coding agent with no runtime is allowed (standalone/test use) and just skips recording."""
    agent = CodingAgent(workdir=str(tmp_path), runtime=None, checkpoint_enabled=False)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _one_reply("print('x')")
    res = agent.run(task="print x", target_file="x.py")  # no test command
    assert res["success"] is True
    # _record is a no-op when runtime is None (must not raise).
    agent._record("task", success=True, latency_ms=1.0, attempts=[])
