"""Lightweight resource awareness for Arena's 16 GB RAM / 8 GB VRAM host."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict
import os

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float
    ram_percent: float
    ram_available_mb: float
    gpu_percent: float | None = None
    vram_percent: float | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResourceManager:
    """Read host resources and expose conservative execution decisions."""

    def __init__(self, ram_limit_gb: float = 16.0, vram_limit_gb: float = 8.0) -> None:
        self.ram_limit_gb = ram_limit_gb
        self.vram_limit_gb = vram_limit_gb

    def snapshot(self) -> ResourceSnapshot:
        if psutil is None:
            return ResourceSnapshot(0.0, 0.0, self.ram_limit_gb * 1024)
        memory = psutil.virtual_memory()
        return ResourceSnapshot(
            cpu_percent=psutil.cpu_percent(interval=None),
            ram_percent=memory.percent,
            ram_available_mb=memory.available / (1024 * 1024),
        )

    def execution_policy(self, snapshot: ResourceSnapshot | None = None) -> Dict[str, Any]:
        snap = snapshot or self.snapshot()
        if snap.ram_percent >= 90:
            return {"mode": "constrained", "allow_background_learning": False,
                    "preferred_model_tier": "fast", "reason": "RAM >= 90%"}
        if snap.ram_percent >= 80:
            return {"mode": "pressure", "allow_background_learning": False,
                    "preferred_model_tier": "fast", "reason": "RAM >= 80%"}
        return {"mode": "normal", "allow_background_learning": True,
                "preferred_model_tier": "main", "reason": "resources within normal range"}
