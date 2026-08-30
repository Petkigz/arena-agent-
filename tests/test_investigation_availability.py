"""P0 review #1: InvestigationExecutor availability — ONE interpretation.

Manifest availability checkers return DICTS. {"available": False} is truthy,
so the old `if checker() is False:` in
InvestigationExecutor._execute_from_manifest never fired — a tool with a
missing dependency had its handler attempted anyway. All consumers now route
through ToolRegistry.interpret_availability: one canonical meaning for
available True / False / None, and for plain-boolean checkers.
"""

from unittest.mock import patch

from app.cognition.action_selection import (
    InvestigationExecutor,
    InvestigationPlan,
)
from app.cognition.tool_registry import interpret_availability


def _plan(tool="probe_tool"):
    return InvestigationPlan(tool=tool, arguments={}, target="t",
                             reason="test", priority=1)


def _manifest_entry(checker):
    return {
        "name": "probe_tool", "category": "system", "safety_level": 0,
        "handler": lambda **kw: {"success": True, "executed": True},
        "availability": checker,
    }


def _execute_with_manifest(entry):
    import app.tools.manifest as manifest_mod
    with patch("app.tools.manifest.get_tool_manifest", return_value={"probe_tool": entry}):
        return InvestigationExecutor().execute(_plan())


def test_unavailable_dict_checker_refuses_before_handler():
    """THE bug: {'available': False, ...} is a TRUTHY dict. The handler must
    never run; the refusal must NAME the missing dependency."""
    handler_calls = []

    def handler(**kw):
        handler_calls.append(kw)
        return {"success": True}

    entry = _manifest_entry(
        lambda probe=False: {
            "available": False,
            "status": "dependency_unavailable",
            "missing_dependency": "playwright",
        })
    entry["handler"] = handler

    result = _execute_with_manifest(entry)
    assert result.success is False
    assert "playwright" in result.error
    assert handler_calls == [], "handler ran despite a missing dependency"


def test_available_dict_checker_runs_handler():
    entry = _manifest_entry(lambda probe=False: {"available": True, "status": "available"})
    result = _execute_with_manifest(entry)
    assert result.success is True
    assert result.output == {"success": True, "executed": True}


def test_plain_false_checker_still_refuses():
    """Backward compatibility: checkers returning a bare False keep working."""
    handler_calls = []

    def handler(**kw):
        handler_calls.append(kw)
        return {"success": True}

    entry = _manifest_entry(lambda: False)
    entry["handler"] = handler
    result = _execute_with_manifest(entry)
    assert result.success is False
    assert handler_calls == []


def test_plain_true_and_no_checker_run_handler():
    assert _execute_with_manifest(_manifest_entry(lambda: True)).success is True
    entry = _manifest_entry(lambda: True)
    entry["availability"] = None
    assert _execute_with_manifest(entry).success is True


def test_not_checked_after_probe_is_attempted_and_caught_honestly():
    """available=None (still undecidable after probing) is NOT False: the
    probe runs, and if it truly fails the exception is reported honestly."""
    entry = _manifest_entry(lambda probe=False: {"available": None, "status": "not_checked"})
    result = _execute_with_manifest(entry)
    assert result.success is True  # undecidable != refused


def test_interpret_availability_canonical_shapes():
    assert interpret_availability(None) == {"available": True, "status": "available"}
    assert interpret_availability(lambda probe=False: {"available": False})["available"] is False
    assert interpret_availability(lambda: False)["available"] is False
    assert interpret_availability(lambda: True)["available"] is True
    assert interpret_availability(lambda probe=False: {"available": None})["available"] is None
    # None is never coerced to a boolean.
    assert interpret_availability(lambda: None)["available"] is None


def test_gated_safety_still_refuses_before_availability():
    """Safety ceiling is checked before availability — order preserved."""
    entry = _manifest_entry(lambda: True)
    entry["safety_level"] = 3
    result = _execute_with_manifest(entry)
    assert result.success is False
    assert "gated execution" in result.error.lower()
