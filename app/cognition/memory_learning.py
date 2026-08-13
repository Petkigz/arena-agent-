"""Phase 4 memory consolidation and lightweight experience learning."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from .memory import MemoryRecord, MemoryStore

@dataclass(frozen=True)
class Lesson:
    content: str
    importance: float
    tags: tuple[str, ...] = ()

class MemoryLearner:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def record_episode(self, content: str, *, task_id: str | None = None, source: str | None = None,
                       importance: float = 0.5, tags: Iterable[str] = (), outcome: str | None = None,
                       success: bool | None = None) -> MemoryRecord:
        return self.store.add("episodic", content, task_id=task_id, source=source,
                              importance=importance, tags=tuple(tags), outcome=outcome, success=success)

    def learn_lesson(self, lesson: Lesson, *, source: str = "reflection") -> MemoryRecord:
        return self.store.add("lesson", lesson.content, source=source, importance=lesson.importance, tags=lesson.tags)

    def learn_procedure(self, procedure: str, *, importance: float = 0.7, tags: Iterable[str] = (),
                        source: str = "experience") -> MemoryRecord:
        return self.store.add("procedural", procedure, source=source, importance=importance, tags=tuple(tags))

    def consolidate(self, episodes: list[MemoryRecord], *, semantic_facts: Iterable[str] = (),
                    procedures: Iterable[str] = (), lessons: Iterable[Lesson] = ()) -> list[MemoryRecord]:
        """Promote selected experience into durable knowledge; callers decide what is justified."""
        created: list[MemoryRecord] = []
        for fact in semantic_facts:
            created.append(self.store.add("semantic", fact, source="consolidation", importance=0.7))
        for procedure in procedures:
            created.append(self.learn_procedure(procedure, source="consolidation"))
        for lesson in lessons:
            created.append(self.learn_lesson(lesson))
        return created

    def retrieve_for_task(self, task_description: str, *, limit: int = 8) -> list[MemoryRecord]:
        return self.store.search(task_description, limit=limit)
