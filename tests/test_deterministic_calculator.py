"""F3b (DIAG D1): deterministic arithmetic — the agent must never guess math.

Live bug (owner machine, 2026-09-01): 'What is 17 * 24?' went to the 3B
chat model, which answered 396 (ground truth 408), and the goal verified
as 'achieved' because a reply existed. Arithmetic has ONE correct answer
and the agent owns a CPU — the answer must come from a deterministic
evaluation, and the reply must be phrased from that evidence.

Contract under test:
  * app.tools.calculator.DeterministicCalculator
      - extract_expression(text): the shared arithmetic-question detector
        (ONE implementation — the observation router and the goal
        interpreter both use it, no duplicated keyword heuristics);
      - evaluate_expression(expr): AST-safe evaluation — numeric literals,
        + - * / // % ** and unary minus ONLY. No names, no calls, no
        attributes: nothing that could execute code;
      - reply_mentions_value(reply, value): numeric-equality match of a
        computed value inside reply text (verification seam).
  * manifest registration: 'calculate_expression', category system,
    safety_level 0, payload key 'expression' (arity contract).
  * observation routing: the exact live D1 question plans the calculator.
"""

import pytest

from app.tools.calculator import DeterministicCalculator


# ── extract_expression: the shared question detector ───────────────────

@pytest.mark.parametrize("text,expected", [
    ("What is 17 * 24?", "17 * 24"),                      # exact live D1 input
    ("what is 17*24", "17*24"),
    ("Calculate 17 * 24", "17 * 24"),
    ("compute 17*24 please", "17*24"),                   # trailing please
    ("what's 17 x 24?", "17*24"),                       # word operator x
    ("How much is 100 divided by 4?", "100 / 4"),
    ("What is 2 plus 2?", "2 + 2"),
    ("what is 10 minus 4", "10 - 4"),
    ("compute 2^10", "2**10"),
    ("What is 1,234 * 2?", "1234 * 2"),                  # thousands separator
    ("17 * 24", "17 * 24"),                              # bare expression
])
def test_extract_expression_arithmetic_questions(text, expected):
    assert DeterministicCalculator.extract_expression(text) == expected


@pytest.mark.parametrize("text", [
    "What is love?",                                     # no digits
    "What is the average of the amount column?",         # statistic ask (D2)
    "Find the file called 17",                           # file search, not math
    "What is your name?",
    "how much ram do I have",                            # host-state question
    "",                                                  # empty
])
def test_extract_expression_rejects_non_arithmetic(text):
    assert DeterministicCalculator.extract_expression(text) is None


# ── evaluate_expression: deterministic, AST-safe ────────────────────────

def test_evaluate_d1_ground_truth():
    res = DeterministicCalculator.evaluate_expression("17 * 24")
    assert res["success"] is True
    assert res["value"] == 408
    assert res["value_str"] == "408"


@pytest.mark.parametrize("expr,expected", [
    ("2 + 3 * 4", 14),          # precedence
    ("(2 + 3) * 4", 20),
    ("7 / 2", 3.5),
    ("7 // 2", 3),
    ("7 % 3", 1),
    ("2 ** 10", 1024),
    ("-5 + 3", -2),             # unary minus
    ("3.5 + 1.25", 4.75),
])
def test_evaluate_arithmetic_semantics(expr, expected):
    res = DeterministicCalculator.evaluate_expression(expr)
    assert res["success"] is True
    assert res["value"] == expected


@pytest.mark.parametrize("expr", [
    "__import__('os').system('rm -rf /')",
    "os.system('x')",
    "().__class__",
    "open('/etc/passwd')",
    "True + True",             # bool literals are not arithmetic operands
    "lambda: 1",
    "[1,2,3]",
    "'a' + 'b'",               # string literals are not arithmetic
    "17 * 24; import os",       # statements
])
def test_evaluate_rejects_non_arithmetic(expr):
    res = DeterministicCalculator.evaluate_expression(expr)
    assert res["success"] is False
    assert res.get("error_type") == "invalid_expression"


def test_evaluate_division_by_zero_is_a_typed_error():
    res = DeterministicCalculator.evaluate_expression("1 / 0")
    assert res["success"] is False
    assert res.get("error_type") == "arithmetic_error"
    assert "division" in res.get("error", "").lower()


def test_evaluate_exponent_guard():
    """10**10**10 style exponentiation would be a DoS vector."""
    res = DeterministicCalculator.evaluate_expression("9 ** 9 ** 9")
    assert res["success"] is False


# ── reply_mentions_value: the verification seam ─────────────────────────

def test_reply_mentions_value_matches():
    assert DeterministicCalculator.reply_mentions_value(
        "17 * 24 = 408", 408) is True
    assert DeterministicCalculator.reply_mentions_value(
        "The answer is 408.", 408.0) is True
    assert DeterministicCalculator.reply_mentions_value(
        "It is 1,234 items", 1234) is True


def test_reply_mentions_value_rejects_wrong_numbers():
    # The exact live failure: the 3B model answered 396 for 17 * 24.
    assert DeterministicCalculator.reply_mentions_value(
        "17 * 24 is 396", 408) is False
    assert DeterministicCalculator.reply_mentions_value("", 408) is False


# ── manifest registration + registry authority ──────────────────────────

def test_manifest_registration_level0():
    from app.cognition.tool_registry import capability_entry
    entry = capability_entry("calculate_expression")
    assert entry is not None, "calculate_expression must be in the manifest"
    assert int(entry.get("safety_level", 99)) == 0
    assert callable(entry.get("handler"))


def test_manifest_handler_executes_via_payload():
    from app.cognition.tool_registry import capability_entry
    handler = capability_entry("calculate_expression")["handler"]
    res = handler({"expression": "17 * 24"})
    assert res["success"] is True
    assert res["value"] == 408


def test_manifest_wrapper_arity_is_declared():
    """Wrong payload key must degrade to a typed error, never a TypeError
    (the N2 contract, applied to the new tool)."""
    from app.cognition.tool_registry import capability_entry
    handler = capability_entry("calculate_expression")["handler"]
    res = handler({"expr": "17 * 24"})  # wrong key
    assert res["success"] is False
    assert "expression" in str(res.get("expected_keys", res.get("error", "")))


def test_action_gate_allows_level0_read_only_calculation():
    from app.cognition.action_proposal import ActionProposal, ActionGate
    proposal = ActionProposal(
        action_type="calculate_expression",
        payload={"expression": "17 * 24"},
        recommendation_reason="deterministic arithmetic",
        confidence=0.9,
    )
    gate_res = ActionGate.evaluate_proposal(proposal)
    assert gate_res.allowed is True


# ── observation routing: the exact live D1 question ─────────────────────

def test_observation_router_plans_the_calculator():
    from app.cognition.observation_router import plan_observation
    plan = plan_observation("What is 17 * 24?")
    assert plan is not None
    assert plan.action_type == "calculate_expression"
    assert plan.payload["expression"] == "17 * 24"
    assert plan.question_kind == "arithmetic"


def test_observation_router_leaves_non_arithmetic_alone():
    from app.cognition.observation_router import plan_observation
    assert plan_observation("What is the average of the amount column?") is None or \
        plan_observation("What is the average of the amount column?").action_type != "calculate_expression"


def test_render_evidence_states_the_computed_answer():
    from app.cognition.observation_router import (
        plan_observation, render_observation_evidence,
    )
    from app.cognition.tool_registry import capability_entry
    plan = plan_observation("What is 17 * 24?")
    result = capability_entry("calculate_expression")["handler"](plan.payload)
    evidence = render_observation_evidence(result, plan)
    assert "408" in evidence
    assert "17 * 24" in evidence
