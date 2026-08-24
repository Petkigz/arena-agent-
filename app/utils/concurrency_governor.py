"""Measured, owner-configured worker concurrency derived from live pressure.

The hardware self-model recommends a parallel-CPU task count from installed RAM,
but a recommendation is not a scheduler. This module turns that recommendation
into a *measured* budget: before any parallelizable workload runs, the governor
samples live RAM/CPU pressure, applies the owner's persisted override, and
grants a worker count with typed reasons. Every execution writes a receipt
(workers granted, items, duration, refusal reasons) so concurrency claims stay
evidence-backed instead of asserted.

Owner authority rules (mirroring the sovereign-grant invariants):
  * The owner may set ``max_workers`` anywhere in ``[1, physical thread count]``
    — raising or lowering the configured budget is the owner's decision.
  * The owner may disable parallelism entirely (``enabled: false``).
  * No override may bypass the critical resource gate: under critical RAM/CPU
    pressure the granted budget collapses to 1 (serial execution) regardless of
    the override.
  * The owner cannot grant more workers than physically exist.

Honesty note: Python threads only truly parallelize work that releases the GIL
(I/O, C extensions). Receipts record measured wall-time so any speedup claim
comes from measurement, never from this module's configuration.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

import psutil

from app.config import settings
from app.utils.hardware_monitor import HardwareMonitor
from app.utils.logger import app_logger, audit_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConcurrencyOverride:
    """Owner's persisted concurrency policy. Missing values mean measured defaults."""
    enabled: bool = True
    max_workers: Optional[int] = None  # None → use the measured recommendation
    revision: int = 0
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConcurrencyOverrideStore:
    """Atomic, thread-safe persistence for the owner's concurrency budget."""

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = Path(path) if path is not None else settings.DATA_DIR / "concurrency_budget.json"
        self._lock = threading.RLock()
        self._override: ConcurrencyOverride = self._load()

    def _load(self) -> ConcurrencyOverride:
        if not self.path.exists():
            return ConcurrencyOverride()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            max_workers = raw.get("max_workers")
            return ConcurrencyOverride(
                enabled=bool(raw.get("enabled", True)),
                max_workers=None if max_workers is None else max(1, int(max_workers)),
                revision=max(0, int(raw.get("revision", 0))),
                updated_at=str(raw.get("updated_at", "")),
            )
        except Exception as exc:
            # A malformed budget file must never broaden concurrency; fall back
            # to measured defaults and record why.
            app_logger.warning(f"Concurrency override file unreadable ({exc}); using measured defaults.")
            return ConcurrencyOverride()

    def _persist(self, override: ConcurrencyOverride) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(override.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self) -> ConcurrencyOverride:
        with self._lock:
            return ConcurrencyOverride(**self._override.to_dict())

    def update(self, patch: Dict[str, Any]) -> ConcurrencyOverride:
        if "enabled" in patch and not isinstance(patch["enabled"], bool):
            raise ValueError("enabled must be a boolean")
        if "max_workers" in patch and patch["max_workers"] is not None:
            value = patch["max_workers"]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("max_workers must be an integer or null")
        unknown = set(patch) - {"enabled", "max_workers"}
        if unknown:
            raise ValueError(f"Unknown concurrency budget field(s): {', '.join(sorted(unknown))}")
        with self._lock:
            current = self._override.to_dict()
            current.update(patch)
            merged = ConcurrencyOverride(
                enabled=bool(current["enabled"]),
                max_workers=None if current["max_workers"] is None else max(1, int(current["max_workers"])),
                revision=self._override.revision + 1,
                updated_at=_now(),
            )
            self._persist(merged)
            self._override = merged
            audit_logger.info(
                f"Owner concurrency budget updated: enabled={merged.enabled}, "
                f"max_workers={merged.max_workers}, revision={merged.revision}"
            )
            return self.get()


# Module-level singleton, mirroring owner_control_store / autonomy envelope stores.
concurrency_override_store = ConcurrencyOverrideStore()


class ConcurrencyGovernor:
    """Grants worker budgets from live pressure and runs measured parallel maps."""

    critical_ram_percent = 90.0
    high_ram_percent = 80.0
    moderate_ram_percent = 65.0
    critical_cpu_percent = 95.0
    high_cpu_percent = 80.0

    max_receipts = 200

    receipts_path = settings.DATA_DIR / "concurrency_receipts.jsonl"

    @classmethod
    def measure(
        cls,
        *,
        stats: Optional[Dict[str, Any]] = None,
        cpu_threads: Optional[int] = None,
        store: Optional[ConcurrencyOverrideStore] = None,
    ) -> Dict[str, Any]:
        live = stats if stats is not None else HardwareMonitor.get_hardware_stats()
        threads = int(cpu_threads) if cpu_threads else (psutil.cpu_count(logical=True) or 2)
        ram_total_gb = float(live.get("ram_total_gb") or 0.0)
        ram_percent = float(live.get("ram_percent") or 0.0)
        cpu_percent = float(live.get("cpu_percent") or 0.0)

        physical_cap = max(1, threads)
        # Leave headroom for the interactive runtime: half the logical threads.
        cpu_headroom_cap = max(1, threads // 2)
        base = 6 if ram_total_gb >= 40 else 3 if ram_total_gb >= 24 else 1
        base = min(base, cpu_headroom_cap)

        override = (store or concurrency_override_store).get()
        reasons: List[str] = []
        if override.max_workers is None:
            budget = base
        else:
            # Owner-configured budget: full authority within physical threads.
            budget = min(max(1, override.max_workers), physical_cap)
            if budget != override.max_workers:
                reasons.append(f"owner_max_workers_clamped_to_physical_{physical_cap}")
        if not override.enabled:
            budget = 1
            reasons.append("owner_disabled_parallelism")

        granted = budget
        if ram_percent >= cls.critical_ram_percent:
            granted = 1
            reasons.append("critical_ram_pressure_serial_only")
        elif ram_percent >= cls.high_ram_percent:
            granted = max(1, granted // 2)
            reasons.append("high_ram_pressure_halved")
        elif ram_percent >= cls.moderate_ram_percent:
            granted = max(1, (granted * 3 + 3) // 4)
            reasons.append("moderate_ram_pressure_scaled")
        if cpu_percent >= cls.critical_cpu_percent:
            granted = 1
            reasons.append("critical_cpu_pressure_serial_only")
        elif cpu_percent >= cls.high_cpu_percent and granted > 1:
            granted = max(1, granted // 2)
            reasons.append("high_cpu_pressure_halved")

        return {
            "success": True,
            "workers_granted": int(granted),
            "configured_budget": int(budget),
            "base_recommendation": int(base),
            "physical_thread_cap": physical_cap,
            "reasons": reasons,
            "measured": {
                "cpu_threads": threads,
                "ram_total_gb": round(ram_total_gb, 1),
                "ram_percent": round(ram_percent, 1),
                "cpu_percent": round(cpu_percent, 1),
                "sampled_at": _now(),
            },
            "owner_override": override.to_dict(),
        }

    @classmethod
    def _append_receipt(cls, receipt: Dict[str, Any], path: Optional[Path] = None) -> None:
        target = Path(path) if path is not None else cls.receipts_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            lines: List[str] = []
            if target.exists():
                lines = [ln for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()]
            lines.append(json.dumps(receipt))
            with target.open("w", encoding="utf-8") as fh:
                fh.write("\n".join(lines[-cls.max_receipts:]) + "\n")
        except Exception as exc:  # Receipt persistence must never break the workload.
            app_logger.warning(f"Could not persist concurrency receipt: {exc}")

    @classmethod
    def recent_receipts(cls, limit: int = 20, path: Optional[Path] = None) -> List[Dict[str, Any]]:
        target = Path(path) if path is not None else cls.receipts_path
        if not target.exists():
            return []
        try:
            lines = [ln for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()]
            return [json.loads(ln) for ln in lines[-max(1, min(limit, cls.max_receipts)):]]
        except Exception:
            return []

    @classmethod
    def run_parallel(
        cls,
        fn: Callable[[Any], Any],
        items: Sequence[Any],
        *,
        label: str,
        measurement: Optional[Dict[str, Any]] = None,
        receipts_path: Optional[Path] = None,
    ) -> Tuple[List[Any], Dict[str, Any]]:
        """Map ``fn`` over ``items`` with the measured worker budget.

        Order is always preserved and matches serial execution exactly. When the
        granted budget is 1 (or there is at most one item) the map runs serially;
        otherwise it uses a ThreadPoolExecutor sized by the grant.
        """
        measure = measurement if measurement is not None else cls.measure()
        granted = int(measure.get("workers_granted", 1))
        started = _now()
        started_monotonic = datetime.now(timezone.utc)
        parallel = granted > 1 and len(items) > 1
        if parallel:
            with ThreadPoolExecutor(max_workers=granted) as pool:
                results = list(pool.map(fn, items))
        else:
            results = [fn(item) for item in items]
        duration = (datetime.now(timezone.utc) - started_monotonic).total_seconds()
        reasons = list(measure.get("reasons", []))
        receipt = {
            "receipt_id": f"ccr_{uuid4().hex[:12]}",
            "label": str(label),
            "items": len(items),
            "workers_granted": granted,
            "parallel_executed": parallel,
            "serial_reason": None if parallel else (reasons[0] if reasons else ("single_item" if len(items) <= 1 else "budget_one")),
            "reasons": reasons,
            "measured": measure.get("measured", {}),
            "started_at": started,
            "duration_seconds": round(duration, 6),
        }
        cls._append_receipt(receipt, path=receipts_path)
        return results, receipt
