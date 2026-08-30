"""P0 bottleneck #12: filesystem search defaults to the USER'S files, not
Arena's own install directory. Explicit scopes (workspace/home/desktop/
documents/downloads/music/pictures/videos/all_user_files), smallest-sensible
inference from the query, and narrow-scope escalation that never fabricates
absence."""
from pathlib import Path

import pytest

from app.config import settings
from app.tools.universal_filesystem import UniversalFilesystem


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    (tmp_path / "Music").mkdir()
    (tmp_path / "Documents").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def test_default_scope_is_all_user_files_not_the_agent_dir(fake_home):
    (fake_home / "Music" / "Kaba.mp3").write_text("x")
    hits = UniversalFilesystem.search_filesystem("Kaba")
    assert hits and hits[0]["file_name"] == "Kaba.mp3"
    assert hits[0]["scope"] == "all_user_files"
    # The old default searched settings.BASE_DIR (the agent's install dir).
    assert str(settings.BASE_DIR) not in str(hits[0]["file_path"])


def test_scope_inference_picks_the_smallest_sensible_scope():
    cases = [
        ("find my song called kaba", "music"),
        ("where is the contract.pdf document", "documents"),
        ("the downloaded installer", "downloads"),
        ("vacation photo from the camera", "pictures"),
        ("that movie clip", "videos"),
        ("clean up my desktop", "desktop"),
        ("something in your workspace", "workspace"),
        ("kaba", "all_user_files"),
    ]
    for query, expected in cases:
        assert UniversalFilesystem.infer_scope_from_query(query) == expected, query


def test_explicit_scope_searches_only_that_folder(fake_home):
    (fake_home / "Music" / "Kaba.mp3").write_text("x")
    (fake_home / "Documents" / "Kaba.txt").write_text("x")
    hits = UniversalFilesystem.search_filesystem("Kaba", scope="music")
    assert [h["file_name"] for h in hits] == ["Kaba.mp3"]
    assert hits[0]["scope"] == "music"


def test_narrow_scope_escalates_instead_of_fabricating_absence(fake_home):
    """A miss in ~/Music is not proof the file doesn't exist elsewhere."""
    (fake_home / "Documents" / "Kaba.txt").write_text("x")   # NOT in Music
    hits = UniversalFilesystem.search_filesystem("Kaba", scope="music")
    assert hits, "music-scope miss must escalate, not report nothing"
    assert hits[0]["file_name"] == "Kaba.txt"
    assert hits[0]["scope_escalated"] is True


def test_explicit_root_dir_still_wins(tmp_path):
    d = tmp_path / "somewhere"
    d.mkdir()
    (d / "needle.txt").write_text("x")
    hits = UniversalFilesystem.search_filesystem("needle", root_dir=str(d))
    assert hits and hits[0]["file_name"] == "needle.txt"
    assert "scope" not in hits[0]   # explicit path: no scope tagging


def test_missing_canonical_folder_falls_back_to_home(fake_home):
    """No Downloads folder on this machine: search the home superset rather
    than an empty scope — a superset can only find more, never miss."""
    (fake_home / "installer.exe").write_text("x")
    hits = UniversalFilesystem.search_filesystem("installer", scope="downloads")
    assert hits and hits[0]["file_name"] == "installer.exe"


def test_workspace_scope_targets_the_agent_directory():
    roots = UniversalFilesystem.resolve_scope_roots("workspace")
    assert roots == [Path(settings.BASE_DIR)]


def test_unknown_scope_falls_back_to_all_user_files():
    roots = UniversalFilesystem.resolve_scope_roots("galaxy_wide")
    assert roots == UniversalFilesystem.resolve_scope_roots("all_user_files")


def test_manifest_search_files_accepts_scope(fake_home):
    from app.tools.manifest import get_tool_manifest
    (fake_home / "Music" / "Kaba.mp3").write_text("x")
    handler = get_tool_manifest()["search_files"]["handler"]
    res = handler({"query": "Kaba", "scope": "music", "max_results": 5})
    assert res and res[0]["file_name"] == "Kaba.mp3" and res[0]["scope"] == "music"


def test_observation_router_roots_use_the_scope_system():
    from app.cognition.observation_router import _file_search_roots
    expected = [str(r) for r in UniversalFilesystem.resolve_scope_roots("all_user_files")]
    assert _file_search_roots() == expected
