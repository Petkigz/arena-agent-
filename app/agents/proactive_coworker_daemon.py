import asyncio
import os
import psutil
import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger, audit_logger
from app.utils.hardware_governor import HardwareGovernor
from app.tools.app_inventory import SystemAppInventory
from app.tools.doc_manager import DocumentManager
from app.tasks import TaskManager
from app.memory.semantic_rag import SemanticRAGEngine
from app.scheduler.self_healer import AutonomousSelfHealer

class ProactiveCoworkerDaemon:
    """
    Proactive Coworker Autonomous Daemon & Ambient PC Idle Listener.
    Monitors host CPU load and idle state on Intel E-Cores, launching background memory indexing,
    workspace audits, and tool self-healing automatically when the user is away from the desk.
    """

    _last_proactive_insight: Optional[str] = None
    _is_idle: bool = False

    @classmethod
    def check_pc_idle_state(cls, cpu_idle_threshold: float = 18.0) -> Dict[str, Any]:
        """
        Monitors host system CPU load to determine if the PC is currently in an idle state.
        """
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cls._is_idle = cpu_percent < cpu_idle_threshold

        return {
            "is_idle": cls._is_idle,
            "cpu_usage_percent": cpu_percent,
            "idle_threshold": cpu_idle_threshold,
            "note": "PC is idle; launching background E-Core maintenance." if cls._is_idle else "PC is active; pausing background maintenance to reserve resources."
        }

    @classmethod
    def run_idle_proactive_cycle(cls) -> Dict[str, Any]:
        """
        Executes an idle proactive cycle: scans workspace, active task queue, and runs tool self-healing.
        """
        HardwareGovernor.set_thread_affinity(e_cores_only=True)
        idle_info = cls.check_pc_idle_state()

        app_logger.info(f"[PROACTIVE DAEMON] Running background coworker cycle on E-Cores (CPU: {idle_info['cpu_usage_percent']}%)...")

        # 1. Inspect Active Tasks
        pending_tasks = TaskManager.get_all_tasks(status="queued")
        task_summary = f"{len(pending_tasks)} queued tasks" if pending_tasks else "task queue clean"

        # 2. Inspect Workspace Files
        workspace_files = DocumentManager.list_workspace_files()
        file_count = len(workspace_files) if isinstance(workspace_files, list) else 0

        # 3. Inspect System App Count
        app_count = SystemAppInventory.get_installed_apps_count()

        # 4. Trigger Self-Healing Immune Cycle if Idle
        self_heal_res = None
        if idle_info["is_idle"]:
            try:
                # Async loop wrapper or background trigger
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(AutonomousSelfHealer.run_maintenance_cycle())
                else:
                    loop.run_until_complete(AutonomousSelfHealer.run_maintenance_cycle())
                self_heal_res = "Autonomous self-healer triggered on idle E-Cores."
            except Exception as e:
                self_heal_res = f"Self-healer notice: {e}"

        # Construct Proactive Insight
        today_str = datetime.datetime.now().strftime("%I:%M %p")
        insight = (
            f"Proactive Coworker Update ({today_str}): Workspace has {file_count} documents and {task_summary}. "
            f"System index reflects {app_count} installed applications. {self_heal_res or 'All systems running secure.'}"
        )

        cls._last_proactive_insight = insight

        # Save to RAG memory
        db.create_memory({
            "content": insight,
            "category": "proactive_insight",
            "source": "proactive_coworker_daemon",
            "confidence": 1.0
        })

        db.create_audit_log("run_idle_proactive_cycle", "success", insight, level=0)

        return {
            "success": True,
            "proactive_insight": insight,
            "pc_idle_state": idle_info,
            "queued_tasks_count": len(pending_tasks),
            "workspace_files_count": file_count,
            "installed_apps_count": app_count,
            "self_heal_status": self_heal_res
        }

    @classmethod
    def get_proactive_greeting(cls) -> str:
        """
        Returns a warm, concise proactive greeting for the user.
        """
        if cls._last_proactive_insight:
            return cls._last_proactive_insight
        
        cycle_res = cls.run_idle_proactive_cycle()
        return cycle_res.get("proactive_insight", "Proactive Coworker ready.")
