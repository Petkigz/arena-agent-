"""
Tests for the two expansion levers: the generic local executor and the plugin
registry.
"""

import json
from pathlib import Path

from app.tools.local_executor import LocalExecutor
from app.tools.plugin_registry import PluginRegistry


# ── local executor ──────────────────────────────────────────────────────────
def test_executor_rejects_bad_action():
    assert LocalExecutor.execute(action="explode")["success"] is False


def test_executor_shell_requires_command():
    assert LocalExecutor.execute(action="shell")["success"] is False


def test_executor_http_requires_url():
    assert LocalExecutor.execute(action="http")["success"] is False


def test_executor_http_blocks_external_urls():
    res = LocalExecutor.execute(action="http", url="https://evil.com")
    assert res["success"] is False
    assert "localhost" in res["error"]


def test_executor_python_requires_code():
    assert LocalExecutor.execute(action="python")["success"] is False


# ── plugin registry ─────────────────────────────────────────────────────────
def test_plugin_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(PluginRegistry, "PLUGIN_DIR", tmp_path)

    plugin = tmp_path / "hello.py"
    plugin.write_text(
        'NAME = "say_hello"\n'
        'DESCRIPTION = "Says hello"\n'
        'SAFETY_LEVEL = 0\n'
        'CATEGORY = "plugin"\n'
        "def execute(payload):\n"
        "    name = payload.get('name', 'world')\n"
        "    return {'success': True, 'message': f'hello {name}'}\n"
    )

    plugins = PluginRegistry.discover_plugins()
    assert "say_hello" in plugins
    entry = plugins["say_hello"]
    assert entry["safety_level"] == 0
    assert entry["handler"]({"name": "beanie"})["message"] == "hello beanie"


def test_plugin_skips_malformed(tmp_path, monkeypatch):
    monkeypatch.setattr(PluginRegistry, "PLUGIN_DIR", tmp_path)

    # Missing NAME.
    (tmp_path / "bad1.py").write_text("def execute(p): return {}\n")
    # Missing execute.
    (tmp_path / "bad2.py").write_text('NAME = "nope"\n')
    # Syntax error.
    (tmp_path / "bad3.py").write_text("this is not valid python !!!\n")

    plugins = PluginRegistry.discover_plugins()
    assert plugins == {}  # all malformed plugins skipped, no crash


def test_plugin_manifests_merge_into_manifest(tmp_path, monkeypatch):
    """A plugin dropped into the dir shows up in the unified manifest."""
    monkeypatch.setattr(PluginRegistry, "PLUGIN_DIR", tmp_path)
    (tmp_path / "greet.py").write_text(
        'NAME = "greet"\nSAFETY_LEVEL = 0\n'
        "def execute(p): return {'success': True}\n"
    )

    # Reset the manifest cache so it re-discovers plugins, then restore it after.
    import app.tools.manifest as mf
    saved = mf._TOOL_MANIFEST
    mf._TOOL_MANIFEST = None
    try:
        manifest = mf.get_tool_manifest()
        assert "greet" in manifest
    finally:
        mf._TOOL_MANIFEST = saved
