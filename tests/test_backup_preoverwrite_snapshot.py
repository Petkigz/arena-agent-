"""Pre-overwrite snapshots make restore_backup_overwrite recoverable.

With pre_snapshot=True, every existing file the archive will overwrite is first
captured into a verified backup whose arcnames match the archive members — so
restoring the snapshot reproduces the exact pre-overwrite state. Snapshot
failure refuses the overwrite with zero side effects.
"""
from pathlib import Path
from unittest.mock import patch

from app.tools.backup_manager import BackupManager


def setup_manager(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(BackupManager, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(BackupManager, "INDEX_PATH", backup_dir / "index.json")
    # Relative destination paths resolve under BASE_DIR; use absolute paths.
    return backup_dir


def make_backup_with(tmp_path, monkeypatch, content: str, name: str = "src") -> str:
    setup_manager(tmp_path, monkeypatch)
    source = tmp_path / "origin"
    source.mkdir(exist_ok=True)
    (source / "a.txt").write_text(content)
    result = BackupManager.create_backup([str(source / "a.txt")], name=name)
    assert result["success"] is True, result
    return result["backup_id"]


def test_overwrite_with_pre_snapshot_creates_recoverable_backup(tmp_path, monkeypatch):
    backup_id = make_backup_with(tmp_path, monkeypatch, content="new-content")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("old-content")
    (dest / "untouched.txt").write_text("stay")

    result = BackupManager.restore_backup_overwrite(backup_id, str(dest), pre_snapshot=True)
    assert result["success"] is True
    assert result["pre_overwrite_snapshot"]["created"] is True
    snapshot_id = result["rollback_backup_id"]
    assert result["rollback_supported"] is True
    # Overwrite happened; untouched file survived.
    assert (dest / "a.txt").read_text() == "new-content"
    assert (dest / "untouched.txt").read_text() == "stay"

    # The snapshot is a normal verified backup containing ONLY the overwritten file.
    listing = BackupManager.list_backups()["backups"]
    snapshot_entry = next(e for e in listing if e["id"] == snapshot_id)
    assert snapshot_entry["file_count"] == 1
    assert snapshot_entry["overwrote_files"] == ["a.txt"]
    assert BackupManager.verify_backup(snapshot_id)["intact"] is True


def test_snapshot_restores_the_pre_overwrite_state(tmp_path, monkeypatch):
    backup_id = make_backup_with(tmp_path, monkeypatch, content="new-content")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("old-content")
    overwritten = BackupManager.restore_backup_overwrite(backup_id, str(dest), pre_snapshot=True)
    assert (dest / "a.txt").read_text() == "new-content"

    rollback = BackupManager.restore_backup_overwrite(overwritten["rollback_backup_id"], str(dest))
    assert rollback["success"] is True
    assert (dest / "a.txt").read_text() == "old-content"


def test_snapshot_failure_refuses_overwrite_without_side_effects(tmp_path, monkeypatch):
    backup_id = make_backup_with(tmp_path, monkeypatch, content="new-content")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("old-content")

    def broken_snapshot(*args, **kwargs):
        return {"created": False, "error": "disk full while zipping"}

    with patch.object(BackupManager, "_create_preoverwrite_snapshot", side_effect=broken_snapshot):
        result = BackupManager.restore_backup_overwrite(backup_id, str(dest), pre_snapshot=True)
    assert result["success"] is False and result["refused"] is True
    assert result["side_effects"] is False
    assert "snapshot failed" in result["error"].lower()
    # The destination is untouched — destruction never happens without recovery evidence.
    assert (dest / "a.txt").read_text() == "old-content"


def test_no_existing_files_means_no_snapshot_needed(tmp_path, monkeypatch):
    backup_id = make_backup_with(tmp_path, monkeypatch, content="fresh")
    dest = tmp_path / "empty-dest"
    result = BackupManager.restore_backup_overwrite(backup_id, str(dest), pre_snapshot=True)
    assert result["success"] is True
    assert result["pre_overwrite_snapshot"]["created"] is False
    assert result["pre_overwrite_snapshot"]["reason"] == "no existing files would be overwritten"
    assert result["rollback_supported"] is False
    assert (dest / "a.txt").read_text() == "fresh"


def test_default_overwrite_behavior_is_unchanged(tmp_path, monkeypatch):
    backup_id = make_backup_with(tmp_path, monkeypatch, content="new-content")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("old-content")
    result = BackupManager.restore_backup_overwrite(backup_id, str(dest))
    assert result["success"] is True
    assert "pre_overwrite_snapshot" not in result
    assert result["rollback_supported"] is False
    assert (dest / "a.txt").read_text() == "new-content"  # old content destroyed, as before


def test_snapshot_only_covers_files_the_archive_overwrites(tmp_path, monkeypatch):
    backup_id = make_backup_with(tmp_path, monkeypatch, content="new-content", name="only-a")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("old-a")
    (dest / "b.txt").write_text("old-b")  # not in the archive
    result = BackupManager.restore_backup_overwrite(backup_id, str(dest), pre_snapshot=True)
    snapshot = result["pre_overwrite_snapshot"]
    assert snapshot["created"] is True and snapshot["overwrote_files"] == ["a.txt"]
    assert (dest / "b.txt").read_text() == "old-b"  # never touched, never snapshotted
