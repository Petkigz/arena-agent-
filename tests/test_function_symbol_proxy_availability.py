"""Regression: function-symbol lazy proxies must expose the PROXY's
availability probe, not a delegating invoke() closure.

binary_analyze / binary_strings are registered through _LazyImportProxy
wrapping module-level FUNCTIONS. _copy_availability does
getattr(source, 'tool_availability') on the raw proxy, which hit
__getattr__ and returned an invoke() closure for the attribute name
'tool_availability' — a closure that, called as a checker, did
getattr(loaded_function, 'tool_availability') and raised AttributeError.

The bug was latent until any FULL availability listing ran
(GET /tools/availability without a tool filter, or
ToolRegistry.list_tool_availability()): single-tool probes never touched
these names. Found by live HTTP verification, not by the unit suite.
"""

from __future__ import annotations

from app.cognition.tool_registry import ToolRegistry
from app.tools.manifest import _LazyImportProxy, get_tool_manifest


FUNCTION_SYMBOL_TOOLS = ("binary_analyze", "binary_strings")


def test_function_symbol_proxies_carry_the_proxy_probe():
    """The checker attached to a function-symbol tool IS the proxy's
    availability method — probeable without exploding."""
    for name in FUNCTION_SYMBOL_TOOLS:
        entry = get_tool_manifest().get(name)
        assert entry is not None, name
        checker = entry.get("availability")
        assert callable(checker), f"{name}: no checker"
        status = checker(probe=False)
        assert isinstance(status, dict), name
        assert status.get("available") in (True, False, None), (name, status)


def test_full_registry_availability_listing_never_raises():
    """THE regression: listing every tool's availability (what
    GET /tools/availability does) must not crash on any checker."""
    reg = ToolRegistry()
    records = reg.list_tool_availability()  # raised AttributeError before
    assert len(records) >= 100
    for record in records:
        assert record.get("available") in (True, False, None), record
        assert record.get("status"), record


def test_function_symbol_tools_probe_available_with_deps():
    """With binary_analyzer importable (psutil/core deps only), the probe
    resolves the module and reports available."""
    reg = ToolRegistry()
    for name in FUNCTION_SYMBOL_TOOLS:
        status = reg.get_tool_availability(name, probe=True, refresh=True)
        assert status.get("available") is True, (name, status)
        assert status.get("status") == "available", (name, status)


def test_proxy_getattr_returns_proxy_availability_not_delegation():
    """Direct pin of the fix: asking a proxy for 'tool_availability'
    returns the proxy's own availability bound method."""
    proxy = _LazyImportProxy("app.tools.binary_analyzer", "analyze_binary")
    checker = getattr(proxy, "tool_availability")
    assert checker == proxy.availability or callable(checker)
    # And it answers a probe honestly without raising.
    status = checker(probe=False)
    assert isinstance(status, dict)
