"""Optional tool dependencies must never become whole-runtime dependencies."""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

import app.tools.manifest as manifest_module
from app.cognition.tool_registry import ToolRegistry


OPTIONAL_TOOL_MODULES = {
    "app.tools.web_research": "bs4",
    "app.tools.data_analyzer": "pandas",
    "app.tools.youtube_learner": "youtube_transcript_api",
    "app.tools.pdf_toolkit": "pypdf",
    "app.tools.ocr_reader": "pytesseract",
    "app.tools.screen_capture": "mss",
}


@pytest.fixture(autouse=True)
def isolated_manifest_cache():
    saved = manifest_module._TOOL_MANIFEST
    manifest_module._TOOL_MANIFEST = None
    try:
        yield
    finally:
        manifest_module._TOOL_MANIFEST = saved


def test_api_module_import_survives_blocked_optional_packages():
    script = r'''
import builtins
real_import = builtins.__import__
blocked = {
    "bs4", "pandas", "youtube_transcript_api", "pypdf", "docx",
    "pytesseract", "mss", "playwright", "faster_whisper",
}
def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".", 1)[0] in blocked:
        raise ModuleNotFoundError(f"blocked optional dependency: {name}", name=name)
    return real_import(name, globals, locals, fromlist, level)
builtins.__import__ = guarded_import
import app.main
import app.server
assert app.server.runtime is app.server.CognitiveRuntime.get_instance()
print("api-import-ok")
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "api-import-ok" in completed.stdout


def test_manifest_and_registry_do_not_import_optional_tool_modules(monkeypatch):
    real_import_module = importlib.import_module
    imported = []

    def recording_import(name, package=None):
        imported.append(name)
        if name in OPTIONAL_TOOL_MODULES:
            missing = OPTIONAL_TOOL_MODULES[name]
            raise ModuleNotFoundError(
                f"No module named '{missing}'", name=missing
            )
        return real_import_module(name, package)

    monkeypatch.setattr(manifest_module.importlib, "import_module", recording_import)

    registry = ToolRegistry()

    assert len(registry._registry) >= 100
    assert not OPTIONAL_TOOL_MODULES.keys() & set(imported)
    assert registry.get_tool_availability("web_search") == {
        "name": "web_search",
        "available": None,
        "status": "not_checked",
    }


@pytest.mark.parametrize(
    ("action", "tool_module", "missing_dependency"),
    [
        ("web_search", "app.tools.web_research", "bs4"),
        ("analyze_data", "app.tools.data_analyzer", "pandas"),
        ("youtube_learn", "app.tools.youtube_learner", "youtube_transcript_api"),
        ("pdf_metadata", "app.tools.pdf_toolkit", "pypdf"),
        ("ocr_read", "app.tools.ocr_reader", "pytesseract"),
        ("screen_capture", "app.tools.screen_capture", "mss"),
    ],
)
def test_missing_dependency_disables_only_its_tool(
    monkeypatch, action, tool_module, missing_dependency
):
    real_import_module = importlib.import_module

    def unavailable_import(name, package=None):
        if name == tool_module:
            raise ModuleNotFoundError(
                f"No module named '{missing_dependency}'", name=missing_dependency
            )
        return real_import_module(name, package)

    monkeypatch.setattr(manifest_module.importlib, "import_module", unavailable_import)
    registry = ToolRegistry()

    availability = registry.get_tool_availability(action, probe=True)
    assert availability["available"] is False
    assert availability["status"] == "dependency_unavailable"
    assert availability["missing_dependency"] == missing_dependency

    result = registry.execute_registered_tool(action, {})
    assert result["success"] is False
    assert result["available"] is False
    assert result["error_type"] == "dependency_unavailable"
    assert result["missing_dependency"] == missing_dependency

    # An unrelated core capability remains registered and was not probed.
    assert registry.get_tool_availability("list_contacts")["status"] == "not_checked"


def test_cognitive_runtime_constructs_without_importing_optional_tools(monkeypatch, tmp_path):
    from app.cognition.runtime import CognitiveRuntime

    real_import_module = importlib.import_module
    imported = []

    def unavailable_import(name, package=None):
        imported.append(name)
        if name in OPTIONAL_TOOL_MODULES:
            missing = OPTIONAL_TOOL_MODULES[name]
            raise ModuleNotFoundError(
                f"No module named '{missing}'", name=missing
            )
        return real_import_module(name, package)

    monkeypatch.setattr(manifest_module.importlib, "import_module", unavailable_import)

    runtime = CognitiveRuntime(db_path=str(tmp_path / "runtime.db"))

    assert len(runtime.registry._registry) >= 100
    assert not OPTIONAL_TOOL_MODULES.keys() & set(imported)
