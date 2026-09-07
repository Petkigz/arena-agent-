#!/usr/bin/env python3
"""Run the existing regression suites, once, with explicit scope.

    python validate.py --quick   # bounded core contracts
    python validate.py --full    # full Python suite (the default)

This is software validation, not proof that all features are wired or that the
owner's physical devices/model work. Hardware and browser checks remain separate.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
QUICK_TESTS = (
    "tests/test_closed_loop_invariants.py",
    "tests/test_owner_control_plane.py",
    "tests/test_execution_control.py",
    "tests/test_unified_server.py",
    "tests/test_scoped_authorization.py",
    "tests/test_response_feedback_api.py",
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--quick", action="store_true", help="Run bounded core regression contracts")
    scope.add_argument("--full", action="store_true", help="Run the complete Python suite (default)")
    parser.add_argument("--timeout", type=int, default=1200, help="Maximum seconds for pytest (default 1200)")
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    return args


def run_validation(*, quick: bool = False, timeout: int = 1200) -> dict:
    """Use pytest's real result/exit code, not made-up component-wiring probes."""
    targets = list(QUICK_TESTS) if quick else ["tests/"]
    with tempfile.TemporaryDirectory(prefix="arena_validation_") as directory:
        temporary = Path(directory)
        data = temporary / "data"
        data.mkdir()
        report = temporary / "pytest.xml"
        env = {
            **os.environ,
            "ARENA_LLM_DISABLED": "1",
            "LPA_AUTONOMY_MODE": "off",
            "LPA_DATA_DIR": str(data),
            "LPA_DB_PATH": str(data / "assistant.db"),
        }
        command = [sys.executable, "-m", "pytest", *targets, "-q", "-ra", f"--junitxml={report}"]
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            return {"success": False, "scope": "quick" if quick else "full", "error": f"Validation timed out after {timeout}s", "output": str(exc.stdout or "")[-3000:]}
        counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
        if report.exists():
            for case in ET.parse(report).iter("testcase"):
                if case.find("failure") is not None:
                    counts["failed"] += 1
                elif case.find("error") is not None:
                    counts["errors"] += 1
                elif case.find("skipped") is not None:
                    counts["skipped"] += 1
                else:
                    counts["passed"] += 1
        return {
            "success": result.returncode == 0 and report.exists() and counts["passed"] > 0
                and counts["failed"] == 0 and counts["errors"] == 0,
            "scope": "quick" if quick else "full", "returncode": result.returncode,
            **counts, "output": result.stdout + result.stderr,
        }


def main(argv=None) -> int:
    args = parse_args(argv)
    print("Arena regression validation — not a live capability certification", flush=True)
    result = run_validation(quick=args.quick, timeout=args.timeout)
    print(result.get("output", ""))
    if result.get("error"):
        print(result["error"], file=sys.stderr)
    print(f"Scope: {result['scope']}; result: {'PASS' if result['success'] else 'FAIL'}")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
