"""BackupManager tests — create/list/verify/restore/delete, deterministic
(real zip + sha256) against a tmp source tree."""

from app.tools.backup_manager import BackupManager


def _write_files(root):
    (root / "a.txt").write_text("hello")
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("world")
    return [str(root / "a.txt"), str(sub)]


def test_create_and_list(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    _write_files(src)

    # Isolate the backup store so the global DATA_DIR isn't touched.
    monkeypatch.setattr(BackupManager, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(BackupManager, "INDEX_PATH", tmp_path / "backups" / "index.json")

    res = BackupManager.create_backup([str(src)])
    assert res["success"] is True
    assert res["file_count"] == 2  # a.txt + sub/b.txt
    assert res["backup_id"]

    lst = BackupManager.list_backups()
    assert lst["success"] is True
    assert lst["count"] == 1
    assert lst["backups"][0]["id"] == res["backup_id"]


def test_create_requires_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(BackupManager, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(BackupManager, "INDEX_PATH", tmp_path / "backups" / "index.json")
    assert BackupManager.create_backup([])["success"] is False


def test_create_missing_source(tmp_path, monkeypatch):
    monkeypatch.setattr(BackupManager, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(BackupManager, "INDEX_PATH", tmp_path / "backups" / "index.json")
    res = BackupManager.create_backup([str(tmp_path / "nope")])
    assert res["success"] is False
    assert "not found" in res["error"].lower()


def test_verify_roundtrip(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("hello")

    monkeypatch.setattr(BackupManager, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(BackupManager, "INDEX_PATH", tmp_path / "backups" / "index.json")

    res = BackupManager.create_backup([str(src)])
    bid = res["backup_id"]

    ver = BackupManager.verify_backup(bid)
    assert ver["success"] is True
    assert ver["intact"] is True


def test_verify_missing_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(BackupManager, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(BackupManager, "INDEX_PATH", tmp_path / "backups" / "index.json")
    assert BackupManager.verify_backup("nope")["success"] is False


def test_restore(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("hello")

    monkeypatch.setattr(BackupManager, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(BackupManager, "INDEX_PATH", tmp_path / "backups" / "index.json")

    bid = BackupManager.create_backup([str(src)])["backup_id"]
    dest = tmp_path / "restored"
    res = BackupManager.restore_backup(bid, str(dest))
    assert res["success"] is True
    # The archive stored a.txt relative to src's parent, so a.txt lands directly.
    assert (dest / "a.txt").exists() or any(dest.rglob("a.txt"))


def test_restore_refuses_overwrite(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("hello")

    monkeypatch.setattr(BackupManager, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(BackupManager, "INDEX_PATH", tmp_path / "backups" / "index.json")

    bid = BackupManager.create_backup([str(src)])["backup_id"]
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "existing.txt").write_text("x")

    assert BackupManager.restore_backup(bid, str(dest))["success"] is False
    # Overwrite is a separate Level-3 operation.
    redirected = BackupManager.restore_backup(bid, str(dest), overwrite=True)
    assert redirected["success"] is False
    assert redirected["required_action"] == "restore_backup_overwrite"
    assert BackupManager.restore_backup_overwrite(bid, str(dest))["success"] is True


def test_delete_backup(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("hello")

    monkeypatch.setattr(BackupManager, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(BackupManager, "INDEX_PATH", tmp_path / "backups" / "index.json")

    bid = BackupManager.create_backup([str(src)])["backup_id"]
    assert BackupManager.delete_backup(bid)["success"] is True
    assert BackupManager.list_backups()["count"] == 0
    assert BackupManager.delete_backup(bid)["success"] is False


def test_refuses_to_backup_backup_dir(tmp_path, monkeypatch):
    bk = tmp_path / "backups"
    bk.mkdir()
    monkeypatch.setattr(BackupManager, "BACKUP_DIR", bk)
    monkeypatch.setattr(BackupManager, "INDEX_PATH", bk / "index.json")
    res = BackupManager.create_backup([str(bk)])
    assert res["success"] is False
