"""Plugin registry — a folder where dropping a Python file adds a capability.

A plugin is a `.py` file in DATA_DIR/plugins that defines, at module level:

    NAME = "my_tool"                 # unique action_type
    DESCRIPTION = "what it does"
    SAFETY_LEVEL = 0                 # 0 read / 1 draft / 2 reversible / 3 sensitive
    CATEGORY = "plugin"

    def execute(payload: dict) -> dict:
        # payload carries the caller's kwargs; return {"success": ..., ...}

The registry scans that folder, imports each plugin, validates its shape, and
returns plugin entries in the same format the tool manifest uses — so plugins are
discovered and usable by the cognitive layer automatically.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger


class PluginRegistry:
    PLUGIN_DIR = settings.DATA_DIR / "plugins"

    @classmethod
    def ensure_dir(cls) -> None:
        cls.PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def discover_plugins(cls) -> Dict[str, Dict[str, Any]]:
        """Scan the plugin dir and return {action_type: manifest_entry}.

        Malformed plugins are logged and skipped — one bad plugin never breaks
        the whole registry.
        """
        cls.ensure_dir()
        plugins: Dict[str, Dict[str, Any]] = {}
        for path in sorted(cls.PLUGIN_DIR.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                mod = cls._load(path)
                name = getattr(mod, "NAME", None)
                if not name:
                    app_logger.warning(f"Plugin {path.name} missing NAME — skipped")
                    continue
                execute = getattr(mod, "execute", None)
                if not callable(execute):
                    app_logger.warning(f"Plugin {path.name} missing callable execute() — skipped")
                    continue

                # Single-arg closure so the handler signature matches the
                # "exactly one payload dict" invariant enforced elsewhere.
                handler = lambda payload: execute(payload or {})  # noqa: E731

                plugins[name] = {
                    "name": name,
                    "category": getattr(mod, "CATEGORY", "plugin"),
                    "safety_level": int(getattr(mod, "SAFETY_LEVEL", 3)),
                    "description": getattr(mod, "DESCRIPTION", "User plugin"),
                    "handler": handler,
                }
            except Exception as e:
                app_logger.warning(f"Could not load plugin {path.name}: {e}")
        return plugins

    @classmethod
    def _load(cls, path: Path):
        spec = importlib.util.spec_from_file_location(f"arena_plugin_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
