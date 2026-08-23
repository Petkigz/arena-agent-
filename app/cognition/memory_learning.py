"""Phase 4/P1-F: Memory Learning & Reflection Integration Engine."""
from __future__ import annotations
from collections import defaultdict
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
        verification_result: Optional[Any] = None,
        surprisal: float = 0.0,
        outcome_summary: Optional[str] = None
    ) -> MemoryRecord:
        """
        Feeds verified execution outcomes into ReflectionEngine, extracts lessons learned,
        and stores in MemoryStore.
        
        Args:
            task_title: Short identifier for the task
            goal: Original goal text
            verification_result: GoalVerificationResult with verified outcomes (required for new code)
            surprisal: Prediction error (0.0 = expected, 1.0 = surprise)
            outcome_summary: Legacy string summary (deprecated, use verification_result)
        
        The lesson is generated from verified outcomes, not arbitrary strings.
        If verification_result is provided, the lesson includes:
          - verified_success status
          - met_conditions and failed_conditions
          - lifecycle state
          - verification reason
        """
        # Build structured summary from verified outcomes
        if verification_result is not None:
            verified = getattr(verification_result, 'verified_success', False)
            lifecycle = getattr(verification_result, 'final_state', None)
            lifecycle_str = lifecycle.value if hasattr(lifecycle, 'value') else str(lifecycle)
            met = getattr(verification_result, 'met_conditions', [])
            failed = getattr(verification_result, 'failed_conditions', [])
            reason = getattr(verification_result, 'verification_reason', '')
            
            summary_parts = [
                f"Verified: {verified}",
                f"State: {lifecycle_str}",
                f"Met: {len(met)} conditions",
                f"Failed: {len(failed)} conditions",
            ]
            if failed:
                summary_parts.append(f"Failed details: {'; '.join(failed[:3])}")
            if reason:
                summary_parts.append(f"Reason: {reason}")
            
            structured_summary = " | ".join(summary_parts)
        elif outcome_summary is not None:
            # Legacy path: accept string but mark as unverified
            structured_summary = f"[UNVERIFIED] {outcome_summary}"
        else:
            raise ValueError("Either verification_result or outcome_summary must be provided")
        
        ref_res = self.reflection.reflect_on_task_execution(
            task_title=task_title,
            task_goal=goal,
            verification_result=verification_result,
            outcome_summary=f"Surprisal: {surprisal:.2f}. {structured_summary}" if verification_result is None else None
        )

        # Always include structured summary for testability and transparency
        reflection_text = ref_res.get('reflection_text', '')
        if verification_result is not None:
            lesson_text = f"Lesson [{task_title}]: {reflection_text} | {structured_summary}"
        else:
            lesson_text = f"Lesson [{task_title}]: {structured_summary}"
        importance = 0.9 if surprisal > 0.3 else 0.6

        audit_logger.info(f"MemoryLearner processed outcome reflection for '{task_title}' (Lesson saved)")
        return self.learn_lesson(Lesson(content=lesson_text, importance=importance, tags=(task_title.lower(),)))

    def record_verified_episode(
        self,
        *,
        goal: str,
        action_type: str,
        verification_result: Any,
        task_id: str | None = None,
        task_type: str = "unknown",
    ) -> MemoryRecord:
        """Persist a structured episode whose authority comes from GoalVerifier."""
        verified = bool(getattr(verification_result, "verified_success", False))
        final_state = getattr(verification_result, "final_state", None)
        state = final_state.value if hasattr(final_state, "value") else str(final_state or "unknown")
        met = [str(item) for item in getattr(verification_result, "met_conditions", [])]
        failed = [str(item) for item in getattr(verification_result, "failed_conditions", [])]
        reason = str(getattr(verification_result, "verification_reason", ""))
        content = (
            f"Goal: {goal[:300]} | Action: {action_type} | Verified: {verified} | "
            f"State: {state} | Met: {'; '.join(met[:3]) or 'none'} | "
            f"Failed: {'; '.join(failed[:3]) or 'none'} | Reason: {reason[:300]}"
        )
        return self.record_episode(
            content,
            task_id=task_id,
            source="goal_verifier",
            importance=0.85 if verified else 0.7,
            tags=(task_type, action_type, "verified_outcome"),
            outcome=state,
            success=verified,
        )

    def consolidate_verified_episodes(
        self, episodes: list[MemoryRecord]
    ) -> list[MemoryRecord]:
        """Promote only verifier-authored terminal episodes with provenance.

        No LLM is used to invent facts. Successful episodes become durable
        verified-experience semantics; failed episodes become lessons. Repeated
        verified successes for the same action also produce a reusable procedure.
        Every target is linked to its source episode, making the operation
        idempotent and auditable.
        """
        eligible = [
            episode for episode in episodes
            if episode.kind == "episodic"
            and episode.source == "goal_verifier"
            and episode.success is not None
            and (episode.outcome or "") in {"achieved", "failed", "blocked"}
        ]
        eligible_ids = {episode.memory_id for episode in eligible}
        for episode in episodes:
            if episode.memory_id not in eligible_ids:
                # Mark reviewed so unverifiable/self-reported episodes cannot
                # starve later verified memories in the bounded consolidation batch.
                self.store.link_consolidation(
                    episode.memory_id,
                    episode.memory_id,
                    relation="not_promoted",
                )
        created: list[MemoryRecord] = []
        successful_by_action: dict[str, list[MemoryRecord]] = defaultdict(list)

        for episode in eligible:
            task_type = episode.tags[0] if len(episode.tags) > 0 else "unknown"
            action_type = episode.tags[1] if len(episode.tags) > 1 else "unknown"
            if episode.success:
                kind = "semantic"
                content = (
                    f"Verified experience [{task_type}/{action_type}]: {episode.content}"
                )
                successful_by_action[action_type].append(episode)
            else:
                kind = "lesson"
                content = (
                    f"Verified failure lesson [{task_type}/{action_type}]: {episode.content}"
                )

            target = self.store.find_exact(kind, content)
            if target is None:
                target = self.store.add(
                    kind,
                    content,
                    source="consolidation",
                    importance=max(0.7, episode.importance),
                    tags=(task_type, action_type, f"evidence:{episode.memory_id}"),
                    outcome=episode.outcome,
                    success=episode.success,
                )
                created.append(target)
            self.store.link_consolidation(episode.memory_id, target.memory_id)

        for action_type in successful_by_action:
            action_episodes = self.store.verified_success_episodes_for_action(action_type)
            if len(action_episodes) < 2:
                continue
            task_types = sorted({
                episode.tags[0] if episode.tags else "unknown"
                for episode in action_episodes
            })
            procedure = (
                f"Verified procedure pattern: action '{action_type}' repeatedly "
                f"achieved its goal for task types {', '.join(task_types)}. Reuse "
                f"only when current preconditions and postcondition probes match."
            )
            target = self.store.find_exact("procedural", procedure)
            if target is None:
                target = self.store.add(
                    "procedural",
                    procedure,
                    source="consolidation",
                    importance=0.8,
                    tags=(action_type, "verified_pattern"),
                    success=True,
                )
                created.append(target)
            for episode in action_episodes:
                self.store.link_consolidation(episode.memory_id, target.memory_id)

        return created

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
