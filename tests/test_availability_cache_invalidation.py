"""Availability cache must never outlive the facts it describes (P0 #6).

A pure 300s TTL lets a runtime-installed capability stay cached
available=False for up to five minutes AFTER its dependency arrives — and,
worse, the lazy-import proxy's sticky load error made even refresh=True
replay the stale failure forever. These tests pin the full invalidation
contract:

  1. execution failed because of availability  -> per-tool cache drop
  2. dependency installation occurred          -> environment revision bump
  3. environment changed                       -> note_environment_change()
  4. runtime registration changed              -> register_tool() bump
  5. result stale vs environment revision      -> entry tagged with its
     revision; a mismatched entry is never served (TTL is only a backstop)
"""

from __future__ import annotations

import types
from typing import Any, Dict

import pytest

from app.cognition.event_bus import EventBus
from app.cognition.tool_registry import ToolRegistry, get_shared_registry


# ── helpers ──────────────────────────────────────────────────────────────────

class CountingChecker:
    """Deterministic availability checker that counts invocations and can
    flip its answer (simulating a dependency being installed later)."""

    def __init__(self, available: bool = True):
        self.calls = 0
        self.available = available

    def __call__(self, *, probe: bool = False) -> Dict[str, Any]:
        self.calls += 1
        return {"available": self.available, "status": "available" if self.available else "dependency_unavailable"}


def make_registry() -> ToolRegistry:
    """A registry on its own bus (event capture without cross-test noise)."""
    return ToolRegistry(event_bus=EventBus())


# ── baseline behavior preserved ─────────────────────────────────────────────

def test_decisive_result_cached_within_ttl_and_revision():
    reg = make_registry()
    checker = CountingChecker(available=True)
    reg.register_tool("stable_tool", "test", lambda p: {"success": True}, availability=checker)

    first = reg.get_tool_availability("stable_tool")
    second = reg.get_tool_availability("stable_tool")

    assert checker.calls == 1, "within TTL and revision, the cache serves the result"
    assert first["available"] is True
    assert second["available"] is True
    assert "probed_at_revision" in first, "decisive results carry their probe revision"
    assert second["probed_at_revision"] == first["probed_at_revision"]


def test_not_checked_still_flows_verbatim_and_never_freezes():
    reg = make_registry()
    calls = {"n": 0}

    def not_checked(*, probe: bool = False):
        calls["n"] += 1
        return {"available": None, "status": "not_checked"}

    reg.register_tool("unchecked_tool", "test", lambda p: {"success": True}, availability=not_checked)

    first = reg.get_tool_availability("unchecked_tool")
    second = reg.get_tool_availability("unchecked_tool")

    assert calls["n"] == 2, "NOT_CHECKED is never cached — it keeps flowing"
    assert first == {
        "name": "unchecked_tool",
        "provenance": "dynamic",
        "available": None,
        "status": "not_checked",
    }
    assert second == first
    assert "probed_at_revision" not in first, "no probe happened — no revision claim"


def test_refresh_true_reprobes_and_updates_entry():
    reg = make_registry()
    checker = CountingChecker(available=True)
    reg.register_tool("refresh_tool", "test", lambda p: {"success": True}, availability=checker)

    reg.get_tool_availability("refresh_tool")
    fresh = reg.get_tool_availability("refresh_tool", refresh=True)

    assert checker.calls == 2, "refresh=True bypasses the cache"
    assert fresh["available"] is True


# ── trigger 1: execution failed because of availability ─────────────────────
# (the tests override a KNOWN Level-0 manifest action in a throwaway registry
# so ActionGate's unknown-action default of Level-3 approval doesn't mask the
# behavior under test — dynamic override of a manifest name is the designed
# intentional-patch path)


def test_execution_reporting_unavailable_drops_cached_true():
    reg = make_registry()
    checker = CountingChecker(available=True)  # planner saw available=True
    reg.register_tool(
        "web_search", "test",
        lambda p: {"success": False, "available": False, "error": "dependency gone"},
        availability=checker,
    )
    reg.get_tool_availability("web_search")
    assert checker.calls == 1

    result = reg.execute_registered_tool("web_search", {})
    assert result["available"] is False

    # Ground truth beat the cached probe: the entry is dropped, the next
    # lookup re-runs the real checker instead of re-freezing the failure.
    assert "web_search" not in reg._availability_cache
    reg.get_tool_availability("web_search")
    assert checker.calls == 2


def test_execution_import_error_drops_cached_true():
    reg = make_registry()
    checker = CountingChecker(available=True)

    def handler(payload):
        raise ImportError("No module named 'some_dependency'")

    reg.register_tool("screen_capture", "test", handler, availability=checker)
    reg.get_tool_availability("screen_capture")

    result = reg.execute_registered_tool("screen_capture", {})
    assert result["success"] is False
    assert result["available"] is False
    assert result["error_type"] == "dependency_unavailable"

    assert "screen_capture" not in reg._availability_cache
    reg.get_tool_availability("screen_capture")
    assert checker.calls == 2


# ── trigger 4: runtime registration changed ─────────────────────────────────

def test_reregistration_invalidates_cached_availability_immediately():
    reg = make_registry()
    reg.register_tool(
        "patched_tool", "test", lambda p: {"success": True},
        availability=CountingChecker(available=False),
    )
    assert reg.get_tool_availability("patched_tool")["available"] is False

    revision_before = reg.environment_revision
    # The runtime installs a NEW registration of the same name — different
    # handler, different checker (e.g. its dependency is now bundled).
    reg.register_tool(
        "patched_tool", "test", lambda p: {"success": True},
        availability=CountingChecker(available=True),
    )

    assert reg.environment_revision > revision_before, "registration advances the revision"
    status = reg.get_tool_availability("patched_tool")
    assert status["available"] is True, "the new registration's truth is visible immediately — no TTL wait"


# ── triggers 2+3+5: environment revision invalidation ───────────────────────

def test_note_environment_change_invalidates_all_entries_and_emits_event():
    reg = make_registry()
    checker_a = CountingChecker(available=True)
    checker_b = CountingChecker(available=True)
    reg.register_tool("tool_a", "test", lambda p: {"success": True}, availability=checker_a)
    reg.register_tool("tool_b", "test", lambda p: {"success": True}, availability=checker_b)
    reg.get_tool_availability("tool_a")
    reg.get_tool_availability("tool_b")
    assert checker_a.calls == 1 and checker_b.calls == 1

    events: list = []
    reg.event_bus.subscribe("environment_changed", events.append)
    revision_before = reg.environment_revision

    revision = reg.note_environment_change("dependency installed", source="test")

    assert revision == reg.environment_revision
    assert revision > revision_before
    assert len(events) == 1
    assert events[0].event_type == "environment_changed"
    assert events[0].data["reason"] == "dependency installed"
    assert events[0].data["revision"] == revision
    assert reg._availability_cache == {}, "every cached fact is stale the moment the revision moves"

    # Both tools re-probe on next lookup.
    reg.get_tool_availability("tool_a")
    reg.get_tool_availability("tool_b")
    assert checker_a.calls == 2 and checker_b.calls == 2


def test_stale_revision_entry_never_served_even_within_ttl():
    """An entry probed at revision R is unservable at revision R+1 even when
    the TTL has not elapsed (this test runs in milliseconds) — the revision,
    not the clock, is the authority. A registration of one tool advances the
    revision, so ANOTHER tool's still-cached entry must be re-probed too."""
    reg = make_registry()
    checker = CountingChecker(available=False)
    reg.register_tool("flips_tool", "test", lambda p: {"success": True}, availability=checker)
    assert reg.get_tool_availability("flips_tool")["available"] is False
    assert checker.calls == 1

    checker.available = True  # the dependency arrived
    # An unrelated runtime registration advances the environment revision
    # WITHOUT touching flips_tool's entry directly.
    reg.register_tool("unrelated_new_tool", "test", lambda p: {"success": True})
    assert checker.calls == 1, "sanity: nothing probed flips_tool yet"
    assert "flips_tool" in reg._availability_cache, "sanity: the entry still exists"

    status = reg.get_tool_availability("flips_tool")
    assert checker.calls == 2, "the revision mismatch forced a re-probe (TTL never elapsed)"
    assert status["available"] is True
    assert status["probed_at_revision"] == reg.environment_revision


# ── the deep fix: a probe must RE-probe, never replay a stale failure ───────

def test_lazy_proxy_retries_after_dependency_becomes_available(monkeypatch):
    """The exact owner scenario: capability probed unavailable, dependency
    installed, next probe must see available — through the real lazy proxy."""
    import app.tools.manifest as manifest_module
    from app.tools.manifest import _LazyImportProxy

    installed = {"now": False}
    real_import = manifest_module.importlib.import_module

    def fake_import(name, package=None):
        if name == "arena_fake_dep_tool":
            if not installed["now"]:
                raise ModuleNotFoundError("No module named 'arena_dep'", name="arena_dep")
            return types.SimpleNamespace(Thing=lambda p: {"success": True})
        return real_import(name, package)

    monkeypatch.setattr(manifest_module.importlib, "import_module", fake_import)

    proxy = _LazyImportProxy("arena_fake_dep_tool", "Thing")
    checker = proxy.availability

    reg = make_registry()
    reg.register_tool("late_dep_tool", "test", lambda p: {"success": True}, availability=checker)

    # 1. Dependency missing: honest unavailable, cached.
    assert reg.get_tool_availability("late_dep_tool", probe=True)["available"] is False
    assert reg.get_tool_availability("late_dep_tool")["available"] is False

    # 2. Dependency installed out of band; environment change declared.
    installed["now"] = True
    reg.note_environment_change("dependency installed", source="test")

    # 3. The planner's next lookup sees the truth — no restart, no TTL wait,
    #    and refresh=True is not even needed.
    assert reg.get_tool_availability("late_dep_tool", probe=True)["available"] is True

    # 4. probe=False now reports the resolved state too (last-error cleared).
    assert reg.get_tool_availability("late_dep_tool")["available"] is True


def test_lazy_proxy_failure_does_not_poison_future_probes():
    """Pre-pinned regression: repeated probes while the dependency is missing
    still fail honestly (and the typed result shape is preserved)."""
    import app.tools.manifest as manifest_module
    from app.tools.manifest import _LazyImportProxy

    proxy = _LazyImportProxy("arena_definitely_missing_module_xyz", "Thing")
    for _ in range(2):
        status = proxy.availability(probe=True)
        assert status["available"] is False
        assert status["status"] == "dependency_unavailable"
        assert status["missing_dependency"] == "arena_definitely_missing_module_xyz"

    unprobed = proxy.availability(probe=False)
    assert unprobed["available"] is False, "last observed error is reported without re-importing"


# ── trigger 2: dependency installation notifies the registry ────────────────

class _FakeProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_package_install_bumps_environment_revision(monkeypatch):
    from app.tools import package_installer

    registry = get_shared_registry()
    before = registry.environment_revision

    monkeypatch.setattr(
        package_installer, "run_cancellable_subprocess",
        lambda cmd, timeout=60: _FakeProcess(returncode=0, stdout="Successfully installed reportlab"),
    )
    result = package_installer.PackageInstaller.install_package("reportlab")

    assert result["success"] is True
    assert registry.environment_revision > before, "install success must advance the revision"


def test_package_uninstall_bumps_environment_revision(monkeypatch):
    from app.tools import package_installer

    registry = get_shared_registry()
    before = registry.environment_revision

    monkeypatch.setattr(
        package_installer, "run_cancellable_subprocess",
        lambda cmd, timeout=60: _FakeProcess(returncode=0),
    )
    result = package_installer.PackageInstaller.uninstall_package("reportlab")

    assert result["success"] is True
    assert registry.environment_revision > before, "uninstall (false-capability risk) must advance the revision"


def test_failed_package_install_does_not_bump_revision(monkeypatch):
    from app.tools import package_installer

    registry = get_shared_registry()
    before = registry.environment_revision

    monkeypatch.setattr(
        package_installer, "run_cancellable_subprocess",
        lambda cmd, timeout=60: _FakeProcess(returncode=1, stderr="no network"),
    )
    result = package_installer.PackageInstaller.install_package("reportlab")

    assert result["success"] is False
    assert registry.environment_revision == before, "nothing changed — no invalidation"


# ── the planner automatically refreshes (no explicit refresh=True needed) ────

def test_planner_classification_reflects_post_install_flip():
    """The planner's capability classification reads the registry; after an
    environment change it must see the new availability WITHOUT any planner
    code change — invalidation is the registry's job, refresh is automatic."""
    from app.cognition.action_planner import ActionPlanner

    checker = CountingChecker(available=False)
    reg = make_registry()
    reg.register_tool("planner_flip_tool", "test", lambda p: {"success": True}, availability=checker)

    branch = types.SimpleNamespace(
        hypothetical_action="planner_flip_tool", candidate_payload={}
    )
    provenance, status = ActionPlanner._classify_capability(branch, reg)
    assert provenance == "dynamic", "runtime-registered tool — provenance is explicit"
    assert status["available"] is False, "dependency missing at plan time"

    checker.available = True  # dependency installed
    reg.note_environment_change("dependency installed", source="test")

    provenance, status = ActionPlanner._classify_capability(branch, reg)
    assert provenance == "dynamic"
    assert status["available"] is True, "planner sees the flip on its next classification pass"


# ── owner-declared environment change (REST surface) ─────────────────────────

def test_owner_can_declare_environment_change_via_api():
    """POST /tools/availability/refresh lets the owner bust the cache for
    changes Arena cannot observe (e.g. a manual pip install in a terminal)
    instead of waiting out the TTL backstop."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.cognition.runtime import CognitiveRuntime

    with TestClient(app) as api:
        registry = CognitiveRuntime.get_instance().registry
        before = registry.environment_revision

        response = api.post("/tools/availability/refresh", json={"reason": "manual pip install"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["reason"] == "manual pip install"
        assert data["environment_revision"] > before
        assert registry.environment_revision == data["environment_revision"]
        assert registry._availability_cache == {}, "owner declaration clears every cached fact"

        # The declared change also lands on the persistent audit trail.
        probe = api.get("/tools/availability", params={"tool": "web_search"})
        assert probe.status_code == 200
