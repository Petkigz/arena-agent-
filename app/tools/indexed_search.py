"""Indexed filesystem search providers (P0 review #11).

The all_user_files scope walks the home tree plus every fixed drive —
correct, but a Python walker over several NTFS drives is seconds-to-minutes
on a large machine. Everything (voidtools) reads the NTFS master file
table and answers filename queries over EVERY drive instantly; Windows
Search plays the same role via its index.

This module is the FAST PATH with the walker as fallback:

    search_filesystem query
        -> indexed provider available?  (Everything HTTP / Everything CLI)
            yes -> instant results, existence-verified, scoped to roots
            no  -> the existing walker (index cache + live walk, unchanged)

Provider contract (provider_search):
  * returns None       -> no provider available/healthy; fall back entirely
  * returns []         -> the live index answered authoritatively: NO file
                          name contains the query (the caller may still run
                          its typo-tolerant fuzzy pass)
  * returns entries    -> walker-equivalent entries: filename substring
                          matches only, existence-verified, inside the
                          requested roots, never inside the agent's own
                          install directory

Every provider result is tagged with its source, so a result never lies
about how it was found.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time as _time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger

import httpx

# Everything's HTTP server plugin (Tools -> HTTP server in Everything).
_DEFAULT_EVERYTHING_URL = "http://localhost:21434"
_PROVIDER_TIMEOUT_S = 2.0
# Remember "unavailable" briefly so a dead port is not re-probed on every
# search; an available provider is re-checked per query anyway.
_UNAVAILABLE_CACHE_S = 300.0

_unavailable_until: Dict[str, float] = {}


def _env_url() -> str:
    import os as _os

    return _os.environ.get("ARENA_EVERYTHING_URL", _DEFAULT_EVERYTHING_URL).rstrip("/")


def _norm_path(path: str) -> str:
    return str(path or "").replace("\\", "/").rstrip("/").lower()


def _inside_roots(file_path: str, roots: List[Path]) -> bool:
    p = _norm_path(file_path)
    if not p:
        return False
    for root in roots:
        r = _norm_path(str(root))
        if r and (p == r or p.startswith(r + "/")):
            return True
    return False


def _excluded(file_path: str) -> bool:
    """The agent's own install tree is never a 'user file' result."""
    base = _norm_path(str(getattr(settings, "BASE_DIR", "") or ""))
    return bool(base) and _norm_path(file_path).startswith(base + "/")


# ---------------------------------------------------------------------------
# Everything HTTP server
# ---------------------------------------------------------------------------

def _everything_http_search(query: str, limit: int) -> Optional[List[Dict[str, Any]]]:
    base = _env_url()
    if _time.monotonic() < _unavailable_until.get(f"http:{base}", 0):
        return None
    try:
        response = httpx.get(
            f"{base}/search",
            params={
                "search": query,
                "json": 1,
                "count": max(1, min(int(limit), 500)),
                "path_column": 1,
                "size_column": 1,
                "date_modified_column": 1,
            },
            timeout=_PROVIDER_TIMEOUT_S,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            return None
        return data
    except Exception as exc:
        _unavailable_until[f"http:{base}"] = _time.monotonic() + _UNAVAILABLE_CACHE_S
        app_logger.info(
            f"Everything HTTP provider unavailable ({exc}); file search uses the walker.")
        return None


def _parse_http_rows(rows: List[Dict[str, Any]]) -> List[str]:
    """Everything HTTP JSON rows -> full file paths ('path'+'name' or a
    complete path field), defensively parsed."""
    paths: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        path = str(row.get("path") or "").strip()
        if name and path:
            # Keep the provider's separator style (Windows rows stay
            # backslash-joined even when parsed on another OS).
            sep = "\\" if "\\" in path else "/"
            paths.append(path.rstrip("\\/") + sep + name)
        elif name or path:
            # Some configurations return the full path in 'name'.
            paths.append(path or name)
    return paths


# ---------------------------------------------------------------------------
# Everything CLI (es.exe)
# ---------------------------------------------------------------------------

def _es_exe_path() -> Optional[str]:
    return shutil.which("es.exe")


def _everything_cli_search(query: str, limit: int) -> Optional[List[str]]:
    exe = _es_exe_path()
    if exe is None:
        return None
    key = f"cli:{exe}"
    if _time.monotonic() < _unavailable_until.get(key, 0):
        return None
    try:
        completed = subprocess.run(
            [exe, "-n", str(max(1, min(int(limit), 500))), "--", query],
            capture_output=True, text=True, timeout=_PROVIDER_TIMEOUT_S,
        )
        if completed.returncode != 0:
            _unavailable_until[key] = _time.monotonic() + _UNAVAILABLE_CACHE_S
            return None
        return [line.strip() for line in (completed.stdout or "").splitlines()
                if line.strip()]
    except Exception as exc:
        _unavailable_until[key] = _time.monotonic() + _UNAVAILABLE_CACHE_S
        app_logger.info(
            f"Everything CLI provider unavailable ({exc}); file search uses the walker.")
        return None


# ---------------------------------------------------------------------------
# The provider entry point
# ---------------------------------------------------------------------------

def provider_available() -> bool:
    """Is any indexed provider present on this machine?"""
    if os.environ.get("ARENA_INDEXED_SEARCH") == "0":
        return False
    if _es_exe_path() is not None:
        return True
    base = _env_url()
    if _time.monotonic() < _unavailable_until.get(f"http:{base}", 0):
        return False
    try:
        response = httpx.get(f"{base}/search",
                             params={"search": "arena_health_probe", "json": 1, "count": 1},
                             timeout=_PROVIDER_TIMEOUT_S)
        return response.status_code == 200
    except Exception:
        return False


def provider_search(
    query: str,
    roots: List[Path],
    limit: int = 20,
) -> Optional[List[Dict[str, Any]]]:
    """Fast indexed search. See module docstring for the contract.

    Results are walker-equivalent: filename substring matches only,
    existence-verified, inside the requested roots, tagged with source.
    """
    if os.environ.get("ARENA_INDEXED_SEARCH") == "0":
        return None
    query_raw = (query or "").strip()
    if not query_raw:
        return None
    limit = max(1, int(limit))

    raw_paths: Optional[List[str]] = None
    source = ""
    rows = _everything_http_search(query_raw, limit * 2)
    if rows is not None:
        raw_paths = _parse_http_rows(rows)
        source = "everything_http"
    if raw_paths is None or not raw_paths:
        cli_paths = _everything_cli_search(query_raw, limit * 2)
        if cli_paths is not None:
            raw_paths = cli_paths
            source = "everything_cli"
    if raw_paths is None:
        return None

    entries: List[Dict[str, Any]] = []
    query_lower = query_raw.lower()
    for file_path in raw_paths:
        if _excluded(file_path) or not _inside_roots(file_path, roots):
            continue
        name = os.path.basename(file_path.replace("\\", "/"))
        # Walker-equivalent semantics: FILENAME substring match only —
        # Everything also matches directory names; those are not what
        # search_files promises.
        if query_lower not in name.lower():
            continue
        if not os.path.exists(file_path):
            continue  # never report stale index rows
        try:
            is_dir = os.path.isdir(file_path)
            size = 0 if is_dir else os.path.getsize(file_path)
        except OSError:
            continue
        entries.append({
            "file_name": name,
            "file_path": str(file_path),
            "size_bytes": size,
            "extension": "" if is_dir else Path(name).suffix.lower(),
            "type": "directory" if is_dir else "file",
            "match": "exact",
            "source": source,
        })
        if len(entries) >= limit:
            break
    if entries:
        app_logger.info(
            f"Indexed search fast path ({source}): {len(entries)} match(es) for "
            f"'{query_raw}' — no filesystem walk needed.")
    return entries
