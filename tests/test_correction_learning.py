"""Owner correction loop: preserve, revise locally, generalize cautiously."""

import sqlite3
from types import SimpleNamespace

import pytest

from app.cognition.correction_learning import CorrectionHandler
from app.cognition.strategy_outcomes import StrategyOutcomeStore


def _trace_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE cognitive_traces (
            trace_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_input TEXT NOT NULL,
            assistant_reply TEXT NOT NULL,
            actions_json TEXT NOT NULL,
            model_used TEXT NOT NULL,
            goal_verified INTEGER,
            epistemic_presentation_json TEXT NOT NULL DEFAULT '{}'
        )""")
        conn.execute(
            "INSERT INTO cognitive_traces VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "trace-1", "session-1", "Where is the phone?",
                "The laptop is on the desk.\n\nEpistemic status: Tentative",
                "[]", "fast", 0,
                '{"confidence_label":"Tentative","evidence_state":"inferred"}',
            ),
        )
        conn.commit()


class _FakeBeliefEngine:
    def __init__(self):
        self.calls = []

    def ingest(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            has_belief=False,
            hypothesis_value=kwargs["value"],
            evidence_count=0,
        )


def test_correction_preserves_trace_and_updates_owner_hypothesis(tmp_path):
    db_path = tmp_path / "corrections.db"
    _trace_db(db_path)
    beliefs = _FakeBeliefEngine()
    handler = CorrectionHandler(
        db_path,
        belief_engine=beliefs,
        strategy_store=StrategyOutcomeStore(str(db_path)),
    )

    result = handler.handle(
        trace_id="trace-1",
        correction="I meant the phone, not the laptop.",
        error_type="intent",
        subject="current_device",
        predicate="referent",
        corrected_value="phone",
        action_type="answer",
        goal_type="device_question",
    )

    assert result["success"] is True
    assert result["original_trace"]["original_response"].startswith("The laptop")
    assert result["correction"]["error_type"] == "intent"
    assert result["belief_update"]["applied"] is True
    assert result["belief_update"]["authoritative_belief_unchanged"] is True
    assert beliefs.calls[0]["source"] == "user_input"
    assert beliefs.calls[0]["observation_type"] == "self_reported"
    assert result["strategy_update"]["generalized"] is False
    assert result["strategy_update"]["adjustment_factor"] == 1.0


def test_repeated_corrections_deprioritize_strategy_but_one_does_not(tmp_path):
    db_path = tmp_path / "corrections.db"
    _trace_db(db_path)
    outcomes = StrategyOutcomeStore(str(db_path))
    handler = CorrectionHandler(db_path, strategy_store=outcomes)
    kwargs = {
        "trace_id": "trace-1",
        "correction": "Use the phone referent.",
        "error_type": "intent",
        "action_type": "answer",
        "goal_type": "device_question",
    }

    first = handler.handle(**kwargs)
    second = handler.handle(**kwargs)

    assert first["strategy_update"]["generalized"] is False
    assert second["strategy_update"]["generalized"] is True
    assert second["strategy_update"]["status"] == (
        "strategy_deprioritized_after_repeated_corrections"
    )
    assert second["strategy_update"]["adjustment_factor"] < 1.0


def test_unknown_trace_is_not_accepted_as_a_correction(tmp_path):
    db_path = tmp_path / "corrections.db"
    _trace_db(db_path)
    handler = CorrectionHandler(db_path)

    with pytest.raises(KeyError, match="Trace not found"):
        handler.handle(trace_id="missing", correction="That was wrong.")
