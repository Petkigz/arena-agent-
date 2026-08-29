"""Filesystem search evidence: directories matched, typo-tolerant fuzzy
fallback, multi-root walks, and honest absence claims.

Live incident: the owner asked for songs called 'kaba'/'ordinary' that exist
on other drives (per Everything), and the agent answered 'there are no files
or folders named…' because the search (a) walked only the home directory,
(b) matched files but not folders, (c) required an exact substring (the
request 'ordinaryr' vs file 'Ordinary'), and (d) rendered absence as a
machine-wide fact. Everything reads the NTFS MFT; this tool walks the tree —
the evidence must say so."""
import shutil
from pathlib import Path

from app.cognition.observation_router import (
    ObservationPlan,
    plan_observation,
    render_observation_evidence,
)
from app.tools.manifest import get_tool_manifest
from app.tools.universal_filesystem import UniversalFilesystem


def _make_tree(tmp: Path) -> Path:
    home = tmp / "home"
    media = home / "Music"
    media.mkdir(parents=True)
    other = tmp / "driveF" / "Media"
    other.mkdir(parents=True)
    (media / "Kaba - Official Video.mp3").write_text("x")
    (other / "KABA").mkdir()  # album folder on another 'drive'
    (other / "Alex Warren - Ordinary.mp3").write_text("x")
    # Junk that must be pruned, not matched.
    junk = home / "AppData" / "Local" / "Junk"
    junk.mkdir(parents=True)
    (junk / "kaba.dll").write_text("x")
    (home / "node_modules" / "kaba").mkdir(parents=True)
    return home


def test_search_matches_directories_not_just_files(tmp_path):
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem(
        "kaba", root_dir=[str(home), str(tmp_path / "driveF")]
    )
    kinds = {h["file_name"]: h["type"] for h in hits}
    assert "Kaba - Official Video.mp3" in kinds and kinds["Kaba - Official Video.mp3"] == "file"
    assert "KABA" in kinds and kinds["KABA"] == "directory"


def test_search_prunes_system_and_junk_dirs(tmp_path):
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem("kaba", root_dir=str(home))
    names = [h["file_name"] for h in hits]
    assert "kaba.dll" not in names  # inside AppData
    assert "kaba" not in names      # inside node_modules


def test_search_fuzzy_fallback_recovers_typos(tmp_path):
    """'ordinaryr' (the owner's typo) must still surface
    'Alex Warren - Ordinary.mp3' via per-token fuzzy matching."""
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem(
        "ordinaryr", root_dir=[str(home), str(tmp_path / "driveF")]
    )
    assert hits, "typo'd query must return fuzzy matches, not nothing"
    top = hits[0]
    assert "Ordinary" in top["file_name"]
    assert top.get("fuzzy_match") is True
    assert top.get("fuzzy_score", 0) >= 0.78


def test_exact_match_beats_fuzzy(tmp_path):
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem(
        "ordinary", root_dir=[str(tmp_path / "driveF")]
    )
    assert all(h.get("match") == "exact" for h in hits)
    assert any("Ordinary" in h["file_name"] for h in hits)


def test_multi_root_search_covers_other_drives(tmp_path):
    home = _make_tree(tmp_path)
    # Home alone misses the album folder; both roots find it.
    home_only = UniversalFilesystem.search_filesystem("kaba", root_dir=str(home))
    assert not any(h["file_name"] == "KABA" for h in home_only)
    both = UniversalFilesystem.search_filesystem(
        "kaba", root_dir=[str(home), str(tmp_path / "driveF")]
    )
    assert any(h["file_name"] == "KABA" for h in both)


def _render_for(query_results, question_kind="file_search", payload=None):
    plan = ObservationPlan(
        action_type="search_files",
        payload=payload or {"query": "x", "root_dir": ["/home/u", "D:\\"], "max_results": 20},
        evidence_hint="",
        question_kind=question_kind,
    )
    return render_observation_evidence(query_results, plan)


def test_render_no_match_is_scoped_not_absolute():
    ev = _render_for([])
    assert "NO matches" in ev
    assert "Do NOT claim the file does not exist" in ev
    assert "D:\\" in ev  # which roots were searched are named in the evidence


def test_render_fuzzy_matches_are_presented_as_likely_intent():
    results = [
        {
            "file_name": "Alex Warren - Ordinary.mp3",
            "file_path": "F:/Media/Alex Warren - Ordinary.mp3",
            "type": "file",
            "match": "fuzzy",
            "fuzzy_match": True,
            "fuzzy_score": 0.94,
        }
    ]
    ev = _render_for(results)
    assert "NO exact filename matches" in ev
    assert "0.94" in ev
    assert "possible typo" in ev


def test_render_directory_matches_are_labelled():
    results = [
        {"file_name": "KABA", "file_path": "F:/Media/KABA", "type": "directory", "match": "exact"}
    ]
    ev = _render_for(results)
    assert "[folder]" in ev


def test_router_payload_uses_multi_root_search():
    plan = plan_observation("do i have a song called kaba on my pc")
    assert plan is not None and plan.action_type == "search_files"
    assert isinstance(plan.payload["root_dir"], list)
    assert plan.payload["root_dir"], "at least the home directory must be searched"


def test_manifest_handler_accepts_list_root(tmp_path):
    """The router payload flows through the manifest wrapper into
    search_filesystem unchanged (list root included)."""
    home = _make_tree(tmp_path)
    manifest = get_tool_manifest()
    entry = manifest["search_files"]
    result = entry["handler"](
        {"query": "kaba", "root_dir": [str(home), str(tmp_path / "driveF")], "max_results": 20}
    )
    assert any(h["file_name"] == "KABA" for h in result)
