"""Phase 4/P1-F: Memory Learning & Reflection Integration Engine."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Dict, Any, List, Optional
from .memory import MemoryRecord, MemoryStore
from app.memory.reflection_engine import ReflectionEngine
from app.utils.logger import app_logger, audit_logger

@dataclass(frozen=True)
class Lesson:
    content: str
    importance: float
    tags: tuple[str, ...] = ()

class MemoryLearner:
    """
    P1-F: Reflection & Memory Learning Integration.
    Feeds prediction error surprisal outcomes and execution tracebacks into ReflectionEngine
    to extract procedural lessons learned into permanent MemoryStore.
    """

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.reflection = ReflectionEngine()

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

    def process_outcome_reflection(
        self,
        task_title: str,
        goal: str,
        outcome_summary: str,
        surprisal: float = 0.0
    ) -> MemoryRecord:
        """
        Feeds execution outcomes into ReflectionEngine, extracts lessons learned, and stores in MemoryStore.
        """
        ref_res = self.reflection.reflect_on_task_execution(
            task_title=task_title,
            task_goal=goal,
            outcome_summary=f"Surprisal: {surprisal:.2f}. {outcome_summary}"
        )

        lesson_text = f"Lesson [{task_title}]: {ref_res.get('key_takeaway', outcome_summary)}"
        importance = 0.9 if surprisal > 0.3 else 0.6

        audit_logger.info(f"MemoryLearner processed outcome reflection for '{task_title}' (Lesson saved)")
        return self.learn_lesson(Lesson(content=lesson_text, importance=importance, tags=(task_title.lower(),)))

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
