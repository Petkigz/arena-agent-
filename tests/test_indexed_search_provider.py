"""P0 review #11: an Everything-style indexed provider is the FAST PATH for
file search; the Python walker stays as the fallback.

all_user_files walks the home tree plus every fixed drive — correct, but
slow on a large machine. When Everything (voidtools) is available its
live NTFS index answers instantly.
"""

import os
from pathlib import Path
from unittest.mock import patch

from app.tools import indexed_search
from app.tools.universal_filesystem import UniversalFilesystem


def _make(root: Path, name: str, content: str = "x") -> Path:
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


def test_provider_hit_answers_without_walking(tmp_path):
    """A provider hit returns instantly — the walker is never invoked."""
    target = _make(tmp_path, "kaba_song.mp3")

    def fake_provider(query, roots, limit=20):
        return [{
            "file_name": "kaba_song.mp3",
            "file_path": str(target),
            "size_bytes": 1,
            "extension": ".mp3",
            "type": "file",
            "match": "exact",
            "source": "everything_http",
        }]

    with patch("app.tools.indexed_search.provider_search", side_effect=fake_provider):
        results = UniversalFilesystem.search_filesystem(
            "kaba", root_dir=tmp_path, max_results=10)
    assert len(results) == 1
    assert results[0]["file_path"] == str(target)
    assert results[0]["source"] == "everything_http"


def test_provider_none_falls_back_to_the_walker(tmp_path):
    _make(tmp_path, "ordinary.txt")
    with patch("app.tools.indexed_search.provider_search", return_value=None):
        results = UniversalFilesystem.search_filesystem(
            "ordinary", root_dir=tmp_path, max_results=10)
    assert len(results) == 1
    assert "source" not in results[0] or results[0].get("source") != "everything_http"


def test_provider_results_are_scoped_to_roots(tmp_path):
    """Searching ~/Music must not return a Windows file from another root:
    provider rows outside the requested roots are dropped."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    _make(outside, "kaba_leak.mp3")

    rows = [{"path": str(outside), "name": "kaba_leak.mp3"}]
    with patch.object(indexed_search, "_everything_cli_search", return_value=None), \
         patch.object(indexed_search, "_everything_http_search", return_value=rows):
        got = indexed_search.provider_search("kaba", [tmp_path / "music"], limit=10)
    assert got == []


def test_provider_results_keep_filename_substring_semantics(tmp_path):
    """search_files matches FILENAME substrings — Everything also matches
    directory names; a path-only match must not become a result."""
    row_path_only = {"path": str(tmp_path / "kaba_folder"), "name": "song.mp3"}
    with patch.object(indexed_search, "_everything_cli_search", return_value=None), \
         patch.object(indexed_search, "_everything_http_search",
                      return_value=[row_path_only]):
        got = indexed_search.provider_search("kaba", [tmp_path], limit=10)
    assert got == []


def test_provider_never_reports_stale_index_rows(tmp_path):
    """Existence-verified: a row for a file that no longer exists is
    dropped (the index can never fabricate presence)."""
    stale = tmp_path / "ghost_kaba.mp3"
    rows = [{"path": str(tmp_path), "name": "ghost_kaba.mp3"}]
    with patch.object(indexed_search, "_everything_cli_search", return_value=None), \
         patch.object(indexed_search, "_everything_http_search", return_value=rows):
        got = indexed_search.provider_search("ghost", [tmp_path], limit=10)
    assert got == []


def test_agent_install_directory_is_excluded(tmp_path, monkeypatch):
    """The agent's own tree is never a 'user file' result — even if the
    provider returns it."""
    from app.config import settings
    base = tmp_path / "arena-agent-"
    base.mkdir()
    monkeypatch.setattr(settings, "BASE_DIR", str(base))
    rows = [{"path": str(base), "name": "kaba_internal.py"}]
    (base / "kaba_internal.py").write_text("x")
    indexed_search._unavailable_until.clear()
    with patch.object(indexed_search, "_everything_cli_search", return_value=None), \
         patch.object(indexed_search, "_everything_http_search", return_value=rows):
        got = indexed_search.provider_search("kaba", [tmp_path], limit=10)
    assert got == []


def test_env_switch_disables_the_provider(tmp_path):
    _make(tmp_path, "kaba_direct.mp3")
    monkey = patch.dict(os.environ, {"ARENA_INDEXED_SEARCH": "0"})
    with monkey:
        got = indexed_search.provider_search("kaba", [tmp_path], limit=10)
    assert got is None


def test_everything_http_row_parsing():
    rows = [
        {"path": "C:\\Users\\me\\Music", "name": "kaba.mp3", "size": 10},
        {"path": "C:\\Users\\me\\Documents", "name": "kaba.txt", "size": 5},
    ]
    paths = indexed_search._parse_http_rows(rows)
    assert paths == ["C:\\Users\\me\\Music\\kaba.mp3",
                     "C:\\Users\\me\\Documents\\kaba.txt"]


def test_unavailable_http_provider_is_cached_not_reprobed():
    indexed_search._unavailable_until.clear()
    calls = {"n": 0}

    def failing_get(url, **kw):
        calls["n"] += 1
        raise ConnectionError("no Everything HTTP server")

    with patch.object(indexed_search.httpx, "get", side_effect=failing_get):
        assert indexed_search._everything_http_search("x", 5) is None
        assert indexed_search._everything_http_search("x", 5) is None
    assert calls["n"] == 1  # second call served from the unavailability cache
