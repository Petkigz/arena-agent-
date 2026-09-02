"""Owner report #4 (D9 live, 2026-09-02): the file-organization
capabilities behind the D9 milestone phrases.

'date-based categorization' and 'duplicate detection' resolved as
UNRESOLVED because no registered implementation existed — the honest
outcome at the time, but the capability SET was incomplete for Arena's
file-organization domain (the D9 project: scan, group by date, find
duplicates, report). These are the two registered implementations the
resolver now aliases to:

  * detect_duplicate_files — content-addressed (size bucket -> sha256),
    read-only, reports true duplicate groups (identical bytes) and
    wasted space. Never name-similar files, never zero-byte noise.
  * group_files_by_date — dry-run report by default (the grouping
    plan, nothing moved); execute=true moves files into
    root/YYYY-MM-DD/ without overwriting.
"""

import os
import time
import uuid

from app.tools.universal_filesystem import UniversalFilesystem


def _touch(path, content=b"x", mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


# ── detect_duplicate_files ────────────────────────────────────────────────────

def test_true_duplicates_are_found_by_content():
    root = _mk_root()
    payload = uuid.uuid4().bytes * 64
    _touch(root / "a" / "photo1.jpg", payload)
    _touch(root / "b" / "copy.jpg", payload)          # same bytes
    _touch(root / "c" / "other.png", uuid.uuid4().bytes * 64)

    res = UniversalFilesystem.detect_duplicate_files(str(root))

    assert res["success"] is True
    assert res["scanned_files"] == 3
    assert res["duplicate_group_count"] == 1
    group = res["duplicate_groups"][0]
    assert group["size_bytes"] == len(payload)
    assert sorted(os.path.basename(p) for p in group["paths"]) == \
        ["copy.jpg", "photo1.jpg"]
    assert res["wasted_bytes"] == len(payload)  # one redundant copy


def test_name_similar_files_are_not_duplicates():
    root = _mk_root()
    _touch(root / "report.pdf", b"version one")
    _touch(root / "report (1).pdf", b"version two")   # different bytes

    res = UniversalFilesystem.detect_duplicate_files(str(root))

    assert res["success"] is True
    assert res["duplicate_group_count"] == 0
    assert res["duplicate_groups"] == []
    assert res["wasted_bytes"] == 0


def test_zero_byte_files_are_not_duplicate_noise():
    root = _mk_root()
    _touch(root / "empty1.txt", b"")
    _touch(root / "empty2.txt", b"")

    res = UniversalFilesystem.detect_duplicate_files(str(root))

    assert res["duplicate_group_count"] == 0


def test_missing_root_is_an_honest_error():
    res = UniversalFilesystem.detect_duplicate_files("/nonexistent/definitely/not/here")
    assert res["success"] is False
    assert "not found" in res["error"].lower()


def test_manifest_dispatches_the_tool(tmp_path):
    from app.tools.manifest import get_tool_manifest
    payload = uuid.uuid4().bytes * 32
    _touch(tmp_path / "x.bin", payload)
    _touch(tmp_path / "y.bin", payload)
    entry = get_tool_manifest()["detect_duplicate_files"]
    res = entry["handler"]({"root_dir": str(tmp_path)})
    assert res["success"] is True
    assert res["duplicate_group_count"] == 1


# ── group_files_by_date ─────────────────────────────────────────────────────

def test_default_is_a_dry_run_nothing_moves():
    root = _mk_root()
    _touch(root / "old.txt", b"1", mtime=1_000_000_000)     # 2001-09-09 UTC-ish
    _touch(root / "new.txt", b"2", mtime=1_700_000_000)     # 2023-11-14 UTC-ish

    res = UniversalFilesystem.group_files_by_date(str(root))

    assert res["success"] is True
    assert res["execute"] is False
    assert res["planned_moves"] == 2
    assert len(res["groups"]) == 2
    # Nothing moved: files still where they were, no date folders.
    assert (root / "old.txt").exists() and (root / "new.txt").exists()
    assert not any(p.is_dir() and p.name[:2] == "20" for p in root.iterdir())
    assert "dry-run" in res["note"].lower()


def test_execute_moves_files_into_date_folders_without_overwriting():
    root = _mk_root()
    day = 1_600_000_000  # a fixed day timestamp
    _touch(root / "a.txt", b"a", mtime=day)
    _touch(root / "sub" / "b.txt", b"b", mtime=day)
    # A file ALREADY in its date folder, named like a collision target.
    date_key = time.strftime("%Y-%m-%d", time.gmtime(day))
    _touch(root / date_key / "a.txt", b"existing", mtime=day)

    res = UniversalFilesystem.group_files_by_date(str(root), execute=True)

    assert res["success"] is True
    assert res["execute"] is True
    assert res["moved_files"] == 2  # the two loose files; the placed one is a no-op
    assert not (root / "a.txt").exists()
    assert not (root / "sub" / "b.txt").exists()
    # The pre-existing a.txt was NOT overwritten, NOT renamed (no-op), and
    # the newcomer got a suffix.
    assert (root / date_key / "a.txt").read_bytes() == b"existing"
    assert (root / date_key / "a (1).txt").read_bytes() == b"a"
    assert (root / date_key / "b.txt").read_bytes() == b"b"

    # Re-running is idempotent: everything is already in its date folder.
    res2 = UniversalFilesystem.group_files_by_date(str(root), execute=True)
    assert res2["success"] is True
    assert res2["moved_files"] == 0
    assert (root / date_key / "a.txt").read_bytes() == b"existing"


def test_grouping_uses_modification_date(tmp_path):
    root = tmp_path / f"org-{uuid.uuid4().hex[:8]}"
    _touch(root / "day1.txt", b"1", mtime=1_500_000_000)
    _touch(root / "day1b.txt", b"2", mtime=1_500_000_900)   # same day
    _touch(root / "day2.txt", b"3", mtime=1_510_000_000)    # different day

    res = UniversalFilesystem.group_files_by_date(str(root))

    sizes = sorted(len(v) for v in res["groups"].values())
    assert sizes == [1, 2]
    key_for_two = [k for k, v in res["groups"].items() if len(v) == 2][0]
    assert {os.path.basename(p) for p in res["groups"][key_for_two]} == \
        {"day1.txt", "day1b.txt"}


def _mk_root(tmp=None):
    import pathlib
    base = pathlib.Path(tmp) if tmp else None
    if base is None:
        import tempfile
        base = pathlib.Path(tempfile.mkdtemp())
    root = base / f"dup-{uuid.uuid4().hex[:8]}"
    root.mkdir(parents=True)
    return root
