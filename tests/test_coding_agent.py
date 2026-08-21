"""
CodingAgent loop tests — plan → write → verify → branch → rollback, with a mocked
LLM and sandbox so the loop logic is tested deterministically (no real model).
"""

from unittest.mock import MagicMock, patch

from app.agents.coding_agent import CodingAgent


def _fake_llm(replies):
    """A fake llm_client that returns `replies` in order, then repeats the last."""
    calls = {"n": 0}

    def generate(**kw):
        i = min(calls["n"], len(replies) - 1)
        calls["n"] += 1
        return {"choices": [{"message": {"content": replies[i]}}]}

    return generate


def test_coding_agent_succeeds_first_attempt(tmp_path):
    agent = CodingAgent(workdir=str(tmp_path), max_attempts=3, checkpoint_enabled=False)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _fake_llm(["def add(a,b): return a+b"])

    with patch.object(agent, "_run_tests", return_value={"success": True, "stdout": "passed"}):
        res = agent.run(task="write add", target_file="add.py", test_command="pytest")

    assert res["success"] is True
    assert res["attempts"] == 1
    assert (tmp_path / "add.py").read_text() == "def add(a,b): return a+b"


def test_coding_agent_branches_on_failure_then_succeeds(tmp_path):
    agent = CodingAgent(workdir=str(tmp_path), max_attempts=3, checkpoint_enabled=False)
    agent._llm = MagicMock()
    # First attempt returns buggy code, second returns fixed code.
    agent._llm.generate_chat_completion.side_effect = _fake_llm([
        "def add(a,b): return a-b",   # wrong
        "def add(a,b): return a+b",   # fixed
    ])

    # Tests fail on attempt 1, pass on attempt 2.
    test_results = iter([{"success": False, "stderr": "assert 3 == -1"}, {"success": True, "stdout": "passed"}])
    with patch.object(agent, "_run_tests", side_effect=lambda *a, **k: next(test_results)):
        res = agent.run(task="write add", target_file="add.py", test_command="pytest")

    assert res["success"] is True
    assert res["attempts"] == 2
    assert (tmp_path / "add.py").read_text() == "def add(a,b): return a+b"


def test_coding_agent_gives_up_after_max_attempts(tmp_path):
    agent = CodingAgent(workdir=str(tmp_path), max_attempts=2, checkpoint_enabled=False)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _fake_llm(["def add(a,b): return a-b"])

    with patch.object(agent, "_run_tests", return_value={"success": False, "stderr": "fail"}):
        res = agent.run(task="write add", target_file="add.py", test_command="pytest")

    assert res["success"] is False
    assert len(res["attempts"]) == 2
    assert "Failed after 2 attempts" in res["message"]


def test_coding_agent_no_test_command_succeeds_after_write(tmp_path):
    agent = CodingAgent(workdir=str(tmp_path), checkpoint_enabled=False)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _fake_llm(["print('hi')"])

    res = agent.run(task="print hi", target_file="hi.py")  # no test_command
    assert res["success"] is True
    assert (tmp_path / "hi.py").exists()


def test_coding_agent_strips_markdown_fences(tmp_path):
    agent = CodingAgent(workdir=str(tmp_path), checkpoint_enabled=False)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _fake_llm(["```python\nprint('x')\n```"])

    with patch.object(agent, "_run_tests", return_value={"success": True}):
        res = agent.run(task="x", target_file="x.py", test_command="pytest")

    assert (tmp_path / "x.py").read_text() == "print('x')"


def test_coding_agent_requires_task(tmp_path):
    agent = CodingAgent(workdir=str(tmp_path), checkpoint_enabled=False)
    assert agent.run("  ")["success"] is False


def test_coding_agent_checkpoint_and_rollback_called(tmp_path):
    """On failure, the agent checkpoints before and rolls back after."""
    agent = CodingAgent(workdir=str(tmp_path), max_attempts=1, checkpoint_enabled=True)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _fake_llm(["def f(): pass"])

    with patch.object(agent, "_checkpoint", return_value="abc123") as mock_cp, \
         patch.object(agent, "_rollback") as mock_rb, \
         patch.object(agent, "_run_tests", return_value={"success": False, "stderr": "fail"}):

        agent.run(task="x", target_file="x.py", test_command="pytest")

    mock_cp.assert_called_once()
    mock_rb.assert_called_once_with("abc123")
