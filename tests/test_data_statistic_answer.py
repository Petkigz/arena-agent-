"""P1 (live 2026-09-01, D2, owner review item 2): a concrete numerical
result must become evidence that closes the goal.

Live incident: 'Analyze the CSV ... tell me the average of the amount
column' — data tool used=True, yet verified=False and lifecycle=
waiting_for_evidence; the reply said "Let's compute the average ...
now" and the mean (159.298) never became evidence. The arithmetic path
(D1) already has the full chain — router plans the deterministic tool,
the result is rendered as VERIFIED evidence, the runtime records the
value as ground truth, the GoalVerifier requires the reply to state it.
The SAME chain must exist for data-statistic asks: analyze_data computes
df.describe(), which contains the mean — that number must close the
goal, not stall it.

Conservative detector scope (like the calculator): statistic asks with
BOTH an explicit '<statistic> of <column> column' AND an explicit data
file (.csv/.xlsx/.xls) in the request. Statistics limited to what
describe() reports directly (mean/average, median, min, max) — no
derived math (sum = mean*count would fabricate precision).
"""

import statistics
from pathlib import Path

import pytest

from app.cognition.observation_router import (
    ObservationPlan,
    extract_statistic_from_analysis,
    plan_observation,
    render_observation_evidence,
)
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_lifecycle import GoalLifecycleState
from app.cognition.goal_verifier import GoalVerifier

AMOUNTS = [120.50, 89.99, 230.00, 45.25, 310.75]  # mean 159.298


@pytest.fixture()
def sales_csv(tmp_path):
    p = tmp_path / "sales.csv"
    p.write_text("date,product,amount\n"
                 "2026-08-01,widget,120.50\n2026-08-02,gadget,89.99\n"
                 "2026-08-03,widget,230.00\n2026-08-04,gizmo,45.25\n"
                 "2026-08-05,gadget,310.75\n", encoding="utf-8")
    return p


def _run_analysis(plan: ObservationPlan):
    from app.cognition.tool_registry import capability_entry
    entry = capability_entry(plan.action_type)
    assert entry is not None, "analyze_data must be registered"
    assert int(entry.get("safety_level", 99)) == 0, (
        "must be Level 0 to run as a read-only observation")
    return entry["handler"](plan.payload)


# ── router: the ask must plan the deterministic analysis ───────────────

def test_router_plans_deterministic_analysis_for_statistic_ask(sales_csv):
    text = (f"Analyze the CSV file at {sales_csv} and tell me the "
            f"average of the amount column.")
    plan = plan_observation(text)
    assert plan is not None
    assert plan.action_type == "analyze_data"
    assert plan.question_kind == "data_statistic"
    assert plan.payload["file_path_str"] == str(sales_csv)
    assert plan.payload["statistic"] == "mean"
    assert plan.payload["column"] == "amount"


def test_router_statistic_variants(sales_csv):
    plan = plan_observation(
        f"What's the max of the 'price' column in {sales_csv}?")
    assert plan.payload["statistic"] == "max"
    assert plan.payload["column"] == "price"
    plan = plan_observation(
        f"compute the median of column age for {sales_csv}")
    assert plan.payload["statistic"] == "median"
    assert plan.payload["column"] == "age"


def test_router_conservative_negatives():
    # No data file named -> not a data statistic ask.
    assert plan_observation(
        "What is the average of the amount column?") is None
    # Statistic word without a column mention -> not this shape.
    assert plan_observation(
        "What is the average price of a house in Kampala?") is None
    # File request without a statistic ask -> other routing owns it.
    assert plan_observation(
        "Read the CSV file at C:/data/sales.csv and summarize it") is None


# ── extraction: the number comes from analyze_data's own result ────────

def test_statistic_extraction_from_real_analysis(sales_csv):
    plan = plan_observation(
        f"Analyze the CSV file at {sales_csv} and tell me the average "
        f"of the amount column.")
    result = _run_analysis(plan)
    assert result["success"] is True
    stat = extract_statistic_from_analysis(result, plan)
    assert stat is not None
    assert stat["value"] == pytest.approx(statistics.mean(AMOUNTS))
    assert stat["value_str"] == "159.298"
    assert stat["statistic"] == "mean"
    assert stat["column"] == "amount"


def test_statistic_extraction_variants(sales_csv):
    for word, expected in (("median", 120.50), ("max", 310.75), ("min", 45.25)):
        plan = plan_observation(
            f"Analyze the CSV file at {sales_csv} and tell me the {word} "
            f"of the amount column.")
        result = _run_analysis(plan)
        stat = extract_statistic_from_analysis(result, plan)
        assert stat is not None, word
        assert stat["value"] == pytest.approx(expected), word


def test_statistic_extraction_honest_when_column_missing(sales_csv):
    plan = plan_observation(
        f"Analyze the CSV file at {sales_csv} and tell me the average "
        f"of the revenue column.")
    result = _run_analysis(plan)
    stat = extract_statistic_from_analysis(result, plan)
    assert stat is None  # no invented number for a column that is not there


# ── renderer: the evidence states the verified value ───────────────────

def test_renderer_states_verified_value(sales_csv):
    plan = plan_observation(
        f"Analyze the CSV file at {sales_csv} and tell me the average "
        f"of the amount column.")
    result = _run_analysis(plan)
    evidence = render_observation_evidence(result, plan)
    assert "VERIFIED DATA ANALYSIS" in evidence
    assert "159.298" in evidence
    assert "State 159.298" in evidence


def test_renderer_honest_when_file_missing(tmp_path):
    missing = tmp_path / "nope.csv"
    plan = plan_observation(
        f"Analyze the CSV file at {missing} and tell me the average "
        f"of the amount column.")
    result = _run_analysis(plan)
    evidence = render_observation_evidence(result, plan)
    assert "could not be completed" in evidence
    assert "159" not in evidence  # never invent a number


# ── the goal closes: ground truth + reply stating it ───────────────────

D2_TEXT = ("Analyze the CSV file at C:/data/sales.csv and tell me the "
           "average of the amount column.")


def _data_observed_state():
    """The state the runtime records after analyze_data ran (D2)."""
    return {
        "deterministic_answers": [
            {"expression": "mean of 'amount' in sales.csv",
             "value": 159.298, "value_str": "159.298"},
        ],
    }


def test_verifier_fails_reply_without_the_mean():
    res = GoalVerifier.verify_goal_achievement(
        SemanticGoalInterpreter.interpret_goal(D2_TEXT),
        [], "I've noted this task before. Let's compute the average now.",
        observed_state=_data_observed_state(),
    )
    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED
    assert any("159.298" in str(fc) for fc in res.failed_conditions)


def test_verifier_achieves_reply_stating_the_mean():
    res = GoalVerifier.verify_goal_achievement(
        SemanticGoalInterpreter.interpret_goal(D2_TEXT),
        [], "The average of the amount column is 159.298.",
        observed_state=_data_observed_state(),
    )
    assert res.verified_success is True
    assert res.final_state == GoalLifecycleState.ACHIEVED
