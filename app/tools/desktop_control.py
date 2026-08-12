import os
import sys
import subprocess
from typing import Dict, Any, List
from app.policy import PolicyEvaluator
from app.utils.logger import app_logger, audit_logger
from app.tools.app_inventory import SystemAppInventory

class DesktopControl:
    @classmethod
    def launch_application(cls, app_key: str) -> Dict[str, Any]:
        """
        Launches ANY installed desktop application on Windows/Linux/macOS under Level 2 Safety Policy.
        """
        return SystemAppInventory.launch_any_app(app_key)

    @classmethod
    def list_approved_apps(cls) -> List[str]:
        defaults = ["vscode", "chrome", "firefox", "notepad", "calculator", "terminal", "lm_studio", "explorer"]
        scan_res = SystemAppInventory.scan_installed_applications()
        scanned_names = [a["app_name"].lower() for a in scan_res.get("applications", [])[:50]]
        return list(dict.fromkeys(defaults + scanned_names))

    @classmethod
    def open_url(cls, url: str) -> Dict[str, Any]:
        """
        Opens a target URL in default desktop web browser (or Firefox/Chrome).
        """
        import webbrowser
        try:
            webbrowser.open(url)
            audit_logger.info(f"Opened URL in desktop browser: '{url}'")
            return {
                "success": True,
                "url": url,
                "message": f"Successfully opened URL in browser: {url}"
            }
        except Exception as e:
            app_logger.error(f"Error opening URL: {e}")
            return {"success": False, "error": str(e)}
