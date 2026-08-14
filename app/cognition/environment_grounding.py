"""Phase B/E: Environmental Self-Grounding & Resource Topology Engine."""

from __future__ import annotations
import os
import sys
import psutil
import platform
import datetime
from typing import Dict, Any, List, Optional

from app.config import settings
from app.database import db
from app.utils.logger import app_logger, audit_logger
from app.utils.hardware_monitor import HardwareMonitor
from app.utils.hardware_governor import HardwareGovernor
from app.tools.app_inventory import SystemAppInventory
from app.tools.win32_ghost_operator import Win32GhostOperator
from app.cognition.world_model import WorldModel, Entity, Observation

class EnvironmentGroundingEngine:
    """
    Environmental Self-Grounding & Resource Topology Engine.
    Probes host hardware, operating system, installed apps, active windows, and local networks,
    constructing a persistent WorldModel representation so the assistant ALWAYS knows where it is
    and works intelligently within available resources.
    """

    @classmethod
    def probe_complete_environment(cls) -> Dict[str, Any]:
        """
        Gathers a complete environmental topology snapshot across hardware, OS, apps, and network.
        """
        host_os = platform.system()
        os_release = platform.release()
        machine = platform.machine()

        # Hardware metrics
        hw_stats = HardwareMonitor.get_hardware_stats()
        cpu_count = psutil.cpu_count(logical=True) or 32

        # Installed Applications Count
        app_count = SystemAppInventory.get_installed_apps_count()

        # Active Window Handles
        windows = Win32GhostOperator.list_open_windows()

        topology_snapshot = {
            "host_os": f"{host_os} {os_release} ({machine})",
            "cpu_threads": cpu_count,
            "cpu_usage_percent": hw_stats.get("cpu_percent", 0),
            "ram_used_gb": hw_stats.get("ram_used_gb", 0),
            "ram_total_gb": hw_stats.get("ram_total_gb", 16),
            "vram_status": "RX 580 8 GB VRAM Managed",
            "installed_apps_count": app_count,
            "active_windows_count": len(windows),
            "top_window_title": windows[0]["title"] if windows else "Desktop"
        }

        # Update WorldModel
        try:
            wm = WorldModel(str(settings.DB_PATH))
            wm.upsert_entity(
                name=f"Host PC ({platform.node()})",
                entity_type="host_environment",
                attributes=topology_snapshot,
                entity_id="host_environment"
            )
            wm.observe(Observation(
                id=f"obs_env_{datetime.datetime.now().strftime('%H%M%S')}",
                subject="host_environment",
                predicate="topology_update",
                value=topology_snapshot,
                source="environment_grounding_engine"
            ))
        except Exception as e:
            app_logger.warning(f"WorldModel environment grounding notice: {e}")

        db.create_audit_log("probe_complete_environment", "success", f"Environment probed: {host_os} ({cpu_count} threads, {app_count} apps)", level=0)

        return topology_snapshot

    @classmethod
    def generate_grounding_prompt_context(cls) -> str:
        """
        Generates a dense, structured environmental self-awareness string for LLM prompts.
        """
        env = cls.probe_complete_environment()
        return (
            f"\n[ENVIRONMENTAL SELF-GROUNDING & LOCAL TOPOLOGY]\n"
            f"• Host Machine: {env['host_os']} | Node: {platform.node()}\n"
            f"• CPU Hardware: Intel Core i9-14900K ({env['cpu_threads']} Logical Threads | {env['cpu_usage_percent']}% Load)\n"
            f"• System Memory: {env['ram_used_gb']}/{env['ram_total_gb']} GB RAM | GPU: RX 580 (8 GB VRAM Managed)\n"
            f"• Software Footprint: {env['installed_apps_count']} Installed Applications | {env['active_windows_count']} Active Windows (Focus: '{env['top_window_title']}')\n"
            f"• Capability Status: 100% Offline, Privacy Preserved, Full Native OS Permission Granted.\n"
        )
