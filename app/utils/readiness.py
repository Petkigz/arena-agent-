"""Startup readiness snapshot — Phase 0 of the owner's mind-platform plan
(2026-09-10): "the owner can see exactly what is running and why."

One honest block at startup (and ``GET /readiness``) answering:

  * is the provider reachable, and which models are ACTUALLY loaded;
  * configured vs. resolved model ids (a pinned id that is not loaded is
    a live 400/simulation waiting to happen — say so at startup, not at
    the first message);
  * which background jobs are enabled (parked rechecks, observer, screen
    watcher, dashboard auto-open, autonomy mode);
  * authority posture (autonomy mode, auth required, elevation);
  * capability inventory size;
  * OpenCV / browser device readiness (the owner's cv2 stub package made
    face detection silently unavailable — report it precisely).

Every probe is fail-open with a short timeout: a readiness check must
never delay or break startup. ``ARENA_READINESS=0`` skips the startup
log (the endpoint stays available).
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable, Dict, List, Optional

PROBE_TIMEOUT_S = 2.0


def probe_provider(base_url: str,
                   timeout: float = PROBE_TIMEOUT_S) -> Dict[str, Any]:
    """Provider reachability + the ACTUALLY loaded model ids.

    Native LM Studio ``/api/v0/models`` first (it reports real load
    state; the OpenAI-compatible ``/v1/models`` lists every downloaded
    model, loaded or not — the distinction that caused the 14B-over-9B
    JIT-load incident on 2026-09-08).
    """
    base = (base_url or "").rstrip("/")
    native = base[: -len("/v1")] if base.endswith("/v1") else base
    for url, native_api in ((f"{native}/api/v0/models", True),
                            (f"{base}/models", False)):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            entries = data.get("data") or []
            if native_api and entries and not any("state" in m for m in entries):
                continue  # a proxy mirroring /models without state: keep looking
            if native_api:
                loaded = sorted({
                    str(m.get("id")) for m in entries
                    if m.get("id") and str(m.get("state", "")).lower() == "loaded"
                })
            else:
                loaded = sorted({
                    str(m.get("id")) for m in entries if m.get("id")
                })
            return {"reachable": True, "endpoint": url, "loaded_models": loaded}
        except Exception:
            continue
    return {"reachable": False, "loaded_models": None,
            "error": f"no response from {base} within {timeout}s"}


def _probe_opencv() -> Dict[str, Any]:
    try:
        import cv2  # noqa: F401
    except Exception as exc:
        return {"importable": False, "cascade": False,
                "detail": f"import failed: {exc}"}
    cascade = hasattr(cv2, "CascadeClassifier")
    detail = ""
    if not cascade:
        version = str(getattr(cv2, "__version__", "") or "")
        if version.startswith("5"):
            # Owner Windows run 2026-09-11: opencv-python 5.0 imports fine
            # but Haar CascadeClassifier moved to opencv_contrib
            # (xobjdetect) in OpenCV 5 — this is NOT a broken install.
            detail = (f"OpenCV {version}: Haar CascadeClassifier moved to "
                      "opencv_contrib (xobjdetect) in OpenCV 5 — the "
                      "install is fine, face cascade is simply not in core. "
                      "Options: 'pip install \"opencv-python<5\"' for the "
                      "classic API, or run without face detection "
                      "(everything else works; all vision paths fail open).")
        else:
            # The owner's live machine had the PyPI stub 'cv2' shadowing the
            # real OpenCV: the import succeeds but the API is missing.
            detail = ("cv2 imports but lacks CascadeClassifier — wrong or "
                      "broken distribution. Uninstall every opencv-* "
                      "distribution from this interpreter and install "
                      "opencv-python.")
    return {"importable": True, "cascade": cascade,
            "version": getattr(cv2, "__version__", None), "detail": detail}


def _probe_browser() -> Dict[str, Any]:
    try:
        import webbrowser
        webbrowser.get()
        return {"available": True}
    except Exception as exc:
        return {"available": False, "detail": str(exc)[:120]}


def collect_readiness(probe_provider_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
                      ) -> Dict[str, Any]:
    """Assemble the full readiness snapshot. Never raises."""
    from app.config import settings

    probe = probe_provider_fn or probe_provider
    try:
        provider = probe(str(getattr(settings, "LM_STUDIO_URL", "")))
    except Exception as exc:
        provider = {"reachable": False, "loaded_models": None, "error": str(exc)[:120]}

    loaded: Optional[List[str]] = provider.get("loaded_models")

    def _pin_status(model_id: str) -> Dict[str, Any]:
        entry: Dict[str, Any] = {"configured": model_id}
        if model_id == "auto":
            entry["resolution"] = "best loaded model, chosen per request"
            return entry
        if loaded is None:
            entry["resolution"] = "unknown (provider unreachable)"
        elif model_id in loaded:
            entry["resolution"] = "loaded"
        else:
            entry["resolution"] = (
                "NOT loaded — requests fall back to the best loaded model "
                "(or simulate if none is)")
        return entry

    def _flag(name: str) -> str:
        return "enabled" if str(getattr(settings, name, "1")) != "0" else "disabled"

    try:
        from app.tools.manifest import get_tool_manifest
        tool_count: Optional[int] = len(get_tool_manifest())
    except Exception:
        tool_count = None

    snapshot: Dict[str, Any] = {
        "provider": provider,
        "models": {
            "main": _pin_status(str(getattr(settings, "MAIN_MODEL", ""))),
            "fast": _pin_status(str(getattr(settings, "FAST_MODEL", ""))),
            "code": _pin_status(str(getattr(settings, "CODE_MODEL", "auto"))),
        },
        "background_jobs": {
            "parked_goal_recheck": _flag("ARENA_PARKED_RECHECK"),
            "background_observer": _flag("ARENA_BACKGROUND_OBSERVER"),
            "screen_watcher": _flag("ARENA_SCREEN_WATCHER"),
            "dashboard_auto_open": _flag("ARENA_AUTO_OPEN_DASHBOARD"),
            "autonomy_mode": str(getattr(settings, "AUTONOMY_MODE", "off")),
        },
        "authority": {
            "autonomy_mode": str(getattr(settings, "AUTONOMY_MODE", "off")),
            "api_key_required": bool(os.environ.get("ARENA_API_KEY")),
            "elevated": _is_elevated(),
        },
        "capabilities": {"manifest_tools": tool_count},
        "opencv": _probe_opencv(),
        "browser": _probe_browser(),
    }
    return snapshot


def _is_elevated() -> bool:
    try:
        import ctypes
        import sys
        if sys.platform == "win32":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


def format_readiness(snapshot: Dict[str, Any]) -> str:
    """The owner-readable startup block."""
    lines = ["STARTUP READINESS", "=" * 60]
    prov = snapshot.get("provider") or {}
    if prov.get("reachable"):
        loaded = prov.get("loaded_models") or []
        lines.append(f"provider      : reachable ({prov.get('endpoint')})")
        lines.append(f"loaded models : {', '.join(loaded) if loaded else '(none)'}")
    else:
        lines.append(f"provider      : UNREACHABLE — {prov.get('error')}")
    for lane in ("main", "fast", "code"):
        m = (snapshot.get("models") or {}).get(lane) or {}
        lines.append(f"model {lane:<6}: {m.get('configured')} -> {m.get('resolution')}")
    jobs = snapshot.get("background_jobs") or {}
    lines.append("background    : " + ", ".join(
        f"{k}={v}" for k, v in jobs.items()))
    auth = snapshot.get("authority") or {}
    lines.append("authority     : mode={autonomy_mode}, api_key_required="
                 "{api_key_required}, elevated={elevated}".format(**{
                     k: auth.get(k) for k in
                     ("autonomy_mode", "api_key_required", "elevated")}))
    caps = snapshot.get("capabilities") or {}
    lines.append(f"capabilities  : {caps.get('manifest_tools')} manifest tools")
    cv = snapshot.get("opencv") or {}
    cv_line = f"opencv        : cascade={'ok' if cv.get('cascade') else 'UNAVAILABLE'}"
    if cv.get("detail"):
        cv_line += f" — {cv['detail']}"
    lines.append(cv_line)
    br = snapshot.get("browser") or {}
    lines.append(f"browser       : {'available' if br.get('available') else 'UNAVAILABLE'}")
    lines.append("=" * 60)
    return "\n".join(lines)
