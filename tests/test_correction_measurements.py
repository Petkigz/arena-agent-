"""Correction telemetry remains trace-linked, bounded, and separate from truth."""

import sqlite3

from app.cognition.correction_measurements import CorrectionMeasurementStore
from app.cognition.trace import CognitiveTrace


def test_correction_measurement_records_trace_latency_and_strategy_scope(tmp_path, monkeypatch):
    from app.config import settings

    trace_db = tmp_path / "trace.db"
    monkeypatch.setattr(settings, "DB_PATH", trace_db)
    trace = CognitiveTrace(
        user_input="Which device?",
        session_id="session-correction",
        created_at="2026-01-01T00:00:00+00:00",
    )
    trace.finalize(
        reply="The wrong device.",
        actions=[],
        latency=1.0,
        goal_verified=False,
    )

    store = CorrectionMeasurementStore(
        tmp_path / "corrections.db",
        trace_db_path=trace_db,
    )
    event = store.record(
        trace_id=trace.trace_id,
        correction_type="factual",
        expected_effect="keep the correction local until repeated evidence exists",
        strategy_update={
            "applied": True,
            "generalized": False,
            "correction_count": 1,
            "adjustment_factor": 1.0,
        },
        evidence=[f"source_trace:{trace.trace_id}"],
        received_at="2026-01-01T00:00:01.250000+00:00",
    )

    assert event.trace_id == trace.trace_id
    assert event.correction_type == "factual"
    assert event.latency_ms == 1250.0
    assert event.latency_basis == "trace_created_at_to_correction_received"
    assert event.strategy_applied is True
    assert event.strategy_generalized is False
    assert store.summary().to_dict() == {
        "total_corrections": 1,
        "trace_linked_corrections": 1,
        "measured_latency_count": 1,
        "mean_latency_ms": 1250.0,
        "strategy_update_count": 1,
        "generalized_update_count": 0,
        "correction_types": {"factual": 1},
    }

    with sqlite3.connect(trace_db) as conn:
        goal_verified = conn.execute(
            "SELECT goal_verified FROM cognitive_traces WHERE trace_id=?",
            (trace.trace_id,),
        ).fetchone()[0]
    assert goal_verified == 0


def test_unlinked_correction_admits_unmeasured_latency(tmp_path):
    store = CorrectionMeasurementStore(tmp_path / "corrections.db")

    event = store.record(
        correction_type="intent",
        expected_effect="keep local",
        received_at="2026-01-01T00:00:01+00:00",
    )

    assert event.trace_id == ""
    assert event.latency_ms is None
    assert event.latency_basis == "unmeasured_no_trace_timestamp"
    assert store.summary().measured_latency_count == 0


def test_correction_measurement_endpoint_exposes_bounded_summary(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.cognition.runtime import CognitiveRuntime
    from app.main import correction_measurements_endpoint

    store = CorrectionMeasurementStore(tmp_path / "corrections.db")
    store.record(
        correction_type="routing",
        expected_effect="keep local",
        received_at="2026-01-01T00:00:01+00:00",
    )
    runtime = SimpleNamespace(correction_measurements=store)
    monkeypatch.setattr(
        CognitiveRuntime,
        "get_instance",
        classmethod(lambda cls: runtime),
    )

    result = correction_measurements_endpoint(limit=1)

    assert result["success"] is True
    assert result["summary"]["total_corrections"] == 1
    assert len(result["events"]) == 1
    assert "human reaction time" in result["note"]


def test_owner_correction_endpoint_records_trace_linked_measurement(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.config import settings
    from app.cognition.runtime import CognitiveRuntime
    from app.cognition.strategy_outcomes import StrategyOutcomeStore
    from app.cognition.training_examples import TrainingExampleStore
    from app.main import OwnerCorrectionRequest, create_owner_correction_endpoint

    trace_db = tmp_path / "trace.db"
    monkeypatch.setattr(settings, "DB_PATH", trace_db)
    trace = CognitiveTrace(user_input="Which device?")
    trace.finalize(reply="The wrong device.", actions=[], latency=1.0, goal_verified=False)
    outcomes = StrategyOutcomeStore(tmp_path / "strategy.db")
    candidates = TrainingExampleStore(tmp_path / "candidates.db", trace_db_path=trace_db)
    measurements = CorrectionMeasurementStore(
        tmp_path / "corrections.db", trace_db_path=trace_db
    )
    runtime = SimpleNamespace(
        training_examples=candidates,
        outcomes=outcomes,
        correction_measurements=measurements,
    )
    monkeypatch.setattr(
        CognitiveRuntime,
        "get_instance",
        classmethod(lambda cls: runtime),
    )

    result = create_owner_correction_endpoint(OwnerCorrectionRequest(
        response="The corrected device is the phone.",
        skill_name="answer",
        correction_type="factual",
        trace_id=trace.trace_id,
        action_type="answer",
        goal_type="device_question",
    ))

    assert result["success"] is True
    measurement = result["correction_measurement"]
    assert measurement["trace_id"] == trace.trace_id
    assert measurement["correction_type"] == "factual"
    assert measurement["strategy_applied"] is True
    assert measurements.summary().total_corrections == 1
