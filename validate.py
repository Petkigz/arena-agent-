#!/usr/bin/env python3
"""
Validation script for Arena cognitive system.

Runs key tests and outputs a summary for easy sharing.
Phase 1.3 of the wiring plan.

Usage:
    python validate.py
    python validate.py --full  # Run all tests
    python validate.py --quick  # Run quick validation only
"""

import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime


def run_command(cmd: list, timeout: int = 300) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def check_imports() -> dict:
    """Check that all key modules can be imported."""
    modules = [
        "app.cognition.runtime",
        "app.cognition.belief_engine",
        "app.cognition.goal_verifier",
        "app.cognition.skill_classifier",
        "app.cognition.analogical_memory",
        "app.cognition.planning_patterns",
        "app.cognition.resource_allocator",
        "app.cognition.confidence_calibrator",
        "app.cognition.self_model",
    ]
    
    results = {}
    for module in modules:
        code, stdout, stderr = run_command([
            sys.executable, "-c", f"import {module}"
        ], timeout=10)
        results[module] = code == 0
    
    return results


def run_pytest(test_path: str, timeout: int = 300) -> dict:
    """Run pytest and parse results."""
    code, stdout, stderr = run_command([
        sys.executable, "-m", "pytest", test_path, "-v", "--tb=no"
    ], timeout=timeout)
    
    # Parse output
    passed = stdout.count(" PASSED")
    failed = stdout.count(" FAILED")
    errors = stdout.count(" ERROR")
    
    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "success": code == 0,
        "output": stdout[-500:] if len(stdout) > 500 else stdout  # Last 500 chars
    }


def test_runtime_basic() -> dict:
    """Test basic runtime functionality."""
    test_code = """
from app.cognition.runtime import CognitiveRuntime
import tempfile
import os

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = os.path.join(tmpdir, "test.db")
    runtime = CognitiveRuntime(db_path=db_path)
    
    # Test simple query
    result = runtime.process_cognitive_cycle(
        user_text="What is Python?",
        complexity="fast"
    )
    
    assert result["request_success"] is True
    assert "assistant_reply" in result
    assert len(result["assistant_reply"]) > 0
    
    print("PASS: Basic runtime works")
"""
    
    code, stdout, stderr = run_command([
        sys.executable, "-c", test_code
    ], timeout=30)
    
    return {
        "success": code == 0 and "PASS" in stdout,
        "output": stdout + stderr
    }


def test_component_wiring() -> dict:
    """Test that all components are wired."""
    test_code = """
from app.cognition.runtime import CognitiveRuntime
import tempfile
import os

with tempfile.TemporaryDirectory() as tmpdir:
    db_path = os.path.join(tmpdir, "test.db")
    runtime = CognitiveRuntime(db_path=db_path)
    
    # Check all components exist
    assert hasattr(runtime, 'skills')
    assert hasattr(runtime, 'analogies')
    assert hasattr(runtime, 'patterns')
    assert hasattr(runtime, 'resource_allocator')
    assert hasattr(runtime, 'confidence_calibrator')
    assert hasattr(runtime, 'self_model')
    
    # Execute a task to trigger all components
    result = runtime.process_cognitive_cycle(
        user_text="Find configuration files",
        complexity="fast"
    )
    
    assert result["request_success"] is True
    
    # Check learning happened
    assert runtime.outcomes.total_recorded() >= 1
    assert runtime.lessons.total_lessons() >= 1
    assert runtime.analogies.total_signatures() >= 1
    
    print("PASS: All components wired and working")
"""
    
    code, stdout, stderr = run_command([
        sys.executable, "-c", test_code
    ], timeout=30)
    
    return {
        "success": code == 0 and "PASS" in stdout,
        "output": stdout + stderr
    }


def main():
    """Run validation and print summary."""
    print("=" * 70)
    print("ARENA COGNITIVE SYSTEM VALIDATION")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    results = {}
    
    # 1. Check imports
    print("1. Checking module imports...")
    results["imports"] = check_imports()
    passed = sum(1 for v in results["imports"].values() if v)
    total = len(results["imports"])
    print(f"   {passed}/{total} modules imported successfully")
    print()
    
    # 2. Test basic runtime
    print("2. Testing basic runtime...")
    results["runtime_basic"] = test_runtime_basic()
    print(f"   {'PASS' if results['runtime_basic']['success'] else 'FAIL'}")
    print()
    
    # 3. Test component wiring
    print("3. Testing component wiring...")
    results["component_wiring"] = test_component_wiring()
    print(f"   {'PASS' if results['component_wiring']['success'] else 'FAIL'}")
    print()
    
    # 4. Run unit tests
    print("4. Running unit tests...")
    results["unit_tests"] = run_pytest("tests/", timeout=300)
    print(f"   {results['unit_tests']['passed']} passed, {results['unit_tests']['failed']} failed")
    print()
    
    # 5. Run integration tests
    print("5. Running integration tests...")
    results["integration_tests"] = run_pytest("tests/test_integration_full_pipeline.py", timeout=120)
    print(f"   {results['integration_tests']['passed']} passed, {results['integration_tests']['failed']} failed")
    print()
    
    # Summary
    print("=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    all_pass = (
        all(results["imports"].values()) and
        results["runtime_basic"]["success"] and
        results["component_wiring"]["success"] and
        results["unit_tests"]["success"] and
        results["integration_tests"]["success"]
    )
    
    print(f"Overall Status: {'✓ PASS' if all_pass else '✗ FAIL'}")
    print()
    print("Details:")
    print(f"  - Module imports: {sum(results['imports'].values())}/{len(results['imports'])}")
    print(f"  - Basic runtime: {'✓' if results['runtime_basic']['success'] else '✗'}")
    print(f"  - Component wiring: {'✓' if results['component_wiring']['success'] else '✗'}")
    print(f"  - Unit tests: {results['unit_tests']['passed']} passed, {results['unit_tests']['failed']} failed")
    print(f"  - Integration tests: {results['integration_tests']['passed']} passed, {results['integration_tests']['failed']} failed")
    print()
    
    if not all_pass:
        print("FAILURES:")
        if not all(results["imports"].values()):
            failed_imports = [k for k, v in results["imports"].items() if not v]
            print(f"  - Failed imports: {', '.join(failed_imports)}")
        if not results["runtime_basic"]["success"]:
            print(f"  - Runtime basic test failed")
        if not results["component_wiring"]["success"]:
            print(f"  - Component wiring test failed")
        if not results["unit_tests"]["success"]:
            print(f"  - Unit tests: {results['unit_tests']['failed']} failures")
        if not results["integration_tests"]["success"]:
            print(f"  - Integration tests: {results['integration_tests']['failed']} failures")
        print()
    
    print("=" * 70)
    print("Copy this output and share it with the Arena team.")
    print("=" * 70)
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
