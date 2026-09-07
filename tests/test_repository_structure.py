"""Structural regression gates, not a claim that every runtime path is verified.

These checks catch recurring copy/paste defects without deleting framework
callbacks, public compatibility exports, or owner-retained unwired features.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import get_type_hints

ROOT = Path(__file__).resolve().parents[1]


def tracked_python():
    files = subprocess.check_output(["git", "ls-files", "-z", "*.py"], cwd=ROOT).decode().split("\0")
    return [ROOT / file for file in files if file and (ROOT / file).exists()]


def test_every_tracked_python_file_parses():
    for path in tracked_python():
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_production_names_imports_and_locals_are_consistent():
    files = [str(path.relative_to(ROOT)) for path in tracked_python() if not path.is_relative_to(ROOT / "tests")]
    for offset in range(0, len(files), 100):
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--select", "F", "--target-version", "py311",
             "--output-format", "concise", *files[offset:offset + 100]],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_no_statements_after_unconditional_termination():
    from scripts.audit_dead_assertions import audit_file

    findings = [finding for path in tracked_python() for finding in audit_file(path)]
    assert findings == [], findings


def test_registered_http_routes_are_not_shadowed():
    from fastapi.routing import APIRoute
    from app.main import app as legacy_app
    from app.server import app as unified_app

    for app in (legacy_app, unified_app):
        seen = {}
        previous = []
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            # Parameter names do not make two otherwise identical URL matchers
            # distinct. Keep converter differences (int/path/string) intact.
            pattern = re.sub(r"\(\?P<[^>]+>", "(?P<parameter>", route.path_regex.pattern)
            for method in route.methods:
                key = (method, pattern)
                assert key not in seen, f"{method} {route.path}: {route.name} shadows {seen.get(key)}"
                seen[key] = route.name
            if "{" not in route.path:
                for older in previous:
                    assert not (older.methods & route.methods and older.path_regex.fullmatch(route.path)), (
                        f"Static route {route.path} is shadowed by {older.path}"
                    )
            previous.append(route)


def test_core_router_has_no_dropped_asset_mounts():
    from starlette.routing import Mount
    from app.main import router

    assert not any(isinstance(route, Mount) for route in router.routes)


def test_legacy_pipeline_names_are_aliases_not_parallel_implementations():
    from app.cognition.cognitive_pipeline import CognitivePipeline
    from app.cognition.pipeline import CognitivePipeline as LegacyPipeline, PipelineBridge

    assert LegacyPipeline is CognitivePipeline
    assert PipelineBridge is CognitivePipeline


def test_model_router_annotations_resolve():
    from app.llm import LocalLLMClient

    assert get_type_hints(LocalLLMClient._resolve_model)["return"]
