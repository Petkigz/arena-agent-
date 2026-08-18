"""Post-task reflection hooks for turning experience into reviewable lessons."""
from __future__ import annotations
from dataclasses import dataclass
from .memory import MemoryRecord
from .memory_learning import Lesson

@dataclass(frozen=True)
class Reflection:
    summary: str
    lesson: Lesson | None = None
    unresolved: tuple[str, ...] = ()

class ReflectionEngine:
    """Keeps reflection explicit; it never silently invents facts from a trace."""
    def reflect(self, memories: list[MemoryRecord], *, summary: str, lesson: Lesson | None = None,
                unresolved: tuple[str, ...] = ()) -> Reflection:
        return Reflection(summary=summary, lesson=lesson, unresolved=unresolved)
