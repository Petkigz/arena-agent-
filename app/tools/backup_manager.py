"""Backup & restore — versioned zip snapshots of files/directories.

Deterministic (stdlib zipfile/hashlib/json, no LLM). Each backup is a zip whose
SHA-256 is recorded in an index; `verify_backup` recomputes it so corruption is
detectable, not assumed away.

Safety model (manifest authoritative):
- create_backup / list_backups / verify_backup → Level 0-1 (read/create).
- restore_backup → Level 2 (writes files; refuses to overwrite a non-empty
  destination unless `overwrite=True`).
- delete_backup → Level 3 (irreversible).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger, audit_logger


class BackupManager:
    BACKUP_DIR = settings.DATA_DIR / "backups"
    INDEX_PATH = BACKUP_DIR / "index.json"

    @classmethod
    def ensure_dir(cls) -> None:
        cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ── index ───────────────────────────────────────────────────────────────
    @classmethod
    def _load_index(cls) -> Dict[str, Dict[str, Any]]:
        if not cls.INDEX_PATH.exists():
            return {}
        try:
            return json.loads(cls.INDEX_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            app_logger.warning(f"Backup index unreadable: {e}")
            return {}

    @classmethod
    def _save_index(cls, index: Dict[str, Dict[str, Any]]) -> None:
        cls.ensure_dir()
        cls.INDEX_PATH.write_text(json.dumps(index, indent=2, default=str), encoding="utf-8")

    # ── create (Level 1) ────────────────────────────────────────────────────
    @classmethod
    def create_backup(cls, sources: List[str], name: Optional[str] = None) -> Dict[str, Any]:
        """Zip the given files/directories into a versioned snapshot."""
        if not sources:
            return {"success": False, "error": "At least one source path is required."}
        paths: List[Path] = []
        for s in sources:
            p = Path(s)
            if not p.is_absolute():
                p = settings.BASE_DIR / p
            if not p.exists():
                return {"success": False, "error": f"Source not found: '{p}'"}
            # Never back up the backup directory into itself.
            if cls.BACKUP_DIR in p.parents or p == cls.BACKUP_DIR:
                return {"success": False, "error": f"Refusing to back up the backup directory: '{p}'"}
            paths.append(p)

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = (name or "backup").strip().replace(" ", "_") or "backup"
        backup_id = f"{stamp}_{safe_name}"
        zip_path = cls.BACKUP_DIR / f"{backup_id}.zip"
        cls.ensure_dir()

        file_count = 0
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in paths:
                    if p.is_dir():
                        for root, _dirs, files in os.walk(p):
                            for fn in files:
                                fp = Path(root) / fn
                                zf.write(fp, fp.relative_to(p.parent))
                                file_count += 1
                    else:
                        zf.write(p, p.name)
                        file_count += 1
        except Exception as e:
            app_logger.warning(f"Backup creation failed: {e}")
            return {"success": False, "error": f"Backup creation failed: {e}"}

        size = zip_path.stat().st_size
        sha = cls._sha256(zip_path)
        entry = {
            "id": backup_id,
            "name": safe_name,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "sources": [str(p) for p in paths],
            "file_count": file_count,
            "size_bytes": size,
            "sha256": sha,
            "path": str(zip_path),
        }
        index = cls._load_index()
        index[backup_id] = entry
        cls._save_index(index)
        audit_logger.info(f"Created backup {backup_id} ({file_count} files, {size} bytes)")
        return {"success": True, **{k: v for k, v in entry.items() if k != "path"}, "backup_id": backup_id}

    # ── list / verify (Level 0) ─────────────────────────────────────────────
    @classmethod
    def list_backups(cls) -> Dict[str, Any]:
        index = cls._load_index()
        entries = sorted(index.values(), key=lambda e: e.get("created_at", ""), reverse=True)
        return {"success": True, "count": len(entries), "backups": entries}

    @classmethod
    def verify_backup(cls, backup_id: str) -> Dict[str, Any]:
        """Recompute the archive's SHA-256 and compare to the recorded value."""
        index = cls._load_index()
        entry = index.get(backup_id)
        if not entry:
            return {"success": False, "error": f"No backup with id '{backup_id}'."}
        path = Path(entry["path"])
        if not path.exists():
            return {"success": False, "error": f"Backup archive missing: '{path}'"}
        try:
            current = cls._sha256(path)
        except Exception as e:
            return {"success": False, "error": f"Could not hash archive: {e}"}
        ok = current == entry.get("sha256")
        return {
            "success": True,
            "backup_id": backup_id,
            "intact": ok,
            "recorded_sha256": entry.get("sha256"),
            "current_sha256": current,
        }

    # ── restore (Level 2) ───────────────────────────────────────────────────
    @classmethod
    def restore_backup(cls, backup_id: str, dest_dir: str, overwrite: bool = False) -> Dict[str, Any]:
        """Non-overwriting restore. Overwrite requires a distinct Level-3 action."""
        if overwrite:
            return {"success": False, "requires_approval": True, "required_action": "restore_backup_overwrite", "error": "Overwrite restore is a separate Level-3 action."}
        return cls._restore_backup_impl(backup_id, dest_dir, overwrite=False)

    @classmethod
    def restore_backup_overwrite(cls, backup_id: str, dest_dir: str, pre_snapshot: bool = False) -> Dict[str, Any]:
        """Level-3 overwriting restore, optionally snapshotted first.

        With pre_snapshot=True, every existing file the archive will overwrite is
        first captured into a verified backup (arcnames match the archive member
        paths, so restoring the snapshot reproduces the pre-overwrite state). If
        the snapshot cannot be created, the overwrite is refused with zero side
        effects — destruction never happens without its recovery evidence.
        """
        return cls._restore_backup_impl(backup_id, dest_dir, overwrite=True, pre_snapshot=pre_snapshot)

    @classmethod
    def _create_preoverwrite_snapshot(cls, backup_id: str, dest: Path, member_names: List[str]) -> Dict[str, Any]:
        """Snapshot exactly the existing files the archive will overwrite."""
        existing: List[Path] = []
        for name in member_names:
            target = (dest / name)
            try:
                if target.is_file():
                    existing.append(target)
            except OSError:
                return {"created": False, "error": f"Could not observe destination file '{name}'"}
        if not existing:
            return {"created": False, "file_count": 0, "reason": "no existing files would be overwritten"}
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        snapshot_id = f"{stamp}_pre-overwrite_{backup_id}"
        zip_path = cls.BACKUP_DIR / f"{snapshot_id}.zip"
        cls.ensure_dir()
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for target in existing:
                    # Arcname = member-relative path: restoring this snapshot
                    # reproduces the exact pre-overwrite layout of the destination.
                    zf.write(target, arcname=target.relative_to(dest))
        except Exception as e:
            zip_path.unlink(missing_ok=True)
            return {"created": False, "error": f"Pre-overwrite snapshot failed: {e}"}
        size = zip_path.stat().st_size
        sha = cls._sha256(zip_path)
        entry = {
            "id": snapshot_id,
            "name": f"pre-overwrite-{backup_id}",
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "sources": [str(dest)],
            "file_count": len(existing),
            "size_bytes": size,
            "sha256": sha,
            "path": str(zip_path),
            "pre_overwrite_for": backup_id,
            "dest_dir": str(dest),
            "overwrote_files": [str(t.relative_to(dest)) for t in existing],
        }
        index = cls._load_index()
        index[snapshot_id] = entry
        cls._save_index(index)
        audit_logger.info(f"Pre-overwrite snapshot {snapshot_id} captured {len(existing)} files before restoring {backup_id}")
        return {"created": True, "backup_id": snapshot_id, "file_count": len(existing), "sha256": sha, "overwrote_files": entry["overwrote_files"]}

    @classmethod
    def _restore_backup_impl(cls, backup_id: str, dest_dir: str, overwrite: bool, pre_snapshot: bool = False) -> Dict[str, Any]:
        """Extract a verified backup after the caller selected the proper safety action."""
        index = cls._load_index()
        entry = index.get(backup_id)
        if not entry:
            return {"success": False, "error": f"No backup with id '{backup_id}'."}
        path = Path(entry["path"])
        if not path.exists():
            return {"success": False, "error": f"Backup archive missing: '{path}'"}

        dest = Path(dest_dir)
        if not dest.is_absolute():
            dest = settings.BASE_DIR / dest

        if dest.exists() and any(dest.iterdir()) and not overwrite:
            return {"success": False, "error": f"Destination '{dest}' is not empty; pass overwrite=True to proceed."}

        verification = cls.verify_backup(backup_id)
        if not verification.get("success") or not verification.get("intact"):
            return {"success": False, "error": "Backup integrity verification failed before restore", "verification": verification}
        try:
            dest.mkdir(parents=True, exist_ok=True)
            root = dest.resolve()
            with zipfile.ZipFile(path) as zf:
                if zf.testzip() is not None:
                    return {"success": False, "error": "Backup archive contains a corrupt member"}
                members = zf.infolist()
                for member in members:
                    target = (root / member.filename).resolve()
                    if target != root and root not in target.parents:
                        return {"success": False, "error": f"Unsafe archive path rejected: {member.filename}"}
                # Optional pre-overwrite snapshot: capture exactly the existing
                # files this extraction will replace. Failure refuses the
                # overwrite entirely (destination untouched).
                snapshot_result: Optional[Dict[str, Any]] = None
                if overwrite and pre_snapshot:
                    snapshot_result = cls._create_preoverwrite_snapshot(
                        backup_id, root, [m.filename for m in members if not m.is_dir()]
                    )
                    if snapshot_result.get("error"):
                        return {
                            "success": False,
                            "refused": True,
                            "side_effects": False,
                            "error": "Pre-overwrite snapshot failed; overwrite refused without side effects",
                            "detail": snapshot_result["error"],
                        }
                zf.extractall(dest)
            restored = [str((root / member.filename).resolve()) for member in members if not member.is_dir()]
            observed = all(Path(item).is_file() for item in restored)
            audit_logger.info(f"Restored backup {backup_id} → {dest}")
            result = {
                "success": observed, "backup_id": backup_id, "restored_to": str(dest),
                "file_count": len(restored), "restored_files": restored,
                "archive_sha256": verification.get("current_sha256"),
                "environment_verified": observed, "side_effects": bool(restored),
            }
            if snapshot_result is not None:
                result["pre_overwrite_snapshot"] = snapshot_result
                if snapshot_result.get("created"):
                    result["rollback_supported"] = True
                    result["rollback_backup_id"] = snapshot_result["backup_id"]
                    result["rollback_reason"] = (
                        f"Pre-overwrite snapshot {snapshot_result['backup_id']} can restore the overwritten files; "
                        "restoring it is a separate action requiring fresh approval."
                    )
                else:
                    result["rollback_supported"] = False
                    result["rollback_reason"] = f"Restore may overwrite or combine with pre-existing destination content; automatic rollback is unsafe (snapshot: {snapshot_result.get('reason')})."
            else:
                result["rollback_supported"] = False
                result["rollback_reason"] = "Restore may overwrite or combine with pre-existing destination content; automatic rollback is unsafe."
            return result
        except Exception as e:
            app_logger.warning(f"Restore failed: {e}")
            return {"success": False, "error": f"Restore failed: {e}"}

    # ── delete (Level 3) ────────────────────────────────────────────────────
    @classmethod
    def delete_backup(cls, backup_id: str) -> Dict[str, Any]:
        index = cls._load_index()
        entry = index.get(backup_id)
        if not entry:
            return {"success": False, "error": f"No backup with id '{backup_id}'."}
        path = Path(entry["path"])
        try:
            if path.exists():
                path.unlink()
            index.pop(backup_id, None)
            cls._save_index(index)
            audit_logger.info(f"Deleted backup {backup_id}")
            return {"success": True, "backup_id": backup_id}
        except Exception as e:
            app_logger.warning(f"Delete backup failed: {e}")
            return {"success": False, "error": f"Delete failed: {e}"}

    # ── helpers ─────────────────────────────────────────────────────────────
    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
