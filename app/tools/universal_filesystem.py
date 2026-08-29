import os
import shutil
import sys
import zipfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

class UniversalFilesystem:
    @staticmethod
    def _sha256(path: Path) -> str:
        import hashlib
        digest=hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def copy_file_verified(cls, source_path: str, destination_path: str) -> Dict[str, Any]:
        src,dst=Path(source_path),Path(destination_path)
        if not src.is_file():return {"success":False,"error":"Source file not found"}
        if dst.exists():return {"success":False,"error":"Destination already exists; refusing overwrite"}
        before=cls._sha256(src)
        try:dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        except Exception as exc:return {"success":False,"error":str(exc)}
        after=cls._sha256(dst) if dst.is_file() else None;verified=before==after
        return {"success":verified,"source_path":str(src),"destination_path":str(dst),"source_sha256":before,"destination_sha256":after,"environment_verified":verified,"side_effects":dst.exists(),"rollback_path":str(dst),"rollback_sha256":after}

    @classmethod
    def remove_verified_copy(cls, file_path: str, expected_sha256: str) -> Dict[str, Any]:
        path=Path(file_path)
        if not path.is_file():return {"success":False,"error":"Rollback target is missing"}
        actual=cls._sha256(path)
        if actual!=expected_sha256:return {"success":False,"error":"Rollback target hash changed; refusing deletion","actual_sha256":actual}
        path.unlink();verified=not path.exists()
        return {"success":verified,"removed_path":str(path),"expected_sha256":expected_sha256,"environment_verified":verified,"side_effects":verified,"rollback_supported":False}

    @classmethod
    def trash_files(cls, file_paths: List[str], trash_root: Optional[str] = None) -> Dict[str, Any]:
        """REVERSIBLE delete: move files to a recoverable trash area.

        'delete the file called X' is a Level-3 action the owner must approve;
        when approved it still must not be irreversible on day one. Files are
        moved (not unlinked) into <home>/.arena_trash/<timestamp>/ with their
        full original path recorded so recovery is trivial and auditable.
        Only paths under the user's home directory are accepted — system
        locations are refused outright.
        """
        import time
        home = Path.home().resolve()
        trash_base = Path(trash_root or home / ".arena_trash")
        if not file_paths:
            return {"success": False, "error": "No file paths supplied"}
        if len(file_paths) > 50:
            return {"success": False, "error": f"Refusing to trash {len(file_paths)} paths at once (limit 50)"}
        session_dir = trash_base / time.strftime("%Y%m%d-%H%M%S")
        moved: List[Dict[str, str]] = []
        errors: List[str] = []
        for raw in file_paths:
            try:
                src = Path(raw).expanduser().resolve()
                if not src.exists():
                    errors.append(f"Not found: {src}")
                    continue
                if home not in src.parents:
                    errors.append(f"Outside home directory, refused: {src}")
                    continue
                dst = session_dir / src.relative_to(home)
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    errors.append(f"Already in trash: {dst}")
                    continue
                shutil.move(str(src), str(dst))
                moved.append({"original": str(src), "trash_path": str(dst)})
                audit_logger.info(f"Trashed (reversible delete) '{src}' -> '{dst}'")
            except Exception as exc:
                errors.append(f"{raw}: {exc}")
        return {
            "success": bool(moved) and not errors,
            "trashed": moved,
            "trash_session": str(session_dir),
            "errors": errors,
            "environment_verified": all(not Path(m["original"]).exists() for m in moved),
            "side_effects": bool(moved),
            "reversible": True,
            "message": (
                f"Moved {len(moved)} file(s) to {session_dir} — recoverable."
                if moved else "Nothing was deleted."
            ),
        }

    # Directories never worth walking for user-file questions (huge, noisy,
    # or cyclic junction bait). Pruned by NAME anywhere in the tree.
    _SKIP_DIRS = {
        "$recycle.bin", "$windows.~bt", "$getcurrent", "$winreagent",
        "system volume information", "windows", "program files",
        "program files (x86)", "programdata", "appdata", "node_modules",
        ".git", ".venv", "__pycache__", "site-packages", "perflogs",
        "msocache", "recovery", "onedrivetemp", "dist-info",
    }

    @classmethod
    def search_filesystem(
        cls,
        query: str,
        root_dir: Optional[Any] = None,
        max_results: int = 20,
        timeout_s: float = 15.0,
    ) -> List[Dict[str, Any]]:
        """Live (non-indexed) filename search: exact substring matches first,
        typo-tolerant fuzzy matches as a fallback.

        Everything (voidtools) reads the NTFS master file table and sees every
        file on every drive instantly; this tool WALKS the tree, so it is
        scoped and budgeted instead:

          * ``root_dir`` may be a single path or a LIST of paths (None → the
            app base directory). Directories are matched as well as files —
            an album folder named 'Kaba' is a hit, not a miss.
          * System/junk directories are pruned; a ``timeout_s`` budget bounds
            huge trees (a timeout returns partial results, never hangs).
          * When nothing matches exactly, a fuzzy pass kicks in (the owner
            asked for 'ordinaryr' and the file is 'Ordinary'): candidates are
            scored per filename token so 'Artist - Title.ext' matches the
            bare title. Fuzzy entries carry ``fuzzy_match``/``fuzzy_score``.
        """
        import difflib
        import re as _re
        import time as _time

        query_raw = (query or "").strip()
        if not query_raw:
            return []
        query_lower = query_raw.lower()
        query_norm = _re.sub(r"[^a-z0-9]+", "", query_lower)

        if root_dir is None:
            roots = [Path(settings.BASE_DIR)]
        elif isinstance(root_dir, (list, tuple)):
            roots = [Path(r) for r in root_dir if str(r or "").strip()]
        else:
            roots = [Path(str(root_dir))]

        exact: List[Dict[str, Any]] = []
        fuzzy: List[Dict[str, Any]] = []
        deadline = _time.monotonic() + float(timeout_s)
        q_head = query_norm[:3]

        def _entry(path: Path, name: str, is_dir: bool) -> Dict[str, Any]:
            try:
                size = 0 if is_dir else path.stat().st_size
            except OSError:
                size = 0
            return {
                "file_name": name,
                "file_path": str(path),
                "size_bytes": size,
                "extension": "" if is_dir else path.suffix.lower(),
                "type": "directory" if is_dir else "file",
                "match": "exact",
            }

        def _fuzzy_score(name: str) -> float:
            """Best similarity between the query and the name / its tokens —
            'ordinaryr' vs 'Alex Warren - Ordinary.mp3' must score on the
            'ordinary' token, not the whole artist-prefixed string."""
            norm = _re.sub(r"[^a-z0-9]+", "", name.lower())
            best = difflib.SequenceMatcher(None, query_norm, norm).ratio()
            for token in _re.split(r"[^a-z0-9]+", name.lower()):
                t = token.strip()
                if len(t) >= 3:
                    best = max(
                        best,
                        difflib.SequenceMatcher(None, query_norm, t).ratio(),
                    )
            return best

        for search_root in roots:
            if not search_root.exists():
                continue
            if _time.monotonic() > deadline:
                break
            try:
                walk = os.walk(search_root)
                for root, dirs, files in walk:
                    if _time.monotonic() > deadline:
                        break
                    # Prune system/junk directories in-place (os.walk reuses
                    # the mutated list).
                    dirs[:] = [d for d in dirs if d.lower() not in cls._SKIP_DIRS]
                    for d in dirs:
                        dl = d.lower()
                        if query_lower in dl:
                            exact.append(_entry(Path(root) / d, d, True))
                        elif (
                            not exact
                            and query_norm
                            and len(fuzzy) < 30
                            and (q_head and (q_head in dl or dl[:3] in query_norm))
                            and _fuzzy_score(d) >= 0.78
                        ):
                            e = _entry(Path(root) / d, d, True)
                            e["match"] = "fuzzy"
                            e["fuzzy_score"] = round(_fuzzy_score(d), 2)
                            fuzzy.append(e)
                    for f in files:
                        fl = f.lower()
                        if query_lower in fl:
                            exact.append(_entry(Path(root) / f, f, False))
                        elif (
                            not exact
                            and query_norm
                            and len(fuzzy) < 30
                            and (q_head and (q_head in fl or fl[:3] in query_norm))
                            and _fuzzy_score(f) >= 0.78
                        ):
                            e = _entry(Path(root) / f, f, False)
                            e["match"] = "fuzzy"
                            e["fuzzy_score"] = round(_fuzzy_score(f), 2)
                            fuzzy.append(e)
                    if len(exact) >= max_results:
                        break
            except Exception as e:
                app_logger.warning(f"Error during filesystem search: {e}")

        if exact:
            return exact[:max_results]
        # No exact hits anywhere → fuzzy candidates are the answer the owner
        # needs (typo'd title). Best scores first.
        fuzzy.sort(key=lambda m: -(m.get("fuzzy_score") or 0))
        for m in fuzzy[:max_results]:
            m["fuzzy_match"] = True
        return fuzzy[:max_results]

    @classmethod
    @classmethod
    def list_directory(cls, directories: List[Dict[str, Any]], include_hidden: bool = False) -> Dict[str, Any]:
        """Read-only listing of directory entries (Level-0 observation).

        Each item of `directories` is {"path": "..."}; missing directories are
        reported per-entry, never fatal. Used for evidence-grounded answers
        about host state (e.g. counting desktop icons).
        """
        listings = []
        errors = []
        for item in directories or []:
            raw = item.get("path") if isinstance(item, dict) else str(item)
            path = Path(str(raw or "")).expanduser()
            if not path.is_dir():
                errors.append({"path": str(raw), "error": "not a directory"})
                continue
            try:
                entries = sorted(
                    e.name for e in path.iterdir()
                    if include_hidden or not e.name.startswith(".")
                )
            except Exception as exc:
                errors.append({"path": str(path), "error": str(exc)})
                continue
            listings.append({"directory": str(path), "count": len(entries), "entries": entries[:200]})
        return {
            "success": bool(listings) and not errors,
            "listings": listings,
            "errors": errors,
            "side_effects": False,
            "note": "Read-only filesystem observation.",
        }

    @classmethod
    def rename_or_move(cls, source_path_str: str, destination_path_str: str) -> Dict[str, Any]:
        """
        Renames or moves any file or folder across the filesystem.
        """
        src = Path(source_path_str)
        dst = Path(destination_path_str)

        if not src.exists():
            return {"success": False, "error": f"Source file/folder not found: '{src}'"}
        if dst.exists():
            return {"success": False, "error": f"Destination already exists; refusing overwrite: '{dst}'"}

        try:
            import hashlib
            source_sha256 = hashlib.sha256(src.read_bytes()).hexdigest() if src.is_file() else None
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            verified = dst.exists() and not src.exists()
            destination_sha256 = hashlib.sha256(dst.read_bytes()).hexdigest() if dst.is_file() else None
            if source_sha256 and destination_sha256 != source_sha256:
                return {"success": False, "error": "Move completed but content hash verification failed", "side_effects": True}
            audit_logger.info(f"Moved/Renamed '{src.name}' -> '{dst.name}'")
            return {
                "success": verified,
                "old_path": str(src),
                "new_path": str(dst),
                "source_sha256": source_sha256,
                "destination_sha256": destination_sha256,
                "environment_verified": verified,
                "side_effects": verified,
                "rollback_source": str(dst),
                "rollback_destination": str(src),
                "message": f"Successfully moved '{src.name}' to '{dst.name}'."
            }
        except Exception as e:
            app_logger.error(f"Error moving file: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def compress_zip(cls, source_paths: List[str], output_zip_path_str: str) -> Dict[str, Any]:
        """
        Compresses files or folders into a ZIP archive.
        """
        zip_path = Path(output_zip_path_str)
        sources=[Path(item) for item in (source_paths or [])]
        if not sources:return {"success":False,"error":"At least one source path is required"}
        missing=[str(path) for path in sources if not path.exists()]
        if missing:return {"success":False,"error":"One or more sources are missing","missing":missing}
        if zip_path.exists():return {"success":False,"error":"Output archive already exists; refusing overwrite"}
        manifest=[]
        try:
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for p in sources:
                    if p.is_file():
                        zipf.write(p, p.name);manifest.append({"path":str(p),"sha256":cls._sha256(p)})
                    elif p.is_dir():
                        for root, _, files in os.walk(p):
                            for f in files:
                                file_p = Path(root) / f
                                zipf.write(file_p, file_p.relative_to(p.parent));manifest.append({"path":str(file_p),"sha256":cls._sha256(file_p)})
            with zipfile.ZipFile(zip_path,'r') as archive:bad=archive.testzip()
            archive_hash=cls._sha256(zip_path);verified=bad is None and bool(manifest)
            audit_logger.info(f"Compressed {len(source_paths)} items into ZIP archive: {zip_path.name}")
            return {
                "success": verified,"zip_path": str(zip_path),"zip_name": zip_path.name,
                "size_bytes": zip_path.stat().st_size,"archive_sha256":archive_hash,
                "source_manifest":manifest,"environment_verified":verified,"side_effects":True,
                "rollback_path":str(zip_path),"rollback_sha256":archive_hash
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def resize_image(cls, image_path_str: str, target_width: int, target_height: int) -> Dict[str, Any]:
        """
        Resizes an image file (.jpg, .png, .webp) to specified width and height.
        """
        img_path = Path(image_path_str)
        if not img_path.exists():
            return {"success": False, "error": f"Image file not found: '{img_path}'"}

        try:
            from PIL import Image
            img = Image.open(img_path)
            resized_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            output_path = img_path.parent / f"resized_{img_path.name}"
            resized_img.save(output_path)

            audit_logger.info(f"Resized image '{img_path.name}' to {target_width}x{target_height}")
            return {
                "success": True,
                "original_path": str(img_path),
                "resized_path": str(output_path),
                "new_width": target_width,
                "new_height": target_height
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def play_media_file(cls, media_path_str: str) -> Dict[str, Any]:
        """
        Launches default OS media player to play audio or video files (.mp3, .wav, .mp4, .mkv).
        """
        media_path = Path(media_path_str)
        if not media_path.exists():
            return {"success": False, "error": f"Media file not found: '{media_path}'"}

        try:
            if os.name == 'nt':
                os.startfile(str(media_path))
            elif sys.platform == 'darwin':
                # `open` prints its failure and exits non-zero; capture and
                # check it instead of claiming success on a blind spawn.
                completed = subprocess.run(['open', str(media_path)], capture_output=True, text=True, timeout=30)
                if completed.returncode != 0:
                    detail = (completed.stderr or completed.stdout or "").strip()[:200]
                    return {"success": False, "file_name": media_path.name,
                            "error": f"macOS 'open' failed (exit {completed.returncode}): {detail}"}
            else:
                completed = subprocess.run(['xdg-open', str(media_path)], capture_output=True, text=True, timeout=30)
                if completed.returncode != 0:
                    detail = (completed.stderr or completed.stdout or "").strip()[:200]
                    return {"success": False, "file_name": media_path.name,
                            "error": f"xdg-open failed (exit {completed.returncode}): {detail}"}

            audit_logger.info(f"Launched media playback for '{media_path.name}'")
            return {"success": True, "file_name": media_path.name, "message": f"Playing media file '{media_path.name}'."}
        except subprocess.TimeoutExpired:
            return {"success": False, "file_name": media_path.name, "error": "Media player launch timed out."}
        except Exception as e:
            return {"success": False, "error": str(e)}
