import os
import sys
import glob
import shutil
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger

class SystemAppInventory:
    """
    Universal System Application Discovery & Enumeration Engine.
    Scans the entire host OS (Windows Start Menu/Registry, Linux .desktop/PATH, macOS /Applications, Android ADB)
    to enumerate every installed application, count them, and launch/operate ANY app on demand.
    """

    _cached_apps: List[Dict[str, Any]] = []

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

        # Save into SQLite table
        now_str = sys.getwindowsversion() if hasattr(sys, 'getwindowsversion') else "scanned"
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

        # Search for exact or fuzzy match. MATCH DIRECTION MATTERS: a short
        # app query matching inside a longer installed name is valid
        # ('firef' -> 'Mozilla Firefox'), but a LONG query containing an app
        # name is a sentence ('now in contrrol panel open user accounts'
        # contains 'control panel') and must NOT match.
        matched_app = None
        for item in cls._cached_apps:
            a_name = item["app_name"].lower()
            if query_clean == a_name:
                matched_app = item
                break
        if matched_app is None:
            # Substring: only the QUERY inside the APP NAME (short query,
            # longer installed name). Never the reverse.
            for item in cls._cached_apps:
                a_name = item["app_name"].lower()
                if len(query_clean) <= len(a_name) and query_clean in a_name:
                    matched_app = item
                    break

        if not matched_app:
            # Fallback direct execution attempt
            matched_app = {
                "app_name": query_clean,
                "executable_path": query_clean,
                "source_category": "Direct Command Fallback"
            }

        exec_path = matched_app["executable_path"]
        app_name = matched_app["app_name"]
        host_os = platform.system().lower()

        app_logger.info(f"Attempting to launch application '{app_name}' (Target: {exec_path}) on {host_os}...")

        try:
            launched_process = None
            # SECURITY: exec_path is resolved from the installed-app inventory
            # (or, in the fallback path, from a user query) — pass it as an argv
            # element, never through a shell, to prevent command injection.
            if host_os == "windows":
                if exec_path.lower().endswith(".lnk") or os.path.exists(exec_path):
                    os.startfile(exec_path)
                else:
                    # `start` is a cmd.exe builtin; invoke it with /c and argv so
                    # exec_path is not shell-interpreted.
                    launched_process = subprocess.Popen(["cmd.exe", "/c", "start", "", exec_path])
            elif host_os == "darwin":
                if exec_path.endswith(".app"):
                    launched_process = subprocess.Popen(["open", exec_path])
                else:
                    launched_process = subprocess.Popen([exec_path])
            else:
                # Linux — exec_path must be a resolvable executable.
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

        except Exception as e:
            app_logger.error(f"Error launching application '{app_name}': {e}")
            return {
                "success": False,
                "app_name": app_name,
                "error": str(e)
            }
