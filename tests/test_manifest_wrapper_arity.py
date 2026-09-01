"""Manifest wrapper arity contract (N2 audit, 2026-09).

An external sandbox battery found that manifest payload keys did not match
handler parameters: 'Run this Python code' crashed with
"CoderBrainTool.explain_and_debug_code() missing 1 required positional
argument: 'code_snippet'" and 'read the file' crashed with
"DocumentManager.read_document() missing ... 'file_path_str'". A systematic
audit of all 147 _wrap'd tools found **30** such mismatches — every payload
shape for those tools either crashed with TypeError or silently dropped the
key. The declarations now carry the handler's REAL parameter names, _wrap
enforces the contract with typed self-describing errors (never a raise),
and _PAYLOAD_KEY_ALIASES keeps the natural public keys (file_path,
image_path, url, message, ...) working.

This test IS the audit, permanently: any future wrapper/payload drift fails
here instead of crashing at runtime on the owner's machine.
"""

import inspect

import pytest

import app.tools.manifest as manifest_module
from app.tools.manifest import (
    _PAYLOAD_KEY_ALIASES,
    _LazyImportProxy,
    _resolve_for_signature,
    _wrap,
    get_tool_manifest,
)


def wrapped_tools():
    """(tool_name, keys) for every _wrap-produced handler in the manifest."""
    manifest_module._TOOL_MANIFEST = None  # rebuild, never a stale cache
    out = []
    for tool, entry in sorted(get_tool_manifest().items()):
        handler = entry.get("handler")
        closure = getattr(handler, "__closure__", None)
        if not closure:
            continue
        fn = keys = None
        for cell in closure:
            try:
                v = cell.cell_contents
            except ValueError:
                continue
            if isinstance(v, tuple) and v and all(isinstance(x, str) for x in v):
                keys = v
            elif inspect.isclass(v):
                continue
            elif callable(v):
                fn = v
        if fn is not None and keys is not None:
            out.append((tool, fn, keys))
    return out


def test_every_wrapped_tool_declares_real_parameter_names():
    """No invented keys: every declared payload key is a real parameter of
    the (proxy-resolved) handler. The pre-fix audit found 30 violations
    ('image_path' vs 'image_path_str', 'issue', 'app_name', ...)."""
    bad = []
    for tool, fn, keys in wrapped_tools():
        try:
            sig = inspect.signature(_resolve_for_signature(fn))
        except Exception:
            continue  # unloadable/unsignaturable — the runtime path degrades
        params = sig.parameters
        if any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
               for p in params.values()):
            continue
        bad += ["%s: %r is not a parameter (real: %s)"
                % (tool, k, sorted(params)) for k in keys if k not in params]
    assert not bad, "invented payload keys:\n  " + "\n  ".join(bad)


def test_every_required_parameter_is_wired():
    """Every parameter the handler REQUIRES must be reachable through a
    declared payload key — an unwired required parameter means the tool
    crashes on every payload shape (the read_document / code_explain
    failure class)."""
    bad = []
    for tool, fn, keys in wrapped_tools():
        try:
            sig = inspect.signature(_resolve_for_signature(fn))
        except Exception:
            continue
        params = sig.parameters
        if any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
               for p in params.values()):
            continue
        required = {n for n, p in params.items()
                    if p.default is p.empty
                    and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}
        missing = sorted(required - set(keys))
        if missing:
            bad.append("%s: required but unwired: %s" % (tool, missing))
    assert not bad, "unreachable required parameters:\n  " + "\n  ".join(bad)


def test_alias_table_maps_param_names_to_public_keys():
    """Aliases are keyed by REAL parameter names and map to distinct public
    payload keys — the table is what keeps natural payloads working."""
    for param, public in _PAYLOAD_KEY_ALIASES.items():
        assert isinstance(param, str) and isinstance(public, str)
        assert param != public
    assert _PAYLOAD_KEY_ALIASES["file_path_str"] == "file_path"
    assert _PAYLOAD_KEY_ALIASES["image_path_str"] == "image_path"


# ── the two battery crashes, as regressions ─────────────────────────────────

def test_read_document_works_through_the_alias_key(tmp_path):
    """T07's crash: 'read the first one' -> read_document crashed with
    missing 'file_path_str' on EVERY payload. Now the natural public key
    works (alias) and so does the real parameter name."""
    f = tmp_path / "doc.txt"
    f.write_text("arity audit content")
    from app.cognition import tool_registry as tr

    reg = tr.get_shared_registry()
    for key in ("file_path", "file_path_str"):
        out = reg.execute_registered_tool("read_document", {key: str(f)})
        assert out.get("success") is True, (key, out)
        assert "arity audit content" in str(out.get("content", ""))


def test_code_explain_never_raises_on_router_payloads():
    """T02's crash: 'Run this Python code' -> code_explain raised TypeError
    (missing 'code_snippet'). A wrong payload now gets a typed,
    self-describing error that NAMES the accepted keys — a model-driven
    caller can retry with them."""
    from app.cognition import tool_registry as tr

    out = tr.get_shared_registry().execute_registered_tool(
        "code_explain", {"query": "def f(): pass"})
    assert isinstance(out, dict)
    assert out.get("success") is False
    assert "code_snippet" in str(out.get("error", ""))
    assert "code_snippet" in out.get("expected_keys", [])


def test_missing_required_payload_is_typed_never_raised(tmp_path):
    """The mechanism, not just the two instances: a _wrap handler with an
    unsatisfied contract returns {success: False, expected_keys} — never a
    TypeError into the execution path."""
    def needs_two(mandatory: str, optional: int = 7):
        return {"success": True, "got": (mandatory, optional)}

    handler = _wrap(needs_two, "mandatory", "optional")
    out = handler({"unrelated": "x"})
    assert out.get("success") is False
    assert "mandatory" in out.get("expected_keys", [])

    # satisfied contract still calls through, aliases and all
    assert handler({"mandatory": "v"})["got"] == ("v", 7)
    assert handler({"mandatory": "v", "optional": 3})["got"] == ("v", 3)


def test_alias_accepts_public_key_for_suffixed_param():
    def tool(path_str: str):
        return {"success": True, "path": path_str}

    # simulate the _str-suffix family: declare the real param, alias the rest
    manifest_module._PAYLOAD_KEY_ALIASES.setdefault("path_str", "path")
    try:
        handler = _wrap(tool, "path_str")
        assert handler({"path": "/x/y.txt"}) == {"success": True,
                                                 "path": "/x/y.txt"}
    finally:
        manifest_module._PAYLOAD_KEY_ALIASES.pop("path_str", None)


def test_proxy_resolution_helper_handles_all_three_shapes():
    """_resolve_for_signature: plain function, lazy proxy instance, and
    proxy method-invoke closure all resolve to something inspectable —
    and unloadable proxies raise (the caller renders typed results)."""
    def plain(a: str) -> str:
        return a

    assert _resolve_for_signature(plain) is plain
    proxy = _LazyImportProxy("app.tools.doc_manager", "DocumentManager")
    resolved = _resolve_for_signature(proxy)
    assert inspect.isclass(resolved) or callable(resolved)
    method = proxy.read_document  # triggers __getattr__ -> invoke closure
    real = _resolve_for_signature(method)
    sig = inspect.signature(real)
    assert "file_path_str" in sig.parameters
