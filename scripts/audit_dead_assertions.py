#!/usr/bin/env python3
"""Static audit: assertions that can NEVER execute.

The never-executed-assertion pattern (owner reviews 2026-09-03/04): an
assertion sits after an earlier statement that unconditionally ends the
block — return / raise / break / continue / pytest.skip() — so it can
never run, coverage looks deceptively high, and the first time the
earlier statements stop failing, the dead assertion turns out to be
wrong (three owner round-trips: the autonomy priority default, the
schedule title-clear, the pip test's post-skip code).

Rules (deliberately STRICT, zero false-positive tolerance):
  * only statements in the SAME block after a terminal statement are
    reported — code after `if x: return` is reachable and never flagged;
  * pytest.importorskip() is NOT terminal (it skips only when the import
    is missing; the code after it is the whole point when it isn't);
  * nested functions are audited separately, never double-counted.

Exit code 1 when findings exist, 0 when clean — CI-able as-is.
"""
from __future__ import annotations

import ast
import sys
from collections import deque
from pathlib import Path

TERMINAL_STMTS = (ast.Return, ast.Raise, ast.Break, ast.Continue)
FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _is_unconditional_pytest_skip(stmt: ast.stmt) -> bool:
    """A plain `pytest.skip(...)` expression statement — always terminal."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Attribute)
        and stmt.value.func.attr == "skip"
        and isinstance(stmt.value.func.value, ast.Name)
        and stmt.value.func.value.id == "pytest"
    )


def _walk_without_nested_functions(root: ast.AST):
    """All descendants of root, not descending into nested function defs
    (each function is audited exactly once, under its own name)."""
    todo = deque([root])
    while todo:
        node = todo.popleft()
        if node is not root and isinstance(node, FUNC_NODES):
            continue
        yield node
        todo.extend(ast.iter_child_nodes(node))


def _blocks_within(func: ast.AST):
    """Every statement-list block owned by this function (bodies, orelse,
    finalbody, except handlers, match cases) — excluding nested defs."""
    for node in _walk_without_nested_functions(func):
        if isinstance(node, ast.match_case):
            if node.body:
                yield node.body
            continue
        if isinstance(node, ast.ExceptHandler):
            # its body is yielded via the owning Try.handlers pass below
            continue
        for attr in ("body", "orelse", "finalbody"):
            block = getattr(node, attr, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                yield block
        for handler in getattr(node, "handlers", None) or []:
            if handler.body:
                yield handler.body


def audit_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [{"file": str(path), "func": "<module>",
                 "line": exc.lineno or 0, "detail": f"SYNTAX ERROR: {exc}"}]

    def visit(func: ast.AST, name: str) -> None:
        for block in _blocks_within(func):
            for index, stmt in enumerate(block):
                terminal = isinstance(stmt, TERMINAL_STMTS) or _is_unconditional_pytest_skip(stmt)
                if not terminal:
                    continue
                dead = block[index + 1:]
                if not dead:
                    continue
                dead_asserts = sum(
                    1 for ds in dead for sub in ast.walk(ds) if isinstance(sub, ast.Assert)
                )
                findings.append({
                    "file": str(path),
                    "func": name,
                    "line": dead[0].lineno,
                    "detail": (
                        f"{len(dead)} unreachable statement(s) after "
                        f"{getattr(stmt, 'end_lineno', stmt.lineno) and ''}"
                        f"{'pytest.skip()' if _is_unconditional_pytest_skip(stmt) else type(stmt).__name__.lower()}"
                        f" at line {stmt.lineno}"
                        + (f" — {dead_asserts} of them ASSERTIONS"
                           if dead_asserts else "")
                    ),
                })

    stack: list[str] = []

    def recurse(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, FUNC_NODES):
                stack.append(child.name)
                visit(child, ".".join(stack))
                recurse(child)
                stack.pop()
            else:
                recurse(child)

    recurse(tree)
    return findings


def main(argv: list[str]) -> int:
    roots = [Path(p) for p in argv[1:]] or [Path("tests")]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(sorted(root.glob("test_*.py")))
            files.extend(sorted(root.glob("*/test_*.py")))
    findings: list[dict] = []
    for path in files:
        findings.extend(audit_file(path))
    if not files:
        print("no test files found under the given roots", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"{finding['file']}:{finding['line']} in {finding['func']}: {finding['detail']}")
    print(f"\naudited {len(files)} files, {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
