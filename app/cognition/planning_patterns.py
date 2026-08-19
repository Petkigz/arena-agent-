"""Phase 3C: Domain-General Planning Patterns.

Extracts reusable planning patterns from successful multi-step task sequences.
Patterns like "search → verify → fallback_search" are transferable across domains.

A planning pattern is:
  1. A sequence of action_types that were tried
  2. Whether the overall task succeeded
  3. Which step in the sequence was the one that succeeded
  4. The intent_type/domain context

These patterns are reusable: if [search_files, web_search] worked for
search_intent/filesystem, the same pattern can be suggested for
search_intent/web tasks.
"""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PlanningPattern:
    """A reusable sequence of actions that led to a specific outcome."""
    pattern_id: str
    intent_type: str             # "search_intent", "action_intent", etc.
    action_sequence: Tuple[str, ...]  # ("search_files", "web_search")
    successful_step: int         # index of the step that achieved the goal (-1 if all failed)
    success: bool                # did the overall task succeed?
    times_used: int              # how many times this exact pattern was used
    success_rate: float          # what fraction of uses succeeded
    last_used: str = field(default_factory=_now)

    def sequence_key(self) -> Tuple[str, Tuple[str, ...]]:
        """Key for matching identical patterns across intents."""
        return (self.intent_type, self.action_sequence)


@dataclass(frozen=True)
class PatternSuggestion:
    """A suggested planning pattern for a new task."""
    pattern: PlanningPattern
    relevance: float  # 0.0-1.0, how relevant this pattern is
    reason: str       # why this pattern was suggested


class PlanningPatternStore:
    """
    Stores and retrieves reusable planning patterns.
    Patterns generalize across domains — a successful pattern for
    code tasks can be suggested for research tasks.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._patterns: List[PlanningPattern] = []
        self._usage_count: Dict[str, int] = {}   # pattern_id → total uses
        self._success_count: Dict[str, int] = {}  # pattern_id → successful uses
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS planning_patterns (
                pattern_id TEXT PRIMARY KEY,
                intent_type TEXT NOT NULL,
                action_sequence TEXT NOT NULL,
                successful_step INTEGER NOT NULL DEFAULT -1,
                success INTEGER NOT NULL,
                times_used INTEGER NOT NULL DEFAULT 1,
                success_rate REAL NOT NULL DEFAULT 1.0,
                last_used TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_patterns_intent
            ON planning_patterns(intent_type)
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""SELECT pattern_id, intent_type, action_sequence,
            successful_step, success, times_used, success_rate, last_used
            FROM planning_patterns ORDER BY last_used DESC""")
        for row in cursor.fetchall():
            try:
                seq = tuple(json.loads(row[2]))
            except Exception:
                seq = ()
            p = PlanningPattern(
                pattern_id=row[0], intent_type=row[1], action_sequence=seq,
                successful_step=row[3], success=bool(row[4]),
                times_used=row[5], success_rate=row[6], last_used=row[7]
            )
            self._patterns.append(p)
            self._usage_count[p.pattern_id] = p.times_used
            self._success_count[p.pattern_id] = int(p.times_used * p.success_rate)
        conn.close()

    def _save_to_db(self, pattern: PlanningPattern) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO planning_patterns
            (pattern_id, intent_type, action_sequence, successful_step,
             success, times_used, success_rate, last_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (pattern.pattern_id, pattern.intent_type,
              json.dumps(list(pattern.action_sequence)),
              pattern.successful_step, int(pattern.success),
              pattern.times_used, pattern.success_rate, pattern.last_used))
        conn.commit()
        conn.close()

    def record_sequence(
        self,
        intent_type: str,
        action_sequence: List[str],
        success: bool,
        successful_step: int = -1
    ) -> PlanningPattern:
        """
        Record a completed action sequence and its outcome.
        If the exact pattern exists, update its statistics.
        If not, create a new pattern.
        """
        seq_tuple = tuple(action_sequence)
        now = _now()

        # Check if this exact pattern already exists
        for i, existing in enumerate(self._patterns):
            if existing.intent_type == intent_type and existing.action_sequence == seq_tuple:
                # Update existing pattern
                self._usage_count[existing.pattern_id] = self._usage_count.get(existing.pattern_id, 0) + 1
                if success:
                    self._success_count[existing.pattern_id] = self._success_count.get(existing.pattern_id, 0) + 1

                total = self._usage_count[existing.pattern_id]
                successes = self._success_count.get(existing.pattern_id, 0)
                rate = successes / total if total > 0 else 0.0

                updated = PlanningPattern(
                    pattern_id=existing.pattern_id,
                    intent_type=intent_type,
                    action_sequence=seq_tuple,
                    successful_step=successful_step if success else existing.successful_step,
                    success=success or existing.success,
                    times_used=total,
                    success_rate=round(rate, 4),
                    last_used=now
                )
                self._patterns[i] = updated
                self._save_to_db(updated)
                return updated

        # New pattern
        pid = uuid4().hex[:12]
        self._usage_count[pid] = 1
        self._success_count[pid] = 1 if success else 0
        pattern = PlanningPattern(
            pattern_id=pid,
            intent_type=intent_type,
            action_sequence=seq_tuple,
            successful_step=successful_step,
            success=success,
            times_used=1,
            success_rate=1.0 if success else 0.0,
            last_used=now
        )
        self._patterns.append(pattern)
        self._save_to_db(pattern)
        return pattern

    def suggest_patterns(
        self,
        intent_type: str,
        first_action: Optional[str] = None,
        limit: int = 5
    ) -> List[PatternSuggestion]:
        """
        Suggest planning patterns for a new task with the given intent_type.
        If first_action is provided, prefer patterns that start with that action.
        Returns patterns sorted by relevance (success_rate × times_used).
        """
        candidates: List[PatternSuggestion] = []

        for pattern in self._patterns:
            if pattern.intent_type != intent_type:
                continue
            if not pattern.success:
                continue  # Only suggest successful patterns

            relevance = pattern.success_rate * min(pattern.times_used / 3.0, 1.0)

            # Bonus for matching first action
            if first_action and pattern.action_sequence and pattern.action_sequence[0] == first_action:
                relevance *= 1.3

            reason = f"Pattern {list(pattern.action_sequence)} succeeded {pattern.times_used}× ({pattern.success_rate:.0%} rate)"
            candidates.append(PatternSuggestion(
                pattern=pattern, relevance=relevance, reason=reason
            ))

        candidates.sort(key=lambda s: s.relevance, reverse=True)
        return candidates[:limit]

    def cross_domain_patterns(
        self, source_intent: str, target_intent: str, limit: int = 5
    ) -> List[PatternSuggestion]:
        """
        Find patterns from source_intent that might transfer to target_intent.
        Patterns that work across domains are the most valuable.
        """
        # Get successful patterns from source
        source_patterns = [
            p for p in self._patterns
            if p.intent_type == source_intent and p.success and p.times_used >= 2
        ]

        # Check if same pattern exists (and failed) in target
        target_failures = set()
        for p in self._patterns:
            if p.intent_type == target_intent and not p.success:
                target_failures.add(p.action_sequence)

        suggestions: List[PatternSuggestion] = []
        for pattern in source_patterns:
            if pattern.action_sequence in target_failures:
                continue  # Don't suggest patterns that already failed in target

            relevance = pattern.success_rate * min(pattern.times_used / 3.0, 1.0) * 0.8  # Cross-domain penalty
            reason = (f"Cross-domain: {list(pattern.action_sequence)} worked for "
                      f"'{source_intent}' ({pattern.times_used}×, {pattern.success_rate:.0%}), "
                      f"may transfer to '{target_intent}'")
            suggestions.append(PatternSuggestion(
                pattern=pattern, relevance=relevance, reason=reason
            ))

        suggestions.sort(key=lambda s: s.relevance, reverse=True)
        return suggestions[:limit]

    def total_patterns(self) -> int:
        return len(self._patterns)

    def successful_patterns(self, intent_type: Optional[str] = None) -> List[PlanningPattern]:
        """List all successful patterns, optionally filtered by intent_type."""
        result = [p for p in self._patterns if p.success]
        if intent_type:
            result = [p for p in result if p.intent_type == intent_type]
        return sorted(result, key=lambda p: p.success_rate * p.times_used, reverse=True)
