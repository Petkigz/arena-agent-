"""Pins the never-executed-assertion auditor (owner review 2026-09-04).

It MUST catch the pattern that cost three owner round-trips — assertions
stranded after a terminal statement or an unconditional pytest.skip() —
including the exact pre-fix shape of the pip test (code inside the
`if not HAS_PIP:` body AFTER the skip call), and must NOT flag code that
is merely after a CONDITIONAL return/skip (that is the normal,
reachable kind)."""

import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from audit_dead_assertions import audit_file  # noqa: E402


def _findings_for(source: str) -> list:
    with tempfile.NamedTemporaryFile("w", suffix="_test_audit.py",
                                     delete=False) as handle:
        handle.write(source)
        path = Path(handle.name)
    try:
        return audit_file(path)
    finally:
        path.unlink(missing_ok=True)


def test_assert_after_return_is_flagged():
    src = "def test_x():\n    return\n    assert 1 == 2\n"
    findings = _findings_for(src)
    assert len(findings) == 1, findings
    assert "ASSERTIONS" in findings[0]["detail"], findings[0]


def test_code_after_unconditional_pytest_skip_is_flagged():
    src = ("def test_x():\n"
           "    import pytest\n"
           "    pytest.skip('gone')\n"
           "    result = do_thing()\n"
           "    assert result\n")
    findings = _findings_for(src)
    assert len(findings) == 1, findings
    assert "pytest.skip()" in findings[0]["detail"], findings[0]


def test_code_inside_if_body_after_skip_is_flagged():
    """The exact pre-fix shape of the pip test (2026-09-04): code placed
    INSIDE the `if not HAS_PIP:` block after the skip call — unreachable
    whenever the module-level flag is true, and dead-miss when it is
    false (the skip already ended the test)."""
    src = ("def test_x():\n"
           "    if not HAS_PIP:\n"
           "        import pytest\n"
           "        pytest.skip('pip not available')\n"
           "        res = list_packages()\n"
           "        assert res['success']\n"
           "    assert res['count'] >= 1\n")
    findings = _findings_for(src)
    assert len(findings) == 1, findings
    assert findings[0]["line"] == 5, findings[0]
    assert "ASSERTIONS" in findings[0]["detail"], findings[0]


def test_code_after_conditional_return_is_not_flagged():
    src = ("def test_x():\n"
           "    if not HAS_PIP:\n"
           "        return\n"
           "    res = do_thing()\n"
           "    assert res\n")
    assert _findings_for(src) == []


def test_code_after_conditional_skip_is_not_flagged():
    """importorskip/conditional skip leaves the following code reachable —
    the auditor must not cry wolf on the standard guard pattern."""
    src = ("def test_x():\n"
           "    if not HAS_PIP:\n"
           "        import pytest\n"
           "        pytest.skip('pip not available')\n"
           "    res = do_thing()\n"
           "    assert res\n")
    assert _findings_for(src) == []


def test_raise_in_except_with_dead_code_is_flagged():
    src = ("def test_x():\n"
           "    try:\n"
           "        do_thing()\n"
           "    except Exception:\n"
           "        raise\n"
           "        assert False\n")
    findings = _findings_for(src)
    assert len(findings) == 1, findings


def test_nested_function_reported_under_its_own_name():
    src = ("def outer():\n"
           "    def inner():\n"
           "        return\n"
           "        assert False\n"
           "    return inner\n")
    findings = _findings_for(src)
    assert len(findings) == 1, findings
    assert findings[0]["func"] == "outer.inner", findings[0]


def test_break_in_loop_only_kills_same_block():
    src = ("def test_x():\n"
           "    for i in range(3):\n"
           "        if i:\n"
           "            break\n"
           "    assert True\n")
    assert _findings_for(src) == []
