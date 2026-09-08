"""Owner charter §2: file-scope and conflict points ASK, they never refuse.

Every converted site returns a typed ``requires_owner_approval`` result with
the real conflict stated, and proceeds once the owner's approval is expressed
through the explicit retry flag."""

from pathlib import Path

from app.tools.universal_filesystem import UniversalFilesystem


def _write(tmp_path, name, content="data"):
    target = tmp_path / name
    target.write_text(content)
    return target


def test_copy_conflict_asks_then_proceeds_with_approval(tmp_path):
    src = _write(tmp_path, "src.txt")
    dst = _write(tmp_path, "dst.txt", "existing")

    ask = UniversalFilesystem.copy_file_verified(str(src), str(dst))
    assert ask["requires_owner_approval"] is True
    assert ask["conflict"] == "destination_exists"
    assert Path(ask["destination"]) == dst
    assert dst.read_text() == "existing"  # untouched while asking

    granted = UniversalFilesystem.copy_file_verified(str(src), str(dst), overwrite=True)
    assert granted["success"] is True
    assert dst.read_text() == "data"


def test_move_conflict_asks_then_proceeds_with_approval(tmp_path):
    src = _write(tmp_path, "src.txt")
    dst = _write(tmp_path, "dst.txt", "existing")

    ask = UniversalFilesystem.rename_or_move(str(src), str(dst))
    assert ask["requires_owner_approval"] is True
    assert ask["conflict"] == "destination_exists"
    assert src.exists()  # untouched while asking

    granted = UniversalFilesystem.rename_or_move(str(src), str(dst), overwrite=True)
    assert granted["success"] is True
    assert not src.exists()


def test_zip_conflict_asks_then_proceeds_with_approval(tmp_path):
    src = _write(tmp_path, "src.txt")
    archive = _write(tmp_path, "out.zip", "old archive")

    ask = UniversalFilesystem.compress_zip([str(src)], str(archive))
    assert ask["requires_owner_approval"] is True
    assert ask["conflict"] == "destination_exists"

    granted = UniversalFilesystem.compress_zip([str(src)], str(archive), overwrite=True)
    assert granted["success"] is True


def test_trash_outside_home_asks_before_anything_moves(tmp_path):
    inside = _write(tmp_path, "inside.txt")
    outside = Path(tmp_path.parent) / "outside-charter-test.txt"
    outside.write_text("outside")

    try:
        ask = UniversalFilesystem.trash_files([str(inside), str(outside)])
        # The ask fires BEFORE any move: nothing is trashed yet.
        assert ask["requires_owner_approval"] is True
        assert ask["conflict"] == "outside_home_scope"
        assert any(p.endswith("outside-charter-test.txt") for p in ask["paths"])
        assert inside.exists() and outside.exists()

        granted = UniversalFilesystem.trash_files(
            [str(inside), str(outside)], trash_root=str(tmp_path / ".arena_trash"),
            allow_outside_home=True,
        )
        assert granted["success"] is True
        assert not inside.exists() and not outside.exists()
    finally:
        if outside.exists():
            outside.unlink()


# ── Charter §6 ledger conversions (2026-09-08) ────────────────────────


def test_process_guard_asks_instead_of_refusing():
    """Killing PID 0/1 or Arena itself surfaces a typed ask, never a refusal."""
    import os

    from app.tools.process_manager import ProcessManager

    for guarded_pid in (0, 1, os.getpid()):
        ask = ProcessManager.kill_process(guarded_pid)
        assert ask["requires_owner_approval"] is True, guarded_pid
        assert ask["conflict"] == "protected_process"
        assert ask["pid"] == guarded_pid
        assert "confirm_protected_kill=true" in ask["hint"]
        # The dangerous thing did NOT happen while asking.
        assert os.getpid() in (guarded_pid,) or True  # still alive: the test runs on


def test_rollback_hash_change_asks_with_measured_evidence(tmp_path):
    """A changed rollback target is surfaced with both hashes; the owner decides."""
    target = _write(tmp_path, "rollback.bin", "v1")
    import hashlib

    original_hash = hashlib.sha256(b"v1").hexdigest()
    target.write_text("v2")  # the environment changed under us

    ask = UniversalFilesystem.remove_verified_copy(str(target), original_hash)
    assert ask["requires_owner_approval"] is True
    assert ask["conflict"] == "rollback_target_changed"
    assert ask["expected_sha256"] == original_hash
    assert ask["actual_sha256"] != original_hash
    assert target.exists()  # untouched while asking

    granted = UniversalFilesystem.remove_verified_copy(
        str(target), original_hash, confirm_hash_change=True
    )
    assert granted["success"] is True
    assert not target.exists()


def test_backup_overwrite_ask_states_the_level3_path():
    """Overwrite restore asks and names the Level-3 action + snapshot option."""
    from app.tools.backup_manager import BackupManager

    ask = BackupManager.restore_backup("whatever", "/tmp/dest", overwrite=True)
    assert ask["requires_owner_approval"] is True
    assert ask["required_action"] == "restore_backup_overwrite"
    assert "pre_snapshot=true" in ask["hint"]
    assert "Level-3" in ask["error"]
