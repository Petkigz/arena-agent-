"""Lightweight in-process event bus for Arena's cognitive systems."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Callable, DefaultDict, List, Union, Optional

from .events import CognitiveEvent
from app.utils.logger import app_logger

Handler = Callable[[CognitiveEvent], None]
EventKey = Union[str, type]


class EventBus:
    """
    P1-C: Event-Driven State Synchronization Bus.
    Broadcasting cognitive state transitions, observation updates, prediction errors,
    and tool execution events asynchronously across all modules.
    """

    def __init__(self) -> None:
        self._handlers: DefaultDict[str, List[Handler]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, event_type: str, handler: Handler) -> Callable[[], None]:
        if not event_type:
            raise ValueError("event_type cannot be empty")
        with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)

        def unsubscribe() -> None:
            self.unsubscribe(event_type, handler)

        return unsubscribe

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        with self._lock:
            handlers = self._handlers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(self, event: CognitiveEvent) -> None:
        with self._lock:
            handlers = list(self._handlers.get(event.event_type, []))
            handlers += list(self._handlers.get("*", []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                app_logger.warning(f"EventBus subscriber exception for '{event.event_type}': {e}")
                continue

    def emit(self, event_type: str, data: Optional[dict] = None, source: Optional[str] = "system") -> None:
        """Helper method to construct and publish a CognitiveEvent."""
        evt = CognitiveEvent(
            event_type=event_type,
            data=data or {},
            source=source
        )
        self.publish(evt)

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()
