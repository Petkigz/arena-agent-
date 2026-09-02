"""Package installer — list/check/install/uninstall pip and npm packages.

Deterministic subprocess wrapper, no LLM. Commands are always run as argument
lists (never `shell=True`), and package names are validated against a whitelist
charset + a leading-dash check so a value can't be interpreted as a flag or
inject a shell.

Safety model (manifest authoritative):
- list_packages / check_package → Level 0 (read).
- install_package / uninstall_package → Level 3 (irreversible system mutation),
  gated behind explicit owner approval.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, Optional

from app.cognition.execution_control import run_cancellable_subprocess
from app.utils.logger import app_logger, audit_logger

# Conservative whitelist: letters, digits, and common package-spec punctuation.
# Deliberately excludes whitespace, shell metacharacters, quotes, and backslashes.
_PKG_RE = re.compile(r"^[A-Za-z0-9._\-@/<>!=~+*,\[\]]+$")


class PackageInstaller:
    MANAGERS = ("pip", "npm")

    # ── read (Level 0) ──────────────────────────────────────────────────────
    @classmethod
    def list_packages(cls, manager: str = "pip") -> Dict[str, Any]:
        """List installed packages for the given manager."""
        manager = (manager or "").strip().lower()
        if manager not in cls.MANAGERS:
            return {"success": False, "error": f"Unsupported manager. Use one of {list(cls.MANAGERS)}."}

        if manager == "pip":
            try:
                out = run_cancellable_subprocess(
                    ["pip", "list", "--format=json"], timeout=60,
                )
                if out.returncode != 0:
                    return {"success": False, "error": f"pip list failed: {(out.stderr or '').strip()[:300]}"}
                pkgs = json.loads(out.stdout or "[]")
                return {"success": True, "manager": manager, "count": len(pkgs), "packages": pkgs}
            except FileNotFoundError:
                return {"success": False, "error": "pip is not available on this system."}
            except Exception as e:
                return {"success": False, "error": f"pip list failed: {e}"}

        # npm
        try:
            out = run_cancellable_subprocess(
                ["npm", "list", "--json", "--depth=0"], timeout=60,
            )
            if out.returncode != 0:
                return {"success": False, "error": f"npm list failed: {(out.stderr or '').strip()[:300]}"}
            data = json.loads(out.stdout or "{}")
            deps = data.get("dependencies", {})
            pkgs = [{"name": k, "version": v.get("version", "")} for k, v in deps.items()]
            return {"success": True, "manager": manager, "count": len(pkgs), "packages": pkgs}
        except FileNotFoundError:
            return {"success": False, "error": "npm is not available on this system."}
        except Exception as e:
            return {"success": False, "error": f"npm list failed: {e}"}

    @classmethod
    def check_package(cls, package: str, manager: str = "pip") -> Dict[str, Any]:
        """Check whether a single package is installed, and its version."""
        manager = (manager or "").strip().lower()
        if manager not in cls.MANAGERS:
            return {"success": False, "error": f"Unsupported manager. Use one of {list(cls.MANAGERS)}."}
        pkg, err = cls._validate(package)
        if err:
            return {"success": False, "error": err}

        if manager == "pip":
            try:
                out = run_cancellable_subprocess(
                    ["pip", "show", pkg], timeout=30,
                )
            except FileNotFoundError:
                return {"success": False, "error": "pip is not available on this system."}
            if out.returncode != 0:
                return {"success": False, "installed": False, "package": pkg}
            info = {}
            for line in (out.stdout or "").splitlines():
                if ": " in line:
                    k, v = line.split(": ", 1)
                    info[k.strip().lower()] = v.strip()
            return {"success": True, "installed": True, "package": pkg, "version": info.get("version", "")}
        else:
            try:
                out = run_cancellable_subprocess(
                    ["npm", "list", pkg, "--json", "--depth=0"], timeout=30,
                )
            except FileNotFoundError:
                return {"success": False, "error": "npm is not available on this system."}
            if out.returncode != 0:
                return {"success": False, "installed": False, "package": pkg}
            return {"success": True, "installed": True, "package": pkg}

    # ── write (Level 3) ─────────────────────────────────────────────────────
    @classmethod
    def install_package(cls, package: str, manager: str = "pip", upgrade: bool = False) -> Dict[str, Any]:
        """Install a package. Level 3: requires owner approval."""
        manager = (manager or "").strip().lower()
        if manager not in cls.MANAGERS:
            return {"success": False, "error": f"Unsupported manager. Use one of {list(cls.MANAGERS)}."}
        pkg, err = cls._validate(package)
        if err:
            return {"success": False, "error": err}

        if manager == "pip":
            cmd = ["pip", "install"]
            if upgrade:
                cmd.append("--upgrade")
            cmd.append(pkg)
        else:
            cmd = ["npm", "install"]
            if upgrade:
                cmd = ["npm", "update"]
            cmd.append(pkg)

        try:
            out = run_cancellable_subprocess(cmd, timeout=600)
            audit_logger.info(f"Installed {pkg} via {manager} (rc={out.returncode})")
            if out.returncode != 0:
                return {"success": False, "error": (out.stderr or out.stdout or "").strip()[:500]}
            # The environment changed (follow-up review #6): every cached
            # availability reading is now stale, and tool modules that
            # failed to import get retried.
            try:
                from app.cognition.tool_registry import note_environment_change
                note_environment_change(f"dependency_installed:{pkg}")
            except Exception:
                pass
            return {"success": True, "package": pkg, "manager": manager, "output": (out.stdout or "").strip()[:500]}
        except FileNotFoundError:
            return {"success": False, "error": f"{manager} is not available on this system."}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Installation timed out."}
        except Exception as e:
            return {"success": False, "error": f"Installation failed: {e}"}

    @classmethod
    def uninstall_package(cls, package: str, manager: str = "pip") -> Dict[str, Any]:
        """Uninstall a package. Level 3: requires owner approval."""
        manager = (manager or "").strip().lower()
        if manager not in cls.MANAGERS:
            return {"success": False, "error": f"Unsupported manager. Use one of {list(cls.MANAGERS)}."}
        pkg, err = cls._validate(package)
        if err:
            return {"success": False, "error": err}

        if manager == "pip":
            cmd = ["pip", "uninstall", "-y", pkg]
        else:
            cmd = ["npm", "uninstall", pkg]

        try:
            out = run_cancellable_subprocess(cmd, timeout=300)
            audit_logger.info(f"Uninstalled {pkg} via {manager} (rc={out.returncode})")
            if out.returncode != 0:
                return {"success": False, "error": (out.stderr or out.stdout or "").strip()[:500]}
            # The environment changed (follow-up review #6): cached
            # availability readings are stale; capabilities backed by this
            # package are gone.
            try:
                from app.cognition.tool_registry import note_environment_change
                note_environment_change(f"dependency_uninstalled:{pkg}")
            except Exception:
                pass
            return {"success": True, "package": pkg, "manager": manager}
        except FileNotFoundError:
            return {"success": False, "error": f"{manager} is not available on this system."}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Uninstall timed out."}
        except Exception as e:
            return {"success": False, "error": f"Uninstall failed: {e}"}

    # ── validation ──────────────────────────────────────────────────────────
    @classmethod
    def _validate(cls, package: str):
        """Return (package, None) or (None, error)."""
        if not package or not str(package).strip():
            return None, "A package name is required."
        pkg = str(package).strip()
        if pkg.startswith("-"):
            return None, "Package name must not look like a flag."
        if not _PKG_RE.match(pkg):
            return None, "Package name contains invalid characters."
        return pkg, None
