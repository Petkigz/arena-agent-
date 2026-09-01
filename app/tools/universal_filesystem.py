import os
import re
import shutil
import string
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

    _INDEX_TTL_S = 1800.0  # cache trusted for fast-path hits up to 30 min

    # ------------------------------------------------------------------
    # P0 bottleneck #12: explicit search scopes. The old default
    # (root_dir=None -> Arena's BASE_DIR) made 'find my song called Kaba'
    # search the AGENT'S OWN INSTALL DIRECTORY — wrong semantics for a
    # personal desktop assistant. Scopes are the vocabulary now; the
    # smallest sensible one is inferred from the query, and a narrow
    # scope that finds NOTHING escalates to all_user_files instead of
    # fabricating absence.
    # ------------------------------------------------------------------
    KNOWN_SCOPES = (
        "workspace", "home", "desktop", "documents", "downloads",
        "music", "pictures", "videos", "all_user_files",
    )

    # Location-EXPLICIT patterns only. Content-type words ('song', 'photo',
    # 'document') describe WHAT a file is, never WHERE it is — a song can
    # live in Downloads, on the Desktop, or on another drive, so they must
    # NOT narrow the search. A scope is inferred only when the query names a
    # place: 'in my music folder', 'the installer in downloads',
    # 'notes on the desktop', 'your workspace'.
    _LOCATION_SCOPE_PATTERNS = {
        "workspace": (r"\b(your|arena'?s?)\s+(workspace|files|folder|directory)\b",
                      r"\bworkspace\b"),
        "desktop": (r"\b(on|in|under|inside)\s+(the\s+|my\s+)?desktop\b",
                    r"\bdesktop\s+(folder|directory)\b"),
        "downloads": (r"\b(in|under|inside)\s+(my\s+|the\s+)?downloads?\b",
                      r"\bdownloads?\s+(folder|directory)\b"),
        "documents": (r"\b(in|under|inside)\s+(my\s+|the\s+)?documents?\s+(folder|directory)\b",
                      r"\bdocuments?\s+(folder|directory)\b"),
        "music": (r"\b(in|under|inside)\s+(my\s+|the\s+)?music\b",
                  r"\bmusic\s+(folder|directory)\b"),
        "pictures": (r"\b(in|under|inside)\s+(my\s+|the\s+)?pictures?\s+(folder|directory)\b",
                     r"\bpictures?\s+(folder|directory)\b"),
        "videos": (r"\b(in|under|inside)\s+(my\s+|the\s+)?videos?\s+(folder|directory)\b",
                   r"\bvideos?\s+(folder|directory)\b"),
        "home": (r"\bhome\s+(directory|folder)\b", r"\bin\s+my\s+home\b"),
    }

    @classmethod
    def resolve_scope_roots(cls, scope: str) -> List[Path]:
        """Resolve a named scope to concrete search roots.

        all_user_files = the home tree plus every other fixed drive on
        Windows (the owner's music does not always live under the profile —
        live incident: 'songs called kaba' on another drive while the agent
        walked only the profile and reported nothing)."""
        s = str(scope or "").strip().lower()
        home = Path.home()
        if s == "workspace":
            return [Path(settings.BASE_DIR)]
        if s == "home":
            return [home]
        if s == "all_user_files":
            roots = [home]
            if sys.platform.startswith("win"):
                home_drive = os.path.splitdrive(str(home))[0].upper()
                for letter in string.ascii_uppercase:
                    drive = f"{letter}:\\"
                    if f"{letter}:" == home_drive:
                        continue
                    if os.path.exists(drive):
                        roots.append(Path(drive))
            return roots
        folder_map = {
            "desktop": "Desktop", "documents": "Documents",
            "downloads": "Downloads", "music": "Music",
            "pictures": "Pictures", "videos": "Videos",
        }
        if s in folder_map:
            target = home / folder_map[s]
            if target.exists():
                return [target]
            # Honest fallback: the canonical folder is absent on this machine
            # (localized or redirected profile). Search the home superset
            # rather than an empty scope — a superset can only find MORE,
            # never fabricate a miss.
            app_logger.info(
                f"Search scope '{s}': {target} does not exist; falling back to the home directory.")
            return [home]
        app_logger.warning(f"Unknown search scope '{scope}'; using all_user_files.")
        return cls.resolve_scope_roots("all_user_files")

    @classmethod
    def infer_scope_from_query(cls, query: str) -> str:
        """Infer a scope ONLY from explicit location phrases.

        'find my song called kaba' -> all_user_files (the song can be
        anywhere on the PC — 'song' is a content type, not a place).
        'find kaba in my music folder' -> music. Default: all_user_files —
        a personal assistant searches the user's whole machine, not one
        folder and not its own install directory."""
        text = str(query or "").lower()
        for scope in ("workspace", "desktop", "downloads", "documents",
                      "music", "pictures", "videos", "home"):
            for pattern in cls._LOCATION_SCOPE_PATTERNS[scope]:
                if re.search(pattern, text):
                    return scope
        return "all_user_files"

    @classmethod
    def search_filesystem(
        cls,
        query: str,
        root_dir: Optional[Any] = None,
        max_results: int = 20,
        timeout_s: float = 15.0,
        scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Scoped filename search for a personal desktop assistant (P0 #12).

        Scope resolution, in order:
          1. explicit ``root_dir`` (path or list) — callers that know exactly
             where to look;
          2. explicit ``scope`` — one of KNOWN_SCOPES (workspace, home,
             desktop, documents, downloads, music, pictures, videos,
             all_user_files), the planner's smallest-sensible-scope choice;
          3. inferred ONLY from explicit location phrases ('find kaba in my
             music folder' -> music) — content-type words ('song', 'pdf')
             never narrow: a file can live anywhere on the PC;
          4. otherwise all_user_files — the USER'S files, never the agent's
             own install directory (the old root_dir=None default searched
             Arena's BASE_DIR).

        A narrow scope that finds NOTHING escalates once to all_user_files:
        a miss in ~/Music is not proof the song doesn't exist elsewhere, and
        this search must never fabricate absence. Escalated entries carry
        ``scope_escalated``; every scoped result carries ``scope``.

        Everything (voidtools) reads the NTFS master file table and sees every
        file on every drive instantly; this tool WALKS the tree — but keeps a
        persistent filename index (data/file_index.db) so repeat searches are
        instant. Index hits are existence-verified; misses always fall through
        to a live walk, so the index can never fabricate absence. Directories
        match as well as files; system/junk directories are pruned; a
        ``timeout_s`` budget bounds huge trees (a timeout returns partial
        results, never hangs). When nothing matches exactly, a typo-tolerant
        fuzzy pass kicks in (query 'ordinaryr', file 'Ordinary'), scored per
        filename token so 'Artist - Title.ext' matches the bare title.
        """
        query_raw = (query or "").strip()
        if not query_raw:
            return []

        scope_resolved: Optional[str] = None
        if root_dir is not None:
            if isinstance(root_dir, (list, tuple)):
                roots = [Path(r) for r in root_dir if str(r or "").strip()]
            else:
                roots = [Path(str(root_dir))]
        else:
            if scope is None:
                scope = cls.infer_scope_from_query(query_raw)
            elif scope not in cls.KNOWN_SCOPES:
                app_logger.warning(
                    f"Unknown search scope '{scope}'; inferring from the query instead.")
                scope = cls.infer_scope_from_query(query_raw)
            scope_resolved = scope
            roots = cls.resolve_scope_roots(scope)

        def _tag(entries: List[Dict[str, Any]], escalated: bool = False) -> List[Dict[str, Any]]:
            if scope_resolved is not None or escalated:
                for e in entries:
                    e["scope"] = scope_resolved or "all_user_files"
                    if escalated:
                        e["scope_escalated"] = True
            return entries

        results = cls._search_roots(query_raw, roots, max_results, timeout_s)

        # Never fabricate absence from a narrow scope (P0 #12): a miss in
        # ~/Music is not proof the song isn't on the Desktop or another
        # drive. Escalate once to all_user_files before reporting nothing.
        if (
            not results
            and scope_resolved is not None
            and scope_resolved not in ("all_user_files", "home")
        ):
            esc_roots = cls.resolve_scope_roots("all_user_files")
            if {str(r) for r in esc_roots} - {str(r) for r in roots}:
                app_logger.info(
                    f"Scope '{scope_resolved}' found no matches for '{query_raw}'; "
                    "escalating to all_user_files before reporting absence.")
                results = cls._search_roots(query_raw, esc_roots, max_results, timeout_s)
                return _tag(results, escalated=True)
        # Same rule for an EXPLICIT root_dir (D7 live 2026-09-01): the
        # agent searched the Documents folder while the marker sat in the
        # home root — one wrong root must not hide a file that exists in
        # the user's scope. Escalate once before reporting nothing.
        if not results and root_dir is not None:
            esc_roots = cls.resolve_scope_roots("all_user_files")
            if {str(r) for r in esc_roots} - {str(r) for r in roots}:
                app_logger.info(
                    f"Explicit root {roots} found no matches for "
                    f"'{query_raw}'; escalating to all_user_files before "
                    "reporting absence.")
                results = cls._search_roots(query_raw, esc_roots, max_results, timeout_s)
                return _tag(results, escalated=True)
        return _tag(results)

    @classmethod
    def _search_roots(
        cls,
        query_raw: str,
        roots: List[Path],
        max_results: int = 20,
        timeout_s: float = 15.0,
    ) -> List[Dict[str, Any]]:
        """Core walk: exact substring matches first, fuzzy fallback, bounded
        by a timeout, accelerated by the existence-verified file index."""
        import difflib
        import re as _re
        import time as _time

        query_lower = query_raw.lower()
        query_norm = _re.sub(r"[^a-z0-9]+", "", query_lower)
        query_tokens = [t for t in _re.split(r"[^a-z0-9]+", query_lower) if len(t) >= 3]

        # ── Indexed-provider fast path (P0 review #11) ─────────────────────
        # Everything-style indexed search answers over EVERY drive instantly
        # (live NTFS MFT); the Python walker stays as the fallback. Contract:
        # None -> no provider, fall through; entries -> walker-equivalent,
        # existence-verified, scoped, source-tagged; [] -> the live index
        # says no filename contains the query — fall through so the
        # typo-tolerant fuzzy pass can still help the miss.
        try:
            from app.tools.indexed_search import provider_search
            indexed = provider_search(query_raw, roots, limit=max_results)
            if indexed:
                return indexed[:max_results]
        except Exception as exc:
            app_logger.info(f"Indexed search fast path skipped ({exc}); using the walker.")

        # ── Index fast path ────────────────────────────────────────────────
        # All roots freshly indexed? Answer from the cache — but VERIFY each
        # hit still exists, so deletions/moves can never be reported stale.
        try:
            from app.tools.file_index import get_file_index
            index = get_file_index()
            root_strs = [str(r) for r in roots]
            if all(index.root_age(rs) < cls._INDEX_TTL_S for rs in root_strs):
                cached = index.lookup_exact(query_raw, root_strs, limit=max_results * 2)
                verified = [m for m in cached if os.path.exists(m["file_path"])]
                if verified:
                    try:
                        p = Path(verified[0]["file_path"])
                        verified[0]["size_bytes"] = p.stat().st_size if p.is_file() else 0
                        verified[0]["extension"] = p.suffix.lower()
                    except OSError:
                        pass
                    for m in verified[1:]:
                        m["size_bytes"] = 0
                        m["extension"] = Path(m["file_path"]).suffix.lower()
                    index.stats["hits"] += 1
                    app_logger.info(
                        f"File index cache hit: {len(verified[:max_results])} verified match(es) "
                        f"for '{query_raw}' across {len(root_strs)} indexed root(s)."
                    )
                    return verified[:max_results]
                index.stats["misses"] += 1
        except Exception as exc:
            app_logger.warning(f"File index fast path skipped ({exc}); using live walk.")

        exact: List[Dict[str, Any]] = []
        fuzzy: List[Dict[str, Any]] = []
        deadline = _time.monotonic() + float(timeout_s)

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
            'ordinary' token, not the whole artist-prefixed string.
            Adjacent transpositions ('kbaa' for 'kaba') get an anagram boost,
            and word ORDER is ignored via a token-set comparison
            ('ordinary by alex warren' vs 'Alex Warren - Ordinary.mp3')."""
            norm = _re.sub(r"[^a-z0-9]+", "", name.lower())
            best = difflib.SequenceMatcher(None, query_norm, norm).ratio()
            if sorted(query_norm) == sorted(norm):
                best = max(best, 1.0)
            name_tokens = [t for t in _re.split(r"[^a-z0-9]+", name.lower()) if len(t) >= 3]
            for t in name_tokens:
                best = max(
                    best,
                    difflib.SequenceMatcher(None, query_norm, t).ratio(),
                )
                if sorted(query_norm) == sorted(t):
                    best = max(best, 1.0)
            # Token-set ratio: same words in a different order still match —
            # difflib alone scores 'ordinarybyalexwarren' vs
            # 'alexwarrenordinary' at 0.54 because the shared blocks sit on
            # opposite sides.
            if len(query_tokens) >= 2:
                joined_q = " ".join(sorted(query_tokens))
                joined_n = " ".join(sorted(name_tokens))
                best = max(
                    best,
                    difflib.SequenceMatcher(None, joined_q, joined_n).ratio(),
                )
                # Subset direction: the query's words all appearing in the
                # name (plus filler like 'by') is a strong signal.
                if set(query_tokens) <= set(name_tokens):
                    best = max(best, 0.95)
            return best

        # Cheap fuzzy prefilter: the query's characters must (mostly) be
        # present in the name. Position-free on purpose — 'orinary' (typo
        # dropped the 'd' in 'ordinary') shares every remaining letter but
        # its FIRST THREE CHARS diverge, which a positional prefilter
        # ('ori' in name) would wrongly reject.
        q_chars = set(query_norm)
        q_need = max(3, len(q_chars) - 2)

        def _prefilter(name_lower: str) -> bool:
            return len(q_chars & set(name_lower)) >= q_need

        record_index = False
        try:
            from app.tools.file_index import get_file_index
            index = get_file_index()
            record_index = True
            index.stats["walks"] += 1
        except Exception:
            record_index = False

        for search_root in roots:
            if not search_root.exists():
                continue
            if _time.monotonic() > deadline:
                break
            root_str = str(search_root)
            index_batch: List[tuple] = []
            root_complete = True
            if record_index:
                try:
                    index.begin_root(root_str)
                except Exception:
                    record_index = False

            def _flush_index() -> None:
                if record_index and index_batch:
                    try:
                        index.add_entries(root_str, index_batch)
                    except Exception:
                        pass
                    index_batch.clear()

            try:
                walk = os.walk(search_root)
                for root, dirs, files in walk:
                    if _time.monotonic() > deadline:
                        root_complete = False
                        break
                    # Prune system/junk directories in-place (os.walk reuses
                    # the mutated list).
                    dirs[:] = [d for d in dirs if d.lower() not in cls._SKIP_DIRS]
                    for d in dirs:
                        dl = d.lower()
                        index_batch.append((d, str(Path(root) / d), 1))
                        if query_lower in dl:
                            exact.append(_entry(Path(root) / d, d, True))
                        elif (
                            not exact
                            and query_norm
                            and len(fuzzy) < 30
                            and _prefilter(dl)
                            and _fuzzy_score(d) >= 0.78
                        ):
                            e = _entry(Path(root) / d, d, True)
                            e["match"] = "fuzzy"
                            e["fuzzy_score"] = round(_fuzzy_score(d), 2)
                            fuzzy.append(e)
                    for f in files:
                        fl = f.lower()
                        index_batch.append((f, str(Path(root) / f), 0))
                        if query_lower in fl:
                            exact.append(_entry(Path(root) / f, f, False))
                        elif (
                            not exact
                            and query_norm
                            and len(fuzzy) < 30
                            and _prefilter(fl)
                            and _fuzzy_score(f) >= 0.78
                        ):
                            e = _entry(Path(root) / f, f, False)
                            e["match"] = "fuzzy"
                            e["fuzzy_score"] = round(_fuzzy_score(f), 2)
                            fuzzy.append(e)
                    if len(exact) >= max_results:
                        break
                    if len(index_batch) >= 4096:
                        _flush_index()
                _flush_index()
                if record_index:
                    # An exact-match early break stops the walk early: the
                    # index for this root is partial (still useful — it is
                    # only ever an accelerator).
                    index.finish_root(root_str, complete=root_complete and len(exact) < max_results)
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
