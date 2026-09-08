import os
import shutil
import platform
import subprocess
from typing import Dict, Any, List, Optional
from app.database import db
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

# Windows shell failures print human-readable text to the console ('The system
# cannot find the file X', "'foo' is not recognized as an internal or external
# command") instead of raising an exception — and `cmd /c start` can exit 0
# even then. Any of these patterns in the CAPTURED output means the launch
# failed, regardless of the friendly description.
_LAUNCH_FAILURE_PATTERNS = (
    "cannot find the file",
    "cannot find",
    "is not recognized",
    "no such file",
    "no such application",
    "access is denied",
    "the filename, directory name, or volume label syntax is incorrect",
    "the directory name is invalid",
    "unable to find application",
    "failed to launch",
)


def _launch_failure_detail(returncode: int, stdout: str, stderr: str) -> Optional[str]:
    """Return a human-readable failure reason, or None if output looks clean.

    This is how a failed `start` command is detected: the OS prints the error
    as text rather than raising, so the exit code alone is not enough.
    """
    combined = f"{stdout or ''}\n{stderr or ''}".strip()
    lowered = combined.lower()
    for pattern in _LAUNCH_FAILURE_PATTERNS:
        if pattern in lowered:
            return combined[:300] if combined else pattern
    if returncode != 0:
        detail = f": {combined[:200]}" if combined else ""
        return f"exit code {returncode}{detail}"
    return None


class SystemAppInventory:
    """
    Universal System Application Discovery & Enumeration Engine.
    Scans the entire host OS (Windows Start Menu/Registry, Linux .desktop/PATH, macOS /Applications, Android ADB)
    to enumerate every installed application, count them, and launch/operate ANY app on demand.

    Freshness (owner requirement 2026-09-08): the inventory must reflect what
    is installed NOW, not what was installed when the server started. The
    cache expires (TTL) and ANY matching miss triggers one immediate rescan
    before the tool admits an app is missing — a newly installed app must be
    findable seconds after installation.
    """

    _cached_apps: List[Dict[str, Any]] = []
    _cache_ts: float = 0.0
    CACHE_TTL_S: float = 600.0  # rescan at most every 10 minutes

    @classmethod
    def _cache_age(cls) -> float:
        import time as _time

        return max(0.0, _time.time() - cls._cache_ts)

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Letters+digits only, lowercase — 'Richie TV' and 'RichieTV' and
        'richie-tv' all fold to the same key."""
        return "".join(ch for ch in str(name).lower() if ch.isalnum())

    @classmethod
    def _init_db_table(cls):
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS installed_apps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT UNIQUE NOT NULL,
                    executable_path TEXT NOT NULL,
                    source_category TEXT NOT NULL,
                    last_scanned TEXT NOT NULL
                )
            """)
            conn.commit()

    @classmethod
    def scan_installed_applications(cls) -> Dict[str, Any]:
        """
        Enumerates all installed software and applications on the current host operating system.
        """
        cls._init_db_table()
        host_os = platform.system().lower()
        discovered_apps: Dict[str, Dict[str, Any]] = {}

        # 1. WINDOWS APPLICATION DISCOVERY
        if host_os == "windows":
            # Start Menu Shortcuts (.lnk files)
            program_dirs = [
                os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
                os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
                os.path.expandvars(r"%USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs")
            ]
            for p_dir in program_dirs:
                if os.path.exists(p_dir):
                    for root, _, files in os.walk(p_dir):
                        for f in files:
                            if f.lower().endswith(".lnk") or f.lower().endswith(".exe"):
                                name = f[:-4] if f.lower().endswith(".lnk") else f[:-4]
                                full_p = os.path.join(root, f)
                                if name and name.lower() not in ["uninstall", "help", "website", "readme"]:
                                    discovered_apps[name.lower()] = {
                                        "app_name": name,
                                        "executable_path": full_p,
                                        "source_category": "Windows Start Menu"
                                    }

            # Windows Registry Scan (winreg)
            try:
                import winreg
                for hkey_type in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    for subkey_path in [
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
                    ]:
                        try:
                            key = winreg.OpenKey(hkey_type, subkey_path)
                            for i in range(winreg.QueryInfoKey(key)[0]):
                                try:
                                    skey_name = winreg.EnumKey(key, i)
                                    skey = winreg.OpenKey(key, f"{subkey_path}\\{skey_name}")
                                    display_name = winreg.QueryValueEx(skey, "DisplayName")[0]
                                    install_loc = ""
                                    try:
                                        install_loc = winreg.QueryValueEx(skey, "InstallLocation")[0]
                                    except Exception:
                                        pass
                                    if display_name and display_name.lower() not in discovered_apps:
                                        discovered_apps[display_name.lower()] = {
                                            "app_name": display_name,
                                            "executable_path": install_loc or display_name,
                                            "source_category": "Windows Registry Installed App"
                                        }
                                except Exception:
                                    pass
                        except Exception:
                            pass
            except Exception:
                pass

        # 2. LINUX APPLICATION DISCOVERY
        elif host_os == "linux":
            desktop_dirs = [
                "/usr/share/applications",
                "/usr/local/share/applications",
                os.path.expanduser("~/.local/share/applications")
            ]
            for d in desktop_dirs:
                if os.path.exists(d):
                    for f in os.listdir(d):
                        if f.endswith(".desktop"):
                            f_path = os.path.join(d, f)
                            try:
                                with open(f_path, "r", encoding="utf-8", errors="ignore") as file:
                                    app_name = f[:-8]
                                    exec_cmd = ""
                                    for line in file:
                                        if line.startswith("Name="):
                                            app_name = line.split("=", 1)[1].strip()
                                        elif line.startswith("Exec="):
                                            exec_cmd = line.split("=", 1)[1].strip().split("%")[0].strip()
                                    if app_name:
                                        discovered_apps[app_name.lower()] = {
                                            "app_name": app_name,
                                            "executable_path": exec_cmd or app_name,
                                            "source_category": "Linux Desktop Application"
                                        }
                            except Exception:
                                pass

        # 3. MACOS APPLICATION DISCOVERY
        elif host_os == "darwin":
            mac_dirs = ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]
            for md in mac_dirs:
                if os.path.exists(md):
                    for app_item in os.listdir(md):
                        if app_item.endswith(".app"):
                            name = app_item[:-4]
                            full_p = os.path.join(md, app_item)
                            discovered_apps[name.lower()] = {
                                "app_name": name,
                                "executable_path": full_p,
                                "source_category": "macOS Application"
                            }

        # Common Fallback: Scan PATH environment for binaries
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for p_dir in path_dirs:
            if os.path.exists(p_dir):
                try:
                    for item in os.listdir(p_dir):
                        item_lower = item.lower()
                        if host_os == "windows" and item_lower.endswith(".exe"):
                            bin_name = item_lower[:-4]
                            if bin_name not in discovered_apps and len(bin_name) > 2:
                                discovered_apps[bin_name] = {
                                    "app_name": bin_name,
                                    "executable_path": os.path.join(p_dir, item),
                                    "source_category": "System PATH Binary"
                                }
                        elif host_os != "windows" and os.access(os.path.join(p_dir, item), os.X_OK):
                            if item_lower not in discovered_apps and len(item_lower) > 2:
                                discovered_apps[item_lower] = {
                                    "app_name": item,
                                    "executable_path": os.path.join(p_dir, item),
                                    "source_category": "System PATH Executable"
                                }
                except Exception:
                    pass

        cls._cached_apps = list(discovered_apps.values())
        import time as _time

        cls._cache_ts = _time.time()

        # Save into SQLite table
        with db._get_connection() as conn:
            cursor = conn.cursor()
            for app_info in cls._cached_apps:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO installed_apps (app_name, executable_path, source_category, last_scanned)
                        VALUES (?, ?, ?, ?)
                    """, (app_info["app_name"], app_info["executable_path"], app_info["source_category"], "active"))
                except Exception:
                    pass
            conn.commit()

        app_logger.info(f"Scanned host system ({host_os}): Discovered {len(cls._cached_apps)} installed applications.")
        db.create_audit_log("scan_installed_applications", "success", f"Discovered {len(cls._cached_apps)} applications on {host_os}", level=0)

        return {
            "success": True,
            "host_os": platform.system(),
            "total_apps_count": len(cls._cached_apps),
            "applications": cls._cached_apps
        }

    @classmethod
    def get_installed_apps_count(cls) -> int:
        if not cls._cached_apps:
            cls.scan_installed_applications()
        return len(cls._cached_apps)

    FUZZY_THRESHOLD = 0.6       # auto-launch confidence
    SUGGEST_THRESHOLD = 0.45    # worth showing as 'did you mean ...?'

    @classmethod
    def _match_app(cls, query_clean: str):
        """Best match for an app query against the CURRENT cache.

        Tiers: exact -> punctuation/space-insensitive exact -> query-inside-
        app-name substring (MATCH DIRECTION MATTERS: 'firef' -> 'Mozilla
        Firefox' is valid; a long sentence containing an app name is not) ->
        fuzzy similarity (difflib on normalized names, tolerant of typos and
        spelling drift like 'richst tv' -> 'Richie TV').

        Returns (matched_app_or_None, close_matches_ranked) — close_matches
        feed the honest 'which one did you mean?' ask on a total miss.
        """
        import difflib

        query_norm = cls._normalize_name(query_clean)
        if not query_norm:
            return None, []

        # Tier 1: exact name.
        for item in cls._cached_apps:
            if item["app_name"].lower() == query_clean:
                return item, []

        scored = []
        for item in cls._cached_apps:
            a_name = item["app_name"]
            a_name_l = a_name.lower()
            a_norm = cls._normalize_name(a_name)
            # Tier 2: normalized exact ('richie tv' == 'RichieTV').
            if a_norm == query_norm:
                return item, []
            # Tier 3: query inside the app name (short query, longer name).
            if len(query_clean) <= len(a_name_l) and query_clean in a_name_l:
                scored.append((1.0 - len(query_clean) / max(1, len(a_name_l)) * 0.1, item))
                continue
            # Tier 4: fuzzy similarity on normalized names.
            ratio = difflib.SequenceMatcher(None, query_norm, a_norm).ratio()
            # Token containment bonus: every query word appears in the name.
            q_tokens = [t for t in query_clean.split() if t]
            if q_tokens and all(t in a_name_l for t in q_tokens):
                ratio = max(ratio, 0.75)
            if ratio >= cls.SUGGEST_THRESHOLD:
                scored.append((ratio, item))

        if not scored:
            return None, []
        scored.sort(key=lambda ri: (-ri[0], ri[1]["app_name"].lower()))
        best_score, best = scored[0]
        close_matches = [it for _, it in scored[:3]]
        if best_score < cls.FUZZY_THRESHOLD:
            # Not confident enough to auto-launch — the top candidates still
            # feed the honest 'which one did you mean?' ask.
            return None, close_matches
        app_logger.info(
            f"Fuzzy app match: '{query_clean}' -> '{best['app_name']}' "
            f"(score {best_score:.2f})"
        )
        return best, close_matches

    @classmethod
    def launch_any_app(cls, app_query: str) -> Dict[str, Any]:
        """
        Finds and launches ANY installed application matching app_query on the system.
        """
        if not cls._cached_apps:
            cls.scan_installed_applications()

        query_clean = app_query.lower().strip()

        # INPUT VALIDATION (live bugs: entire sentences were used as app
        # names — 'now in contrrol panel open user accounts' "matched" an
        # app because of the bidirectional substring check below). A query
        # longer than a plausible app name is a sentence, not an app.
        MAX_QUERY_WORDS = 6
        if len(query_clean.split()) > MAX_QUERY_WORDS:
            return {
                "success": False,
                "refused": True,
                "error": (
                    f"'{app_query[:60]}' looks like a sentence, not an app name. "
                    f"App queries must be at most {MAX_QUERY_WORDS} words. "
                    "Extract the app name first or use the OS control planner."
                ),
            }

        # Policy Evaluation Check
        allowed, reason, level = PolicyEvaluator.evaluate_action("open_application", {"app_name": query_clean})
        if not allowed:
            return {"success": False, "error": f"Policy Blocked: {reason}", "authority_level": level}

        matched_app, close_matches = cls._match_app(query_clean)

        if matched_app is None:
            # Owner requirement (2026-09-08): a miss may just mean the app was
            # installed AFTER the last scan. Rescan NOW and retry before
            # telling the owner it does not exist.
            scan_res = cls.scan_installed_applications()
            app_logger.info(
                f"App '{app_query}' not in cached inventory — re-scanned "
                f"({scan_res.get('total_apps_count', 0)} apps) and retried."
            )
            try:
                from app.utils import decision_trace

                decision_trace.record(
                    "app_inventory", "miss_rescan_retry",
                    f"query '{app_query[:60]}' missed; inventory rescanned live",
                )
            except Exception:
                pass
            matched_app, close_matches = cls._match_app(query_clean)

        if not matched_app:
            # Direct Command Fallback — but ONLY for queries that resolve to a
            # real executable. Previously ANY unmatched ≤6-word string was
            # blind-executed via `cmd /c start`, so 'user accounts' became a
            # shell command that failed while the tool reported success=True.
            resolved = shutil.which(query_clean) or (
                query_clean if os.path.exists(query_clean) else None
            )
            if resolved is None:
                # Honest ambiguity ask: name the closest installed apps so the
                # owner can answer with one word.
                suggestions = [c["app_name"] for c in (close_matches or [])[:3]]
                detail = (
                    f"Closest installed apps: {', '.join(suggestions)}. "
                    "Which one did you mean?"
                ) if suggestions else (
                    "Nothing similar is installed. If you just installed it, "
                    "tell me the exact name from its shortcut."
                )
                return {
                    "success": False,
                    "refused": True,
                    "app_name": query_clean,
                    "close_matches": suggestions,
                    "error": (
                        f"No installed application matches '{app_query}' "
                        f"(inventory re-scanned just now) and it does not "
                        f"resolve to an executable on PATH. {detail}"
                    ),
                }
            matched_app = {
                "app_name": query_clean,
                "executable_path": resolved,
                "source_category": "Direct Command Fallback"
            }

        exec_path = matched_app["executable_path"]
        app_name = matched_app["app_name"]
        host_os = platform.system().lower()

        app_logger.info(f"Attempting to launch application '{app_name}' (Target: {exec_path}) on {host_os}...")

        try:
            launched_process = None
            # SECURITY: exec_path is resolved from the installed-app inventory
            # (or, in the fallback path, from shutil.which / an existing path) —
            # pass it as an argv element, never through a shell, to prevent
            # command injection.
            #
            # HONESTY: a failed Windows `start` prints its error to the console
            # instead of raising, so every `cmd /c start` invocation runs with
            # captured output and the captured text + exit code are checked
            # BEFORE success is claimed. os.startfile has no feedback channel,
            # but is only used for paths that verifiably exist on disk.
            if host_os == "windows":
                if exec_path.lower().endswith(".lnk") or os.path.exists(exec_path):
                    os.startfile(exec_path)
                else:
                    # `start` is a cmd.exe builtin; invoke it with /c and argv so
                    # exec_path is not shell-interpreted. `start` returns after
                    # spawning, so run() does not block on the launched app.
                    completed = subprocess.run(
                        ["cmd.exe", "/c", "start", "", exec_path],
                        capture_output=True, text=True, timeout=30,
                    )
                    failure = _launch_failure_detail(
                        completed.returncode, completed.stdout or "", completed.stderr or ""
                    )
                    if failure:
                        app_logger.error(f"Launch of '{app_name}' failed: {failure}")
                        return {
                            "success": False,
                            "app_name": app_name,
                            "executable_path": exec_path,
                            "error": f"Launch failed: {failure}",
                        }
            elif host_os == "darwin":
                if exec_path.endswith(".app"):
                    completed = subprocess.run(
                        ["open", exec_path], capture_output=True, text=True, timeout=30
                    )
                    failure = _launch_failure_detail(
                        completed.returncode, completed.stdout or "", completed.stderr or ""
                    )
                    if failure:
                        app_logger.error(f"Launch of '{app_name}' failed: {failure}")
                        return {
                            "success": False,
                            "app_name": app_name,
                            "executable_path": exec_path,
                            "error": f"Launch failed: {failure}",
                        }
                else:
                    launched_process = subprocess.Popen([exec_path])
            else:
                # Linux — exec_path must be a resolvable executable (verified
                # against the inventory or by shutil.which above); a missing
                # binary raises at spawn time and is caught below.
                launched_process = subprocess.Popen([exec_path])

            audit_logger.info(f"Successfully launched application '{app_name}'")

            return {
                "success": True,
                "app_name": app_name,
                "executable_path": exec_path,
                "launch_command_executed": True,
                "pid": launched_process.pid if launched_process is not None else None,
                "message": f"Successfully launched '{app_name}' on your {platform.system()} system!"
            }

        except subprocess.TimeoutExpired:
            app_logger.error(f"Launch of application '{app_name}' timed out.")
            return {
                "success": False,
                "app_name": app_name,
                "error": "Launch timed out."
            }
        except Exception as e:
            app_logger.error(f"Error launching application '{app_name}': {e}")
            return {
                "success": False,
                "app_name": app_name,
                "error": str(e)
            }
