"""Lightweight in-process event bus for Arena's cognitive systems."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Callable, DefaultDict, List, Union

from .events import CognitiveEvent

Handler = Callable[[CognitiveEvent], None]
EventKey = Union[str, type]


class EventBus:
    """Synchronous by default, intentionally simple for Phase 1.

    Handlers should be fast and side-effect aware. An exception in one
    subscriber is isolated so it cannot prevent other subscribers from
    receiving the event.
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
            except Exception:
                # Phase 1 intentionally keeps event delivery resilient.
                # Production logging/telemetry will be attached later.
                continue

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()
