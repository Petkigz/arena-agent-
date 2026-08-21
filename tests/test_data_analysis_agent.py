"""DataAnalysisAgent loop tests — inspect → plan → query → verify → answer,
with a mocked LLM so the loop logic is tested deterministically (no real model).

The deterministic parts (CSV inspection, read-only SQL enforcement, row
execution) run for real against a tiny fixture CSV.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.agents.data_analysis_agent import DataAnalysisAgent


def _csv(tmp_path):
    p = tmp_path / "sales.csv"
    p.write_text("region,sales\nwest,10\neast,20\nwest,30\n", encoding="utf-8")
    return str(p)


def _fake_llm(replies):
    """Return `replies` in order, then repeat the last."""
    calls = {"n": 0}

    def generate_chat_completion(**kw):
        i = min(calls["n"], len(replies) - 1)
        calls["n"] += 1
        return {"choices": [{"message": {"content": replies[i]}}]}

    return generate_chat_completion


def _agent(tmp_path, replies, max_attempts=3):
    agent = DataAnalysisAgent(workdir=str(tmp_path), max_attempts=max_attempts)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _fake_llm(replies)
    return agent


def test_succeeds_first_attempt(tmp_path):
    # plan, query, answer — three LLM calls for one attempt.
    agent = _agent(tmp_path, [
        "Group sales by region.",
        "SELECT region, SUM(sales) AS total FROM data GROUP BY region",
        "West leads with 40 total sales.",
    ])
    res = agent.run(_csv(tmp_path), "Which region sold the most?")
    assert res["success"] is True
    assert res["attempts"] == 1
    assert res["query"].startswith("SELECT")
    assert "West leads" in res["answer"]
    assert res["count"] == 2  # two regions


def test_retries_on_bad_query_then_succeeds(tmp_path):
    # First query is broken (nonexistent column), second is fixed.
    agent = _agent(tmp_path, [
        "Group sales.",
        "SELECT badcol FROM data",
        "Group sales.",
        "SELECT region, SUM(sales) AS total FROM data GROUP BY region",
        "East sold 20.",
    ])
    res = agent.run(_csv(tmp_path), "Which region sold the most?")
    assert res["success"] is True
    assert res["attempts"] == 2
    assert "badcol" in res["history"][0]["exec"]["error"]


def test_gives_up_after_max_attempts(tmp_path):
    agent = _agent(tmp_path, [
        "Plan.", "SELECT badcol FROM data",
    ], max_attempts=2)
    res = agent.run(_csv(tmp_path), "q?")
    assert res["success"] is False
    assert "Failed after 2 attempts" in res["message"]


def test_requires_question_and_dataset(tmp_path):
    agent = DataAnalysisAgent(workdir=str(tmp_path), max_attempts=1)
    assert agent.run(_csv(tmp_path), "  ")["success"] is False
    assert agent.run("  ", "question")["success"] is False


def test_missing_dataset_fails_cleanly(tmp_path):
    agent = DataAnalysisAgent(workdir=str(tmp_path), max_attempts=1)
    res = agent.run(str(tmp_path / "nope.csv"), "question?")
    assert res["success"] is False
    assert "error" in res


def test_enforces_read_only_sql(tmp_path):
    # Model tries a mutating statement → rejected deterministically, never run.
    agent = _agent(tmp_path, [
        "Delete everything.", "DELETE FROM data",
    ], max_attempts=1)
    res = agent.run(_csv(tmp_path), "wipe?")
    assert res["success"] is False
    assert "read-only" in res["attempts"][0]["exec"]["error"].lower()


def test_deterministic_fallback_when_model_empty(tmp_path):
    # Model returns a valid query but an empty answer → deterministic summary.
    agent = _agent(tmp_path, [
        "Plan.", "SELECT region, SUM(sales) AS total FROM data GROUP BY region", "",
    ])
    res = agent.run(_csv(tmp_path), "Which region?")
    assert res["success"] is True
    assert "returned 2 row" in res["answer"]


def test_strips_sql_fences(tmp_path):
    agent = _agent(tmp_path, [
        "Plan.", "```sql\nSELECT region, SUM(sales) AS total FROM data GROUP BY region\n```",
        "ok",
    ])
    res = agent.run(_csv(tmp_path), "Which region?")
    assert res["success"] is True
    assert not res["query"].startswith("```")


def test_records_outcome_into_runtime(tmp_path):
    runtime = MagicMock()
    agent = DataAnalysisAgent(workdir=str(tmp_path), max_attempts=1, runtime=runtime)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _fake_llm([
        "Plan.", "SELECT region, SUM(sales) AS total FROM data GROUP BY region", "ok",
    ])
    res = agent.run(_csv(tmp_path), "Which region?")
    assert res["success"] is True
    runtime.memory.add.assert_called_once()
    runtime.outcomes.record_outcome.assert_called_once()
    runtime.lessons.extract_lesson.assert_called_once()
    # Recorded as a success.
    assert runtime.outcomes.record_outcome.call_args[1]["success"] is True


def test_records_failure_outcome(tmp_path):
    runtime = MagicMock()
    agent = DataAnalysisAgent(workdir=str(tmp_path), max_attempts=1, runtime=runtime)
    agent._llm = MagicMock()
    agent._llm.generate_chat_completion.side_effect = _fake_llm([
        "Plan.", "SELECT badcol FROM data",
    ])
    agent.run(_csv(tmp_path), "q?")
    assert runtime.outcomes.record_outcome.call_args[1]["success"] is False


def test_excel_query_path(tmp_path):
    # Exercise the pandas→sqlite branch for non-CSV files (skipped if pandas missing).
    pd = pytest.importorskip("pandas")
    p = tmp_path / "sales.xlsx"
    pd.DataFrame({"region": ["west", "east", "west"], "sales": [10, 20, 30]}).to_excel(str(p), index=False)

    agent = _agent(tmp_path, [
        "Plan.", "SELECT region, SUM(sales) AS total FROM data GROUP BY region", "ok",
    ])
    res = agent.run(str(p), "Which region?")
    assert res["success"] is True
    assert res["count"] == 2
