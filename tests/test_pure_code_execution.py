"""P1 (live 2026-09-01, D8, owner review item 6): a PURE deterministic
computation should not require the authority level of an arbitrary OS
command — and the gate must not be weakened globally to make that true.

Live incident: 'Run this Python code and tell me the output:
print(sum(range(1, 101)))' routed to local_execute (Level 3) and
blocked at the policy gate (owner limit 2) — the benchmark expected
5050.

Decision (Option B, scoped): pure-computation snippets — AST-validated
to contain ONLY literals, operators, and whitelisted pure builtins (no
imports possible in eval mode, no attribute access, no subscripts, no
power, no assignments, no lambdas) — execute through a deterministic
Level-0 evaluator, the calculator's own risk class: it CANNOT touch
the file system, network, or process table by construction. Anything
else (open(), os.*, imports, __import__) still routes to local_execute
at Level 3 and the approval gate — unchanged.

The chain mirrors arithmetic (D1): router plans the deterministic tool
-> Level-0 observation executes -> VERIFIED COMPUTATION evidence ->
deterministic answer recorded -> the verifier requires the reply to
state the output.
"""

import pytest

from app.cognition.observation_router import (
    plan_observation, render_observation_evidence)
from app.cognition.goal_interpreter import SemanticGoalInterpreter
from app.cognition.goal_lifecycle import GoalLifecycleState
from app.cognition.goal_verifier import GoalVerifier

D8_TEXT = ("Run this Python code and tell me the output: "
           "print(sum(range(1, 101)))")


# ── purity validation: what may run without the gate ───────────────────

def test_pure_computations_are_detected():
    from app.tools.pure_code import is_pure_code
    assert is_pure_code("print(sum(range(1, 101)))")
    assert is_pure_code("sum(range(1, 101))")
    assert is_pure_code("[x * x for x in range(10)]")
    assert is_pure_code("max(1, 2, 3) + len('abc')")


def test_impure_code_is_rejected():
    from app.tools.pure_code import is_pure_code
    assert not is_pure_code("import os")                 # eval-mode syntax error
    assert not is_pure_code("open('/etc/passwd')")       # not a whitelisted builtin
    assert not is_pure_code("os.system('rm -rf /')")     # attribute access
    assert not is_pure_code("__import__('os')")          # not whitelisted
    assert not is_pure_code("print(open('f').read())")   # attribute access
    assert not is_pure_code("x = 5")                     # statement, not expression
    assert not is_pure_code("(lambda: 1)()")             # lambda
    assert not is_pure_code("10 ** 100000")              # power operator (DoS)
    assert not is_pure_code("sum(range(100000000))")     # literal over the bound cap
    # Nested-comprehension bomb: each literal passes the single-literal
    # cap; the PRODUCT does not (the work is multiplicative in literals).
    assert not is_pure_code("[[0] * 999999 for _ in range(999999)]")
    assert not is_pure_code("[[y for y in range(999999)] for _ in range(999999)]")
    # ...but ordinary comprehension work stays allowed.
    assert is_pure_code("[x * x for x in range(10000)]")
    assert is_pure_code("sum(x * x for x in range(1, 101))")


# ── the evaluator ───────────────────────────────────────────────────────

def test_evaluate_returns_the_printed_output():
    from app.tools.pure_code import evaluate_pure_code
    res = evaluate_pure_code("print(sum(range(1, 101)))")
    assert res["success"] is True
    assert res["output"].strip() == "5050"
    assert res["value"] == 5050


def test_evaluate_returns_the_expression_value():
    from app.tools.pure_code import evaluate_pure_code
    res = evaluate_pure_code("sum(range(1, 101))")
    assert res["success"] is True
    assert res["value"] == 5050
    assert res["value_str"] == "5050"


def test_evaluate_honest_on_error():
    from app.tools.pure_code import evaluate_pure_code
    res = evaluate_pure_code("sum(range(1, 101)) / 0")
    assert res["success"] is False
    assert res.get("error")


def test_manifest_registers_pure_evaluator_at_level_0():
    from app.cognition.tool_registry import capability_entry
    entry = capability_entry("evaluate_pure_code")
    assert entry is not None
    assert int(entry.get("safety_level", 99)) == 0, (
        "pure computation is the calculator's risk class — Level 0 by "
        "construction (no I/O possible), NOT a gate weakening")


# ── routing: pure runs free, arbitrary code stays gated ────────────────

def test_router_plans_deterministic_evaluation_for_pure_code():
    plan = plan_observation(D8_TEXT)
    assert plan is not None
    assert plan.action_type == "evaluate_pure_code"
    assert plan.question_kind == "pure_code"
    assert plan.payload["code"] == "print(sum(range(1, 101)))"


def test_router_leaves_arbitrary_code_to_the_gated_path():
    """open() is NOT pure: no deterministic plan — the matcher's
    local_execute (Level 3, approval-gated) keeps it. The gate is NOT
    weakened."""
    plan = plan_observation(
        "Run this Python code and tell me the output: open('x.txt').read()")
    assert plan is None


def test_matcher_still_routes_arbitrary_code_to_local_execute():
    from app.cognition.tool_matcher import match_control_tool
    m = match_control_tool(
        "Run this Python code and tell me the output: open('x.txt').read()")
    assert m is not None
    assert m.action_type == "local_execute"


# ── the chain: evidence -> reply must state the output ─────────────────

def test_renderer_states_the_verified_output():
    plan = plan_observation(D8_TEXT)
    from app.cognition.tool_registry import capability_entry
    result = capability_entry(plan.action_type)["handler"](plan.payload)
    evidence = render_observation_evidence(result, plan)
    assert "VERIFIED COMPUTATION" in evidence
    assert "5050" in evidence
    assert "State 5050" in evidence


def test_verifier_requires_the_output_in_the_reply():
    rep = SemanticGoalInterpreter.interpret_goal(D8_TEXT)
    observed = {"deterministic_answers": [
        {"expression": "print(sum(range(1, 101)))",
         "value": 5050, "value_str": "5050"}]}
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "The code ran fine.", observed_state=observed)
    assert res.verified_success is False
    assert res.final_state == GoalLifecycleState.FAILED
    res = GoalVerifier.verify_goal_achievement(
        rep, [], "The output is 5050.", observed_state=observed)
    assert res.verified_success is True
    assert res.final_state == GoalLifecycleState.ACHIEVED
