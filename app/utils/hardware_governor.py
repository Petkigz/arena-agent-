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
from app.utils.hardware_monitor import HardwareMonitor

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
        if total_cpus >= 20 and total_ram_gb >= 32.0:
            tier_level = 1
            tier_name = "TIER 1 (High-memory workstation / 32GB+ RAM)"
            max_threads = total_cpus
            max_context_budget = 8192
            enable_background_daemon = True
        elif total_cpus >= 8 and total_ram_gb >= 16.0:
            tier_level = 2
            tier_name = "TIER 2 (Mid-range workstation / 16GB+ RAM)"
            max_threads = min(12, total_cpus)
            max_context_budget = 4096
            enable_background_daemon = True
        else:
            tier_level = 3
            tier_name = "TIER 3 (Low-memory host / under 16GB RAM)"
            max_threads = min(4, total_cpus)
            max_context_budget = 2048
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
    def _detect_gpu_model() -> str:
        """Best-effort GPU model string (NVIDIA via torch, otherwise lspci/wmic)."""
        try:
            import torch
            if torch.cuda.is_available():
                return torch.cuda.get_device_name(0)
        except Exception:
            pass
        try:
            if platform.system() == "Linux":
                out = subprocess.run(
                    ["lspci"], capture_output=True, text=True, timeout=5
                ).stdout
                for line in out.splitlines():
                    if "VGA" in line or "3D controller" in line or "Display controller" in line:
                        return line.split(": ", 1)[-1].strip()
            elif platform.system() == "Windows":
                out = subprocess.run(
                    ["wmic", "path", "win32_VideoController", "get", "name"],
                    capture_output=True, text=True, timeout=5,
                ).stdout
                lines = [l.strip() for l in out.splitlines() if l.strip() and "Name" not in l]
                if lines:
                    return lines[0]
        except Exception:
            pass
        return "Unknown GPU"

    @staticmethod
    def _detect_cpu_model() -> str:
        """Best-effort CPU model string."""
        try:
            proc = platform.processor()
            if proc and proc.strip():
                return proc.strip()
        except Exception:
            pass
        try:
            if platform.system() == "Linux":
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if line.lower().startswith("model name"):
                            return line.split(":", 1)[-1].strip()
        except Exception:
            pass
        return platform.machine() or "Unknown CPU"

    @classmethod
    def build_self_model(cls) -> Dict[str, Any]:
        """
        Build a comprehensive hardware self-model the agent can reason about.

        Combines static tier detection (P/E-core topology, RAM, GPU tier) with live
        telemetry (CPU/RAM/disk load) plus an inference-capability assessment and
        concrete operating recommendations. This is the "knows its own hardware"
        substrate — the agent queries this rather than assuming a fixed profile.
        """
        tier = cls.detect_hardware_tier()
        live = HardwareMonitor.get_hardware_stats()
        cpu_model = cls._detect_cpu_model()
        gpu_model = cls._detect_gpu_model()

        logical_cpus = tier["cpu_threads"]
        # Hybrid Intel (>=24 logical) implies P-cores + E-cores (e.g. i9-14900K: 8P+16E).
        hybrid = logical_cpus >= 24
        p_threads = min(16, logical_cpus) if hybrid else logical_cpus
        e_threads = (logical_cpus - 16) if hybrid else 0

        cuda_available = tier.get("gpu_available", False)
        # RX 580 (Polaris) and similar are not practical CUDA/ROCm inference targets.
        inference_accel = "cuda" if cuda_available else "cpu_only"

        ram_total_gb = float(live.get("ram_total_gb") or tier.get("total_ram_gb") or 16.0)
        ram_pressure = float(live.get("ram_percent", 0.0))
        cpu_pressure = float(live.get("cpu_percent", 0.0))

        # Model-fit recommendation based on RAM + acceleration.
        if inference_accel == "cuda":
            model_recommendation = "qwen2.5-9b-instruct (GPU-accelerated)"
        elif ram_total_gb >= 40:
            model_recommendation = "qwen2.5-14b-instruct (Q4, CPU) or 9B for faster interaction"
        elif ram_total_gb >= 24:
            model_recommendation = "qwen2.5-9b-instruct (Q4_K_M, CPU)"
        elif ram_total_gb >= 12:
            model_recommendation = "qwen2.5-3b/7b-instruct (Q4_K_M, CPU)"
        else:
            model_recommendation = "qwen2.5-1.5b/3b-instruct (Q4_K_M, CPU)"

        operating_mode = "high_performance" if not tier.get("ultra_lean_mode") else "ultra_lean"

        # Measured (not just recommended) concurrency budget from live pressure.
        from app.utils.concurrency_governor import ConcurrencyGovernor
        try:
            worker_budget = ConcurrencyGovernor.measure(stats=live)
        except Exception as exc:
            app_logger.warning(f"Concurrency budget measurement unavailable: {exc}")
            worker_budget = {"success": False, "workers_granted": 1, "reasons": [f"measurement_unavailable: {exc}"]}

        return {
            "cpu_model": cpu_model,
            "cpu_logical_threads": logical_cpus,
            "hybrid_architecture": hybrid,
            "p_core_threads": p_threads,
            "e_core_threads": e_threads,
            "ram_total_gb": ram_total_gb,
            "gpu_model": gpu_model,
            "gpu_acceleration": inference_accel,
            "disk_free_gb": live.get("disk_free_gb", 0.0),
            "hardware_tier": tier["tier_name"],
            "operating_mode": operating_mode,
            "high_memory_profile": ram_total_gb >= 32,
            "recommended_parallel_cpu_tasks": 6 if ram_total_gb >= 40 else 3 if ram_total_gb >= 24 else 1,
            "measured_worker_budget": worker_budget,
            "memory_consolidation_batch": 500 if ram_total_gb >= 40 else 100,
            "memory_record_cap": 20000 if ram_total_gb >= 40 else 5000,
            "live": {
                "cpu_percent": cpu_pressure,
                "ram_percent": ram_pressure,
                "disk_percent": live.get("disk_percent", 0.0),
            },
            "recommendation": {
                "model": model_recommendation,
                "p_cores_for_reasoning": hybrid,
                "e_cores_for_background": hybrid,
                "purge_memory_when_ram_above": 85.0,
                "downgrade_to_fast_when_ram_above": 80.0,
            },
        }

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
