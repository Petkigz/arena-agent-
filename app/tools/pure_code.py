"""Pure-computation evaluator — the deterministic calculator's class of
risk, for code-shaped asks (DIAG D8, owner review item 6, 2026-09-01).

Live incident: 'Run this Python code and tell me the output:
print(sum(range(1, 101)))' routed to local_execute (Level 3) and
blocked at the policy gate — a PURE computation was demanding the
authority level of an arbitrary OS command.

A snippet qualifies as PURE only when the AST contains nothing but
literals, arithmetic/comparison/boolean operators, comprehensions, and
calls to whitelisted pure builtins. Parsed in eval mode, so statements
(imports, assignments) are rejected by the parser itself; attribute
access, subscripts, lambdas, and the power operator are rejected by the
walk; a literal-bound cap bounds the loop space. By construction the
evaluation CANNOT touch the file system, the network, or the process
table — which is why it runs at Level 0 (the calculator's level), not
Level 3. Anything that fails this validation keeps routing to
local_execute and the approval gate — the gate is NOT weakened.
"""

from __future__ import annotations

import ast
import io
import re
import contextlib
from typing import Any, Dict

from app.utils.logger import app_logger

# Whitelisted pure builtins. print is included (stdout only, captured).
PURE_BUILTINS = (
    "sum", "range", "len", "min", "max", "abs", "round", "sorted",
    "reversed", "list", "tuple", "set", "dict", "str", "int", "float",
    "bool", "enumerate", "zip", "print",
)

# Loop-space guard: range/len bounds are literals in pure code (no names
# other than builtins exist), so capping integer literals caps the work.
# A nested-comprehension bomb ('[[0]*N for _ in range(N)]') is multiplicative
# in literals, so the PRODUCT of all int literals is capped too.
_MAX_LITERAL = 1_000_000
_MAX_LITERAL_PRODUCT = 50_000_000
_MAX_CODE_CHARS = 2000

_ALLOWED_NODES = (
    ast.Expression, ast.Constant, ast.Name, ast.Load, ast.Store,
    ast.Call, ast.keyword,
    # Operator wrappers + operators (Pow deliberately EXCLUDED:
    # 10**10**10 is a DoS vector).
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.USub, ast.UAdd, ast.Not,
    ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    # Containers / conditionals / comprehensions.
    ast.IfExp, ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension,
    # f-strings of literals.
    ast.JoinedStr, ast.FormattedValue,
)


class PureCode:
    """Manifest tool surface: handler(payload) with payload key 'code'."""

    @staticmethod
    def is_pure(code: str) -> bool:
        """True iff the snippet is a pure expression (see module doc)."""
        src = str(code or "").strip()
        if not src or len(src) > _MAX_CODE_CHARS:
            return False
        try:
            tree = ast.parse(src, mode="eval")
        except (SyntaxError, ValueError):
            return False
        bound: set = set()  # comprehension-bound names
        # Pre-pass: ast.walk is BFS, so a comprehension's element is
        # visited BEFORE its 'for x in ...' clause — collect targets
        # first or the element's use of x would read as unbound.
        for node in ast.walk(tree):
            if isinstance(node, ast.comprehension):
                for t in ast.walk(node.target):
                    if isinstance(t, ast.Name):
                        bound.add(t.id)
        literal_product = 1
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED_NODES):
                return False
            if isinstance(node, ast.Constant):
                if isinstance(node.value, int) and abs(node.value) > _MAX_LITERAL:
                    return False
                if isinstance(node.value, int) and abs(node.value) > 1:
                    literal_product *= abs(node.value)
                if isinstance(node.value, str) and len(node.value) > 1000:
                    return False
            elif isinstance(node, ast.Call):
                if not (isinstance(node.func, ast.Name)
                        and node.func.id in PURE_BUILTINS):
                    return False
            elif isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Load) and node.id not in PURE_BUILTINS \
                        and node.id not in bound:
                    return False
        # Multiplicative work bound: a nested comprehension bomb
        # ('[[0]*N for _ in range(N)]') scales as the product of its
        # literals, and each literal alone passes the single-literal cap.
        if literal_product > _MAX_LITERAL_PRODUCT:
            return False
        return True

    @staticmethod
    def evaluate(code: str) -> Dict[str, Any]:
        """Evaluate a pure snippet deterministically.

        Returns {'success': True, 'code', 'output', 'value',
        'value_str'} — output is what print produced (or the expression's
        repr), value is the numeric value when one exists (for the
        GoalVerifier's deterministic-answer contract)."""
        src = str(code or "").strip()
        if not PureCode.is_pure(src):
            return {"success": False,
                    "error": "not pure computation (imports, I/O, attribute "
                             "access, or unbounded literals present)"}
        try:
            tree = ast.parse(src, mode="eval")
            env = {name: _BUILTIN_FUNCS[name] for name in PURE_BUILTINS}
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                value = eval(  # noqa: S307 — AST-validated pure expression
                    compile(tree, "<pure_code>", "eval"),
                    {"__builtins__": {}, **env})
            output = buffer.getvalue().strip() or (repr(value) if value is not None else "")
        except Exception as exc:
            return {"success": False, "error": f"evaluation failed: {exc}"}
        numeric = value
        if not isinstance(numeric, (int, float)) or isinstance(numeric, bool):
            try:
                numeric = float(output.replace(",", "")) if output else None
            except (TypeError, ValueError):
                numeric = None
        value_str = None
        if numeric is not None:
            value_str = (str(int(numeric)) if float(numeric).is_integer()
                         else repr(float(numeric)))
        app_logger.info(
            f"Pure code evaluated deterministically: {src[:80]!r} -> "
            f"{output[:80]!r}")
        return {
            "success": True,
            "code": src,
            "output": output,
            "value": numeric,
            "value_str": value_str,
        }


# The actual builtin objects — resolved once; eval sees ONLY these.
_BUILTIN_FUNCS = {
    "sum": sum, "range": range, "len": len, "min": min, "max": max,
    "abs": abs, "round": round, "sorted": sorted, "reversed": reversed,
    "list": list, "tuple": tuple, "set": set, "dict": dict, "str": str,
    "int": int, "float": float, "bool": bool, "enumerate": enumerate,
    "zip": zip, "print": print,
}


def is_pure_code(code: str) -> bool:
    return PureCode.is_pure(code)


def evaluate_pure_code(code: str) -> Dict[str, Any]:
    return PureCode.evaluate(code)
