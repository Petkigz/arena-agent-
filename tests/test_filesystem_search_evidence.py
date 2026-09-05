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
import uuid

from app.tools.universal_filesystem import UniversalFilesystem


# Per-run unique token: searches escalate to ALL roots when the explicit
# root has no hits (D7), and the owner's real drives hold their ACTUAL
# "Kaba - Official Video.mp3" — the 2026-09-02 owner run failed the
# "deleted file is never reported" assertion on that doppelganger. A
# uuid-based token exists only inside tmp_path, so escalation can only
# ever find (or verified-out miss) OUR files.
_TOKEN = f"kaba{uuid.uuid4().hex[:8]}"
_ORDINARY = f"ordinary{uuid.uuid4().hex[:8]}"


def _make_tree(tmp: Path) -> Path:
    home = tmp / "home"
    media = home / "Music"
    media.mkdir(parents=True)
    other = tmp / "driveF" / "Media"
    other.mkdir(parents=True)
    (media / f"{_TOKEN} - Official Video.mp3").write_text("x")
    (other / _TOKEN.upper()).mkdir()  # album folder on another 'drive'
    (other / f"Alex Warren - {_ORDINARY.capitalize()}.mp3").write_text("x")
    # Junk that must be pruned, not matched.
    junk = home / "AppData" / "Local" / "Junk"
    junk.mkdir(parents=True)
    (junk / f"{_TOKEN}.dll").write_text("x")
    (home / "node_modules" / _TOKEN).mkdir(parents=True)
    return home


def test_search_matches_directories_not_just_files(tmp_path):
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem(
        _TOKEN, root_dir=[str(home), str(tmp_path / "driveF")]
    )
    kinds = {h["file_name"]: h["type"] for h in hits}
    assert f"{_TOKEN} - Official Video.mp3" in kinds and kinds[f"{_TOKEN} - Official Video.mp3"] == "file"
    assert _TOKEN.upper() in kinds and kinds[_TOKEN.upper()] == "directory"


def test_search_prunes_system_and_junk_dirs(tmp_path):
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem(_TOKEN, root_dir=str(home))
    names = [h["file_name"] for h in hits]
    assert f"{_TOKEN}.dll" not in names  # inside AppData
    assert _TOKEN not in names           # inside node_modules


def test_search_fuzzy_fallback_recovers_typos(tmp_path):
    """'ordinaryr' (the owner's typo) must still surface
    'Alex Warren - Ordinary.mp3' via per-token fuzzy matching."""
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem(
        _ORDINARY[:2] + _ORDINARY[3:], root_dir=[str(home), str(tmp_path / "driveF")]
    )
    assert hits, "typo'd query must return fuzzy matches, not nothing"
    top = hits[0]
    assert _ORDINARY.capitalize() in top["file_name"]
    assert top.get("fuzzy_match") is True
    assert top.get("fuzzy_score", 0) >= 0.78


def test_exact_match_beats_fuzzy(tmp_path):
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem(
        _ORDINARY, root_dir=[str(tmp_path / "driveF")]
    )
    assert all(h.get("match") == "exact" for h in hits)
    assert any(_ORDINARY.capitalize() in h["file_name"] for h in hits)


def test_multi_root_search_covers_other_drives(tmp_path):
    home = _make_tree(tmp_path)
    # Home alone misses the album folder; both roots find it.
    home_only = UniversalFilesystem.search_filesystem(_TOKEN, root_dir=str(home))
    assert not any(h["file_name"] == _TOKEN.upper() for h in home_only)
    both = UniversalFilesystem.search_filesystem(
        _TOKEN, root_dir=[str(home), str(tmp_path / "driveF")]
    )
    assert any(h["file_name"] == _TOKEN.upper() for h in both)


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
        {"query": _TOKEN, "root_dir": [str(home), str(tmp_path / "driveF")], "max_results": 20}
    )
    assert any(h["file_name"] == _TOKEN.upper() for h in result)


def test_fuzzy_survives_typos_in_first_chars(tmp_path):
    """'orinary' (dropped 'd' from 'ordinary') was rejected by the old
    positional prefilter — its first three chars 'ori' never appear in the
    filename. The prefilter must be character-based, not positional."""
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem(
        _ORDINARY[:2] + _ORDINARY[3:], root_dir=str(tmp_path / "driveF"))
    assert hits and _ORDINARY.capitalize() in hits[0]["file_name"]
    assert hits[0].get("fuzzy_match") is True


def test_fuzzy_catches_adjacent_transpositions(tmp_path):
    """'kbaa' for 'kaba': edit distance punishes the swap a human never
    notices (0.75 < 0.78) — the anagram boost must carry it."""
    home = _make_tree(tmp_path)
    transposed = _TOKEN[0] + _TOKEN[2] + _TOKEN[1] + _TOKEN[3:]
    hits = UniversalFilesystem.search_filesystem(transposed, root_dir=str(home))
    assert hits and _TOKEN in hits[0]["file_name"].lower()
    assert hits[0].get("fuzzy_match") is True


def test_fuzzy_still_rejects_junk(tmp_path):
    """Tolerance must not become noise: a query sharing few characters with
    the tree yields nothing."""
    home = _make_tree(tmp_path)
    assert UniversalFilesystem.search_filesystem("zzznope", root_dir=str(home)) == []


def test_artist_tail_stripped_from_file_question():
    """Live bug: 'do i have a song called ordinary by alex warren' searched
    for the whole phrase 'ordinary by alex warren' — which matches neither
    the exact filename ('Alex Warren - Ordinary.mp3') nor the fuzzy matcher
    (word order reversed). The artist must be stripped into a hint."""
    plan = plan_observation("do i have a song called ordinary by alex warren")
    assert plan is not None and plan.action_type == "search_files"
    assert plan.payload["query"] == "ordinary"
    assert "alex warren" in plan.evidence_hint.lower()

    # Broad phrasing gets the same treatment.
    plan2 = plan_observation("give me a list of all the songs called ordinary by alex warren")
    assert plan2 is not None and plan2.action_type == "search_files"
    assert plan2.payload["query"] == "ordinary"


def test_word_order_independent_fuzzy_match(tmp_path):
    """Even WITH the artist left in the query, the search must match
    'ordinary by alex warren' to 'Alex Warren - Ordinary.mp3'. The token
    tier (2026-09-05) answers this deterministically — a distinctive query
    token as a filename substring — so the pinned invariant is the FIND,
    satisfied by either the token tier or the fuzzy fallback it subsumes."""
    home = _make_tree(tmp_path)
    hits = UniversalFilesystem.search_filesystem(
        f"{_ORDINARY} by alex warren", root_dir=str(tmp_path / "driveF")
    )
    assert hits and _ORDINARY.capitalize() in hits[0]["file_name"]
    assert hits[0].get("match") == "token" or hits[0].get("fuzzy_match") is True


def test_persistent_index_accelerates_without_lying(tmp_path):
    """The agent's own mini-Everything: a persistent filename index.
    - warm searches are cache hits (existence-verified)
    - a file CREATED after indexing is still found (miss -> live walk)
    - a file DELETED after indexing is never reported (verified out)
    """
    from app.tools.file_index import get_file_index, reset_file_index

    reset_file_index(str(tmp_path / "file_index.db"))
    home = _make_tree(tmp_path)
    roots = [str(tmp_path)]

    cold = UniversalFilesystem.search_filesystem(_ORDINARY, root_dir=roots)
    assert any(_ORDINARY.capitalize() in h["file_name"] for h in cold)

    warm = UniversalFilesystem.search_filesystem(_ORDINARY, root_dir=roots)
    assert any(_ORDINARY.capitalize() in h["file_name"] for h in warm)
    assert get_file_index().stats["hits"] >= 1, "second search must use the index"

    # Created after indexing -> still found (never a stale miss).
    fresh_name = f"Brand New Track {uuid.uuid4().hex[:6]}.mp3"
    (tmp_path / "home" / "Music" / fresh_name).write_text("x")
    fresh = UniversalFilesystem.search_filesystem(fresh_name[:-4], root_dir=roots)
    assert any(fresh_name in h["file_name"] for h in fresh)

    # Deleted after indexing -> never reported (existence-verified out).
    # Owner report #5 (2026-09-02): this also pins the explicit-root
    # CONSTRAINT — the search must not escalate past the caller's root,
    # so a same-named file on any other drive can never leak in. (The
    # original failure: escalation to all_user_files returned the
    # owner's REAL same-named video from another indexed drive.)
    (tmp_path / "home" / "Music" / f"{_TOKEN} - Official Video.mp3").unlink()
    gone = UniversalFilesystem.search_filesystem(
        _TOKEN, root_dir=[str(tmp_path / "home")])
    assert gone == [], (
        "deleted file must never be reported, and the explicit root must "
        f"constrain the search (got {[h.get('file_path') for h in gone]})")
