import os
import gc
import sys
import psutil
import platform
import subprocess
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger

class HardwareGovernor:
    """
    Universal Hardware Governor & Hardware Tier Adaptation Engine.
    Detects CPU generation (3rd Gen, 8th Gen, i9-14900K), available system RAM, and GPU VRAM,
    automatically shifting operational profiles (Ultra-Lean Mode vs High-Performance Mode)
    so the assistant runs smooth without lag on ANY machine.
    """

    @classmethod
    def detect_hardware_tier(cls) -> Dict[str, Any]:
        """
        Detects CPU threads, RAM, and GPU status to categorize host PC into Hardware Tier 1, 2, or 3.
        """
        total_cpus = psutil.cpu_count(logical=True) or 4
        ram = psutil.virtual_memory()
        total_ram_gb = round(ram.total / (1024 ** 3), 1)

        gpu_available = False
        try:
            import torch
            gpu_available = torch.cuda.is_available()
        except Exception:
            pass

        # Tier classification logic
        if total_cpus >= 20 and total_ram_gb >= 15.0 and gpu_available:
            tier_level = 1
            tier_name = "TIER 1 (Ultra High-End / i9-14900K)"
            max_threads = total_cpus
            max_context_budget = 1000
            enable_background_daemon = True
        elif total_cpus >= 8 and total_ram_gb >= 8.0:
            tier_level = 2
            tier_name = "TIER 2 (Mid-Range 8th Gen CPU / 8-16GB RAM)"
            max_threads = min(8, total_cpus)
            max_context_budget = 500
            enable_background_daemon = True
        else:
            tier_level = 3
            tier_name = "TIER 3 (Legacy Low-Spec 2nd-7th Gen CPU / <8GB RAM)"
            max_threads = min(4, total_cpus)
            max_context_budget = 250
            enable_background_daemon = False

        return {
            "tier_level": tier_level,
            "tier_name": tier_name,
            "cpu_threads": total_cpus,
            "total_ram_gb": total_ram_gb,
            "gpu_available": gpu_available,
            "allocated_max_threads": max_threads,
            "max_context_budget_tokens": max_context_budget,
            "background_daemon_enabled": enable_background_daemon,
            "ultra_lean_mode": tier_level == 3
        }

    @classmethod
    def set_thread_affinity(cls, p_cores_only: bool = False, e_cores_only: bool = False) -> Dict[str, Any]:
        """
        Binds current process execution affinity across Intel P-Cores / E-Cores or restricts threads on lower-spec CPUs.
        """
        proc = psutil.Process(os.getpid())
        total_cpus = psutil.cpu_count(logical=True) or 4
        tier = cls.detect_hardware_tier()

        selected_affinity = list(range(total_cpus))

        if total_cpus >= 24:
            if p_cores_only:
                selected_affinity = list(range(min(16, total_cpus)))
            elif e_cores_only:
                selected_affinity = list(range(16, total_cpus))
        elif tier["tier_level"] == 3:
            # Low-spec PC: restrict to first 2-4 threads to prevent CPU overheating/lag
            selected_affinity = list(range(min(4, total_cpus)))

        try:
            if hasattr(proc, 'cpu_affinity'):
                proc.cpu_affinity(selected_affinity)
                app_logger.info(f"HardwareGovernor set CPU affinity for {tier['tier_name']}: {selected_affinity[:8]}...")

            return {
                "success": True,
                "hardware_tier": tier["tier_name"],
                "total_cpu_threads": total_cpus,
                "active_affinity_threads": len(selected_affinity),
                "ultra_lean_mode": tier["ultra_lean_mode"]
            }
        except Exception as e:
            app_logger.warning(f"Cpu affinity setting error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def purge_vram_and_system_memory() -> Dict[str, Any]:
        """
        Force-clears Python garbage collection, unloads unused memory objects,
        and issues PyTorch/LM Studio VRAM cache flush triggers.
        """
        gc.collect()

        vram_flushed = False
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                vram_flushed = True
        except Exception:
            pass

        ram = psutil.virtual_memory()
        free_ram_gb = round(ram.available / (1024 ** 3), 2)

        db.create_audit_log("purge_vram_and_system_memory", "success", f"Purged VRAM/RAM. Free RAM: {free_ram_gb} GB", level=0)

        return {
            "success": True,
            "vram_cache_flushed": vram_flushed,
            "free_system_ram_gb": free_ram_gb,
            "total_system_ram_gb": round(ram.total / (1024 ** 3), 2),
            "ram_usage_percent": ram.percent
        }
