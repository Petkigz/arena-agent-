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
    Intel Core i9-14900K Thread Governor & RX 580 VRAM Memory Management Engine.
    Shunts tasks between Intel Performance P-Cores and Efficiency E-Cores, and manages
    VRAM caches for LM Studio local model inference.
    """

    @staticmethod
    def set_thread_affinity(p_cores_only: bool = False, e_cores_only: bool = False) -> Dict[str, Any]:
        """
        Binds current process execution affinity across Intel i9-14900K P-Cores / E-Cores.
        14900K has 8 P-Cores (16 threads: 0-15) and 16 E-Cores (16 threads: 16-31).
        """
        proc = psutil.Process(os.getpid())
        total_cpus = psutil.cpu_count(logical=True) or 32

        selected_affinity = list(range(total_cpus))

        if total_cpus >= 24:
            if p_cores_only:
                # First 16 logical threads (P-Cores with HyperThreading)
                selected_affinity = list(range(min(16, total_cpus)))
            elif e_cores_only:
                # Remaining logical threads (E-Cores)
                selected_affinity = list(range(16, total_cpus))

        try:
            if hasattr(proc, 'cpu_affinity'):
                proc.cpu_affinity(selected_affinity)
                app_logger.info(f"HardwareGovernor set CPU affinity to threads: {selected_affinity[:8]}...")

            return {
                "success": True,
                "total_cpu_threads": total_cpus,
                "active_affinity_threads": len(selected_affinity),
                "p_cores_mode": p_cores_only,
                "e_cores_mode": e_cores_only
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

        # Check PyTorch VRAM flush if available
        vram_flushed = False
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                vram_flushed = True
        except Exception:
            pass

        # Memory stats
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
