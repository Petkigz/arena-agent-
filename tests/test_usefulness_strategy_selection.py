"""Trace-linked usefulness feedback influences strategy selection conservatively."""

import sqlite3

from app.cognition.counterfactual_simulator import CounterfactualSimulator
from app.cognition.strategy_outcomes import StrategyUsefulnessStore
from app.cognition.trace import CognitiveTrace


def _persist_strategy_trace(db_path, goal_type="knowledge_query", action_type="web_search"):
    from app.config import settings

    settings.DB_PATH = db_path
    trace = CognitiveTrace(user_input="search for the requested fact")
    trace.strategy_goal_type = goal_type
    trace.strategy_action_type = action_type
    trace.finalize(reply="Completed", actions=[action_type], latency=2.0)
    return trace


def test_usefulness_requires_multiple_owner_events_and_stays_separate(tmp_path, monkeypatch):
    db_path = tmp_path / "usefulness.db"
    monkeypatch.setattr("app.config.settings.DB_PATH", db_path)
    trace_a = _persist_strategy_trace(db_path)
    trace_b = _persist_strategy_trace(db_path)
    store = StrategyUsefulnessStore(str(db_path))

    CognitiveTrace.record_usefulness_feedback(
        trace_a.trace_id,
        usefulness="helpful",
        outcome_signal="clarification_requested",
        note="Useful direction, but I needed one clarification.",
    )
    assert store.adjustment_factor("knowledge_query", "web_search") == 1.0

    CognitiveTrace.record_usefulness_feedback(
        trace_b.trace_id,
        usefulness="helpful",
        outcome_signal="task_completed",
    )
    score = store.score_strategy("knowledge_query", "web_search")
    assert score is not None
    assert score.total_feedback == 2
    assert score.helpful == 2
    assert score.outcome_signal_counts == {
        "clarification_requested": 1,
        "task_completed": 1,
    }
    assert store.adjustment_factor("knowledge_query", "web_search") > 1.0
    assert store.adjustment_factor("knowledge_query", "web_search") <= 1.15

    # Correctness is not read from or rewritten by usefulness aggregation.
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT goal_verified, strategy_goal_type, strategy_action_type "
            "FROM cognitive_traces WHERE trace_id=?",
            (trace_a.trace_id,),
        ).fetchone()
    assert row[0] == 1
    assert row[1:] == ("knowledge_query", "web_search")


def test_not_helpful_feedback_is_bounded_and_can_deprioritize(tmp_path, monkeypatch):
    db_path = tmp_path / "not-helpful.db"
    monkeypatch.setattr("app.config.settings.DB_PATH", db_path)
    traces = [_persist_strategy_trace(db_path, action_type="slow_strategy") for _ in range(3)]
    for trace in traces:
        CognitiveTrace.record_usefulness_feedback(
            trace.trace_id,
            usefulness="not_helpful",
            outcome_signal="correction_followup",
        )

    store = StrategyUsefulnessStore(str(db_path))
    score = store.score_strategy("knowledge_query", "slow_strategy")
    assert score is not None
    assert score.not_helpful == 3
    assert store.adjustment_factor("knowledge_query", "slow_strategy") >= 0.85
    assert store.adjustment_factor("knowledge_query", "slow_strategy") < 1.0


def test_counterfactual_branch_carries_usefulness_adjustment_without_authority():
    class _Usefulness:
        def adjustment_factor(self, goal_type, action_type):
            return 0.85 if action_type == "slow_strategy" else 1.0

    result = CounterfactualSimulator.simulate_competing_branches(
        "search for the requested fact",
        [
            {"name": "slow", "action_type": "slow_strategy", "payload": {}},
            {"name": "fast", "action_type": "fast_strategy", "payload": {}},
        ],
        goal_type="knowledge_query",
        usefulness_store=_Usefulness(),
    )
    slow = next(branch for branch in result.competing_branches if branch.hypothetical_action == "slow_strategy")
    assert slow.usefulness_adjustment == 0.85
    assert slow.consequences["reversible"] is True
    # The simulation only changes consideration utility; it does not create
    # authorization or execution evidence.
    assert not hasattr(slow, "authorization_id")
