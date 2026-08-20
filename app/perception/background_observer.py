"""Phase 4A: Background Observation Loop.

A daemon thread that periodically probes the environment and detects changes.
Changes are published via EventBus as EnvironmentChangeEvent for cognitive evaluation.

Observation frequency adapts to importance: active tasks get more frequent probes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from app.utils.logger import app_logger


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Environment Change Events ────────────────────────────────────────

@dataclass(frozen=True)
class EnvironmentChange:
    """A detected change in the environment."""
    change_id: str
    change_type: str         # "process_started", "process_stopped", "file_changed", "device_connected", etc.
    subject: str             # entity name or identifier
    previous_state: Any      # what it was before (None if new)
    current_state: Any       # what it is now
    source: str              # probe that detected it
    confidence: float = 1.0
    priority: str = "normal" # "urgent", "normal", "informational"
    timestamp: str = field(default_factory=_now)

    def is_urgent(self) -> bool:
        return self.priority == "urgent"


# ── Probe Interface ──────────────────────────────────────────────────

class EnvironmentProbe:
    """Base class for environment probes. Subclass and implement probe()."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._last_state: Dict[str, Any] = {}

    def probe(self) -> Dict[str, Any]:
        """Return current environment state as {subject: state_dict}."""
        raise NotImplementedError

    def detect_changes(self, current: Dict[str, Any]) -> List[EnvironmentChange]:
        """Compare current state against last known state, return changes."""
        changes: List[EnvironmentChange] = []

        # Detect new or changed subjects
        for subject, state in current.items():
            if subject not in self._last_state:
                changes.append(EnvironmentChange(
                    change_id=uuid4().hex[:12],
                    change_type="appeared",
                    subject=subject,
                    previous_state=None,
                    current_state=state,
                    source=self.name,
                    priority=self._classify_priority(subject, None, state)
                ))
            elif self._last_state[subject] != state:
                changes.append(EnvironmentChange(
                    change_id=uuid4().hex[:12],
                    change_type="changed",
                    subject=subject,
                    previous_state=self._last_state[subject],
                    current_state=state,
                    source=self.name,
                    priority=self._classify_priority(subject, self._last_state[subject], state)
                ))

        # Detect disappeared subjects
        for subject in self._last_state:
            if subject not in current:
                changes.append(EnvironmentChange(
                    change_id=uuid4().hex[:12],
                    change_type="disappeared",
                    subject=subject,
                    previous_state=self._last_state[subject],
                    current_state=None,
                    source=self.name,
                    priority=self._classify_priority(subject, self._last_state[subject], None)
                ))

        self._last_state = dict(current)
        return changes

    def _classify_priority(self, subject: str, old: Any, new: Any) -> str:
        """Classify change priority. Override in subclasses for domain-specific rules."""
        if new is None:
            return "normal"  # Something disappeared
        if old is None:
            return "normal"  # Something appeared
        return "informational"


class ProcessProbe(EnvironmentProbe):
    """Monitors running processes."""

    def __init__(self) -> None:
        super().__init__("process_probe")

    def probe(self) -> Dict[str, Any]:
        try:
            import psutil
            processes = {}
            for proc in psutil.process_iter(['pid', 'name', 'status']):
                try:
                    info = proc.info
                    name = (info['name'] or "").lower()
                    if name:
                        processes[name] = {
                            "pid": info['pid'],
                            "status": info['status'],
                        }
                except Exception:
                    continue
            return processes
        except ImportError:
            return {}


class SystemResourceProbe(EnvironmentProbe):
    """Monitors CPU, memory, disk usage."""

    def __init__(self) -> None:
        super().__init__("system_resource_probe")

    def probe(self) -> Dict[str, Any]:
        try:
            import psutil
            return {
                "cpu": {"percent": psutil.cpu_percent(interval=0)},
                "memory": {"percent": psutil.virtual_memory().percent,
                           "available_mb": psutil.virtual_memory().available // (1024 * 1024)},
                "disk": {"percent": psutil.disk_usage("/").percent},
            }
        except ImportError:
            return {}


# ── Background Observer ──────────────────────────────────────────────

class BackgroundObserver:
    """
    Daemon thread that periodically runs environment probes, detects changes,
    and publishes EnvironmentChange events.

    Usage:
        observer = BackgroundObserver(event_bus=bus)
        observer.add_probe(ProcessProbe())
        observer.start()
        # ... later ...
        observer.stop()
    """

    DEFAULT_INTERVAL = 30.0   # seconds between probe cycles
    ACTIVE_INTERVAL = 10.0    # faster when active tasks exist
    MIN_INTERVAL = 5.0        # never probe faster than this

    def __init__(
        self,
        event_bus: Optional[Any] = None,
        interval: float = DEFAULT_INTERVAL,
        on_change: Optional[Callable[[EnvironmentChange], None]] = None
    ) -> None:
        self._probes: List[EnvironmentProbe] = []
        self._event_bus = event_bus
        self._on_change = on_change
        self._interval = interval
        self._active_tasks: int = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._changes: List[EnvironmentChange] = []
        self._lock = threading.Lock()
        self._cycle_count: int = 0

    def add_probe(self, probe: EnvironmentProbe) -> None:
        """Register an environment probe."""
        self._probes.append(probe)

    def set_active_tasks(self, count: int) -> None:
        """Update the number of active tasks (affects probe frequency)."""
        self._active_tasks = max(0, count)

    @property
    def current_interval(self) -> float:
        """Current probe interval, adapting to active task count."""
        if self._active_tasks > 0:
            return max(self.MIN_INTERVAL, self.ACTIVE_INTERVAL)
        return self._interval

    def start(self) -> None:
        """Start the background observation loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="BackgroundObserver")
        self._thread.start()
        app_logger.info(f"BackgroundObserver started with {len(self._probes)} probe(s), interval={self._interval}s")

    def stop(self) -> None:
        """Stop the background observation loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def run_once(self) -> List[EnvironmentChange]:
        """Run a single probe cycle (useful for testing without threading)."""
        return self._probe_cycle()

    def get_changes(self, clear: bool = True) -> List[EnvironmentChange]:
        """Get accumulated changes, optionally clearing the buffer."""
        with self._lock:
            changes = list(self._changes)
            if clear:
                self._changes.clear()
            return changes

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    def _loop(self) -> None:
        """Main observation loop — runs in daemon thread."""
        while self._running:
            try:
                self._probe_cycle()
            except Exception as e:
                app_logger.warning(f"BackgroundObserver probe cycle error: {e}")

            time.sleep(self.current_interval)

    def _probe_cycle(self) -> List[EnvironmentChange]:
        """Run all probes and detect changes."""
        all_changes: List[EnvironmentChange] = []

        for probe in self._probes:
            try:
                current_state = probe.probe()
                changes = probe.detect_changes(current_state)
                all_changes.extend(changes)
            except Exception as e:
                app_logger.warning(f"BackgroundObserver probe '{probe.name}' error: {e}")

        self._cycle_count += 1

        # Publish changes
        for change in all_changes:
            with self._lock:
                self._changes.append(change)

            # Notify via event bus
            if self._event_bus:
                try:
                    self._event_bus.emit(
                        event_type=f"environment.{change.change_type}",
                        data={
                            "change_id": change.change_id,
                            "subject": change.subject,
                            "change_type": change.change_type,
                            "previous_state": change.previous_state,
                            "current_state": change.current_state,
                            "source": change.source,
                            "priority": change.priority,
                        },
                        source=change.source
                    )
                except Exception as e:
                    app_logger.warning(f"BackgroundObserver event publish error: {e}")

            # Notify via callback
            if self._on_change:
                try:
                    self._on_change(change)
                except Exception as e:
                    app_logger.warning(f"BackgroundObserver on_change callback error: {e}")

        return all_changes
