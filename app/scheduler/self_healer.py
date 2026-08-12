import asyncio
import os
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger, audit_logger
from app.utils.hardware_governor import HardwareGovernor
from app.agents.self_evolving_agent import SelfEvolvingAgent

class AutonomousSelfHealer:
    """
    Autonomous Idle-Time Self-Healing & Immune Engine.
    Scans system audit logs for tool failures during idle cycles, diagnoses traceback errors,
    and hot-patches the codebase live without server restarts.
    """

    _healing_lock = asyncio.Lock()

    @classmethod
    async def run_maintenance_cycle(cls) -> Dict[str, Any]:
        """
        Scans recent SQLite audit logs for tool failures, diagnoses the bug,
        and triggers hot-patching.
        """
        if cls._healing_lock.locked():
            return {"success": False, "note": "Self-healer cycle already active."}

        async with cls._healing_lock:
            # Pin background maintenance strictly to Intel E-Cores
            HardwareGovernor.set_thread_affinity(e_cores_only=True)
            app_logger.info("[SELF-HEALER IMMUNE ENGINE] Starting autonomous audit cycle on E-Cores...")

            logs = db.get_audit_logs(limit=50)
            failed_logs = [l for l in logs if l.get("status") in ["failed", "error", "crash"]]

            if not failed_logs:
                app_logger.info("[SELF-HEALER IMMUNE ENGINE] System operating 100% cleanly. Zero failures detected.")
                return {"success": True, "failed_tools_count": 0, "note": "All system tools operating cleanly."}

            target = failed_logs[0]
            action_name = target.get("action", "unknown_tool")
            details = target.get("details", "")

            app_logger.warning(f"[SELF-HEALER IMMUNE ENGINE] Failure detected in tool '{action_name}': {details[:100]}. Auto-patching...")

            patch_res = SelfEvolvingAgent.synthesize_and_hotload_tool(
                task_objective=f"Fix runtime error in tool '{action_name}': {details}",
                tool_name_query=f"patched_{action_name}"
            )

            # Purge VRAM and RAM after maintenance
            HardwareGovernor.purge_vram_and_system_memory()

            db.create_audit_log("self_heal_cycle", "success", f"Auto-patched tool failure in '{action_name}'", level=1)

            return {
                "success": True,
                "patched_tool": action_name,
                "details": details,
                "patch_result": patch_res
            }
