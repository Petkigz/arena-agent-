"""Deterministic arithmetic evaluation (DIAG F3b, live incident D1).

Live bug (owner machine, 2026-09-01): 'What is 17 * 24?' was routed to the
3B chat model, which answered 396 — ground truth is 408 — and the goal
verified as 'achieved' because a reply existed. Arithmetic has exactly one
correct answer and the agent owns a CPU: the answer must come from THIS
deterministic evaluator, and the reply must be phrased from its evidence.

This module is the ONE shared home for three seams (no duplicated keyword
heuristics across consumers):
  * extract_expression(text) — is this question a pure arithmetic ask, and
    if so what is the expression? (used by the observation router AND the
    goal interpreter);
  * evaluate_expression(expr) — AST-safe evaluation: numeric literals,
    + - * / // % ** and unary signs ONLY. No names, no calls, no
    attributes, no string/bool literals — nothing that could execute code;
  * reply_mentions_value(reply, value) — numeric-equality match of a
    computed value inside reply text (the GoalVerifier's honesty seam: a
    reply that contradicts the deterministic answer is a FAILED answer,
    not an achieved goal).
"""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, Optional

# Length and magnitude guards: this evaluator answers chat-scale
# arithmetic, not arbitrary-precision number crunching. 200 chars and a
# 10_000 exponent cap keep '9 ** 9 ** 9' style expressions from becoming
# memory DoS vectors while leaving every realistic question untouched.
_MAX_EXPRESSION_CHARS = 200
_MAX_EXPONENT = 10_000

_ALLOWED_BINOPS = (
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
)
_ALLOWED_UNARYOPS = (ast.UAdd, ast.USub)


def extract_expression(text: str) -> Optional[str]:
    """The pure arithmetic expression inside an arithmetic question, or None.

    Conservative by design (matching the observation router's philosophy):
    anything with words left over after the question prefix and operator
    normalization is NOT a calculator question and returns None — a
    statistic ask like 'the average of the amount column' must fall
    through to the data pipeline, not land here.
    """
    if not text:
        return None
    t = text.strip()
    # Strip trailing interrogative punctuation, '=' tails and politeness.
    t = re.sub(r"[\s?=]+$", "", t).strip()
    t = re.sub(r"\s*(?:please|thanks|thank\s+you)[\s.!?]*$", "", t,
               flags=re.IGNORECASE).strip()
    # Strip a leading question/command prefix (repeatedly: 'can you
    # calculate ...' has two layers).
    prefix = re.compile(
        r"^(?:please|can\s+you|could\s+you|what(?:'s|\u2019s|\s+is|\s+are|"
        r"\s+was|\s+were)|whats|calculate|compute|evaluate|solve|"
        r"how\s+much\s+is|how\s+many\s+is|what\s+does)\s+",
        re.IGNORECASE,
    )
    while True:
        t2 = prefix.sub("", t, count=1)
        if t2 == t:
            break
        t = t2
    t = t.strip().rstrip("?= ").strip()
    # Normalize word/symbol operators to ASCII arithmetic.
    t = re.sub(r"\bdivided\s+by\b", "/", t, flags=re.IGNORECASE)
    t = re.sub(r"\bmultiplied\s+by\b", "*", t, flags=re.IGNORECASE)
    t = re.sub(r"\bplus\b", "+", t, flags=re.IGNORECASE)
    t = re.sub(r"\bminus\b", "-", t, flags=re.IGNORECASE)
    t = re.sub(r"\btimes\b", "*", t, flags=re.IGNORECASE)
    t = re.sub(r"(?<=\d)\s*[x\u00d7]\s*(?=\d)", "*", t)      # 17 x 24, 17 × 24
    t = t.replace("\u00f7", "/")
    t = re.sub(r"\^", "**", t)
    t = re.sub(r"(?<=\d),(?=\d)", "", t)                     # 1,234 -> 1234
    t = re.sub(r"\s+", " ", t).strip()
    # Pure arithmetic shape: digits, operators, parentheses, spaces — with
    # at least one digit. Any surviving letter disqualifies the text.
    if not t or len(t) > _MAX_EXPRESSION_CHARS:
        return None
    if not re.fullmatch(r"[\d\s+\-*/%().]*", t):
        return None
    if not re.search(r"\d", t):
        return None
    # Reject bare punctuation soup like '-' or '('.
    if not re.search(r"\d", t.replace(" ", "")):
        return None
    return t


def _eval_node(node: ast.AST) -> Any:
    """Evaluate an AST node under the arithmetic-only whitelist."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        # bool is a subclass of int — explicitly NOT an arithmetic operand.
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("only numeric literals are allowed")
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARYOPS):
        return +_eval_node(node.operand) if isinstance(node.op, ast.UAdd) \
            else -_eval_node(node.operand)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINOPS):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(float(right)) > _MAX_EXPONENT:
                raise ValueError(
                    f"exponent {right} exceeds the {_MAX_EXPONENT} guard"
                )
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left ** right
    raise ValueError(
        f"disallowed syntax in arithmetic expression: {type(node).__name__}"
    )


def _value_str(value: Any) -> str:
    """Honest rendering: ints stay ints; floats keep their exact repr
    (0.1 + 0.2 IS 0.30000000000000004 and the reply should not lie)."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    return repr(float(value))


def evaluate_expression(expression: str) -> Dict[str, Any]:
    """Deterministically evaluate an arithmetic expression.

    Returns {'success': True, 'expression', 'value', 'value_str'} or a
    typed error {'success': False, 'error_type', 'error'} — never raises,
    never executes anything but arithmetic.
    """
    expr = (expression or "").strip()
    if not expr:
        return {
            "success": False,
            "error_type": "invalid_expression",
            "error": "empty expression",
            "expression": expr,
        }
    if len(expr) > _MAX_EXPRESSION_CHARS:
        return {
            "success": False,
            "error_type": "invalid_expression",
            "error": f"expression longer than {_MAX_EXPRESSION_CHARS} characters",
            "expression": expr[:60] + "...",
        }
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError) as exc:
        return {
            "success": False,
            "error_type": "invalid_expression",
            "error": f"not a valid arithmetic expression: {exc}",
            "expression": expr,
        }
    try:
        value = _eval_node(tree)
    except ZeroDivisionError:
        return {
            "success": False,
            "error_type": "arithmetic_error",
            "error": "division by zero",
            "expression": expr,
        }
    except (ValueError, OverflowError) as exc:
        return {
            "success": False,
            "error_type": "invalid_expression",
            "error": str(exc),
            "expression": expr,
        }
    return {
        "success": True,
        "expression": expr,
        "value": value,
        "value_str": _value_str(value),
        "tool": "deterministic_calculator",
    }


def reply_mentions_value(reply: str, value: Any) -> bool:
    """Does the reply contain a number numerically equal to `value`?

    Commas inside digit runs count as thousands separators ('1,234' == 1234).
    Used by the GoalVerifier: a deterministic computation is ground truth,
    so a reply without the computed value has NOT delivered the answer.
    """
    if not reply:
        return False
    try:
        target = float(value)
    except (TypeError, ValueError):
        return False
    numbers = [
        float(m.replace(",", ""))
        for m in re.findall(r"\d[\d,]*(?:\.\d+)?", reply)
    ]
    tol = 1e-9 * max(1.0, abs(target))
    return any(abs(n - target) <= tol for n in numbers)


class DeterministicCalculator:
    """Manifest tool surface: handler(payload) with payload key
    'expression' (the N2 arity contract — the declared key IS the handler
    parameter, and it is REQUIRED so a wrong payload key degrades to the
    typed arity error instead of an empty-expression result).

    The shared seams are bound as staticmethods so consumers can use the
    class OR the module functions — one implementation either way."""

    evaluate = staticmethod(evaluate_expression)
    evaluate_expression = staticmethod(evaluate_expression)
    extract_expression = staticmethod(extract_expression)
    reply_mentions_value = staticmethod(reply_mentions_value)
