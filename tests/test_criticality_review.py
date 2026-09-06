"""Bounded adversarial review contracts and telemetry persistence."""

import json
import sqlite3
from dataclasses import dataclass

from app.cognition.action_proposal import ActionProposal, GateResult
from app.cognition.criticality_review import review_action_proposal
from app.cognition.reasoning_cycle import ReasoningAction, ReasoningDecision
from app.cognition.reasoning_loop import CycleTrace
from app.cognition.runtime import CognitiveRuntime
from app.cognition.trace import CognitiveTrace


@dataclass
class _Goal:
    unknowns: list[str]


def test_criticality_review_surfaces_uncertainty_without_authorizing():
    proposal = ActionProposal(
        action_type="unknown_sensitive_capability",
        payload={"target": "owner-machine"},
        predicted_outcome={"changed": "something"},
    )

    review = review_action_proposal(
        proposal,
        goal_rep=_Goal(unknowns=["which target is intended"]),
        calibrated_confidence=0.95,
        history_available=False,
    )

    assert review.required is True
    assert review.severity == "high"
    assert "high_risk_action" in review.triggers
    assert "no_verified_action_history" in review.triggers
    assert "unresolved_goal_unknowns" in review.triggers
    assert "high_confidence_under_uncertainty" in review.triggers
    assert review.recommendation == "surface_review_and_preserve_uncertainty"
    assert review.checks["authorization_left_to_action_gate"] is True
    assert review.checks["execution_truth_left_to_observation"] is True


def test_criticality_review_records_malformed_and_missing_prediction():
    review = review_action_proposal(
        ActionProposal(action_type="", payload=[]),
        history_available=True,
    )

    assert "malformed_recommendation" in review.triggers
    assert "missing_prediction" in review.triggers
    assert review.checks["payload_is_mapping"] is False
    assert review.checks["predicted_outcome_present"] is False


def test_runtime_reviews_before_action_gate_without_authorizing(tmp_path):
    from unittest.mock import patch

    runtime = CognitiveRuntime(db_path=str(tmp_path / "runtime-review.db"))
    proposal = ActionProposal(
        action_type="unknown_sensitive_capability",
        payload={"target": "owner-machine"},
        predicted_outcome={"changed": "something"},
    )
    loop_trace = CycleTrace(
        decisions=[
            ReasoningDecision(
                action=ReasoningAction.ACT,
                confidence=0.95,
                reason="action requested",
            )
        ]
    )
    gate_seen_review = []

    def gate_evaluator(_proposal):
        gate_seen_review.append(runtime.blackboard.get("criticality_review"))
        return GateResult(
            allowed=False,
            gate_name="policy_gate",
            reason="test block",
            requires_approval=False,
        )

    with patch.object(runtime.loop, "run", return_value=loop_trace), \
         patch("app.cognition.tool_matcher.match_control_tool", return_value=None), \
         patch.object(runtime, "generate_candidate_action_proposal", return_value=proposal), \
         patch("app.cognition.action_proposal.ActionGate.evaluate_proposal", side_effect=gate_evaluator):
        result = runtime.process_cognitive_cycle("perform the sensitive operation")

    assert result["success"] is False
    assert result["criticality_review"]["required"] is True
    assert gate_seen_review and gate_seen_review[0]["required"] is True
    assert result["criticality_review"]["recommendation"] == "surface_review_and_preserve_uncertainty"
    assert result["compute_policy"]["advisory_only"] is True
    assert result["compute_policy"]["calibration_status"] == "not_calibrated"
    assert result["gate_blocked"] == "policy_gate"


def test_trace_migrates_older_schema_for_criticality_and_route(tmp_path, monkeypatch):
    from app.config import settings

    db_path = tmp_path / "old-trace.db"
    monkeypatch.setattr(settings, "DB_PATH", db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE cognitive_traces (
                trace_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_input TEXT NOT NULL,
                assistant_reply TEXT NOT NULL,
                actions_json TEXT NOT NULL,
                model_used TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                vram_pressure REAL,
                ram_pressure REAL,
                attention_focus TEXT,
                belief_confidence REAL,
                gate_decision TEXT,
                prediction_surprisal REAL,
                reflection_lesson TEXT,
                goal_verified INTEGER,
                goal_lifecycle_state TEXT,
                created_at TEXT NOT NULL
            )
        """)

    trace = CognitiveTrace(user_input="migrate review telemetry")
    trace.criticality_review = {"severity": "low"}
    trace.route_comparison = {"agreement": None}
    trace.finalize(reply="migrated", actions=[], latency=1.0)

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(cognitive_traces)")}
        row = conn.execute(
            "SELECT criticality_review_json, route_comparison_json "
            "FROM cognitive_traces WHERE trace_id=?",
            (trace.trace_id,),
        ).fetchone()

    assert {"criticality_review_json", "route_comparison_json"} <= columns
    assert json.loads(row[0]) == {"severity": "low"}
    assert json.loads(row[1]) == {"agreement": None}


def test_trace_persists_criticality_and_route_comparison(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "criticality.db")
    trace = CognitiveTrace(user_input="review this proposal")
    trace.criticality_review = {
        "severity": "high",
        "triggers": ["conflicting_historical_evidence"],
        "required": True,
    }
    trace.route_comparison = {
        "agreement": True,
        "action_agreement": False,
    }
    trace.finalize(reply="Review recorded", actions=[], latency=1.0)

    with sqlite3.connect(settings.DB_PATH) as conn:
        row = conn.execute(
            "SELECT criticality_review_json, route_comparison_json "
            "FROM cognitive_traces WHERE trace_id=?",
            (trace.trace_id,),
        ).fetchone()

    assert row is not None
    assert json.loads(row[0])["triggers"] == ["conflicting_historical_evidence"]
    assert json.loads(row[1])["action_agreement"] is False
