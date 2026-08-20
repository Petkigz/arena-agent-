"""Phase 3B: Analogical Reasoning.

Finds structurally similar past tasks when facing a new one.
"This is like that time I..." triggers relevant memory retrieval.

Structural similarity is based on:
- Same intent_type (action_intent, search_intent, etc.)
- Similar entity types (process, file, etc.)
- Similar constraint patterns
- Similar target domains

NOT surface-level keyword matching.
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
class TaskSignature:
    """Structural fingerprint of a task — used for analogical matching."""
    task_id: str
    intent_type: str          # "action_intent", "search_intent", etc.
    target_domain: str        # "desktop_os", "filesystem", "web", etc.
    entity_types: Tuple[str, ...]  # ("process",) or ("file",)
    action_type: str          # "open_application", "search_files", etc.
    success: bool
    strategy_count: int       # how many strategies were tried
    outcome: str              # "achieved", "failed", "blocked", etc.
    goal_text: str            # original user request (truncated)
    timestamp: str = field(default_factory=_now)

    def structural_key(self) -> Tuple[str, str, Tuple[str, ...]]:
        """Key for structural matching (ignores specific entities)."""
        return (self.intent_type, self.target_domain, self.entity_types)

    def similarity_to(self, other: 'TaskSignature') -> float:
        """
        Compute structural similarity (0.0-1.0) between two task signatures.
        Higher = more structurally similar.
        """
        score = 0.0
        max_score = 0.0

        # Intent type match (weight: 0.35)
        max_score += 0.35
        if self.intent_type == other.intent_type:
            score += 0.35

        # Target domain match (weight: 0.25)
        max_score += 0.25
        if self.target_domain == other.target_domain:
            score += 0.25

        # Entity type overlap (weight: 0.25)
        max_score += 0.25
        if self.entity_types and other.entity_types:
            self_set = set(self.entity_types)
            other_set = set(other.entity_types)
            if self_set and other_set:
                overlap = len(self_set & other_set) / len(self_set | other_set)
                score += 0.25 * overlap

        # Outcome agreement (weight: 0.15) — similar outcomes suggest similar difficulty
        max_score += 0.15
        if self.outcome == other.outcome:
            score += 0.15

        return score / max_score if max_score > 0 else 0.0


@dataclass(frozen=True)
class AnalogyMatch:
    """A past task that is structurally similar to the current one."""
    past_task: TaskSignature
    similarity: float
    insight: str  # "This succeeded using search_files" or "This failed 3 times with open_application"


class AnalogicalMemory:
    """
    Stores task signatures and retrieves structurally similar past tasks.
    Enables analogical reasoning: 'this task is like that previous one.'
    """

    MIN_SIMILARITY = 0.4  # Minimum similarity to report a match

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path
        self._signatures: List[TaskSignature] = []
        if self.db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_signatures (
                task_id TEXT PRIMARY KEY,
                intent_type TEXT NOT NULL,
                target_domain TEXT NOT NULL,
                entity_types TEXT NOT NULL,
                action_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                strategy_count INTEGER NOT NULL DEFAULT 1,
                outcome TEXT NOT NULL DEFAULT '',
                goal_text TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sigs_intent_domain
            ON task_signatures(intent_type, target_domain)
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""SELECT task_id, intent_type, target_domain, entity_types,
            action_type, success, strategy_count, outcome, goal_text, timestamp
            FROM task_signatures ORDER BY timestamp""")
        for row in cursor.fetchall():
            try:
                et = tuple(json.loads(row[3]))
            except Exception:
                et = ()
            self._signatures.append(TaskSignature(
                task_id=row[0], intent_type=row[1], target_domain=row[2],
                entity_types=et, action_type=row[4], success=bool(row[5]),
                strategy_count=row[6], outcome=row[7], goal_text=row[8],
                timestamp=row[9]
            ))
        conn.close()

    def _save_to_db(self, sig: TaskSignature) -> None:
        if not self.db_path:
            return
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO task_signatures
            (task_id, intent_type, target_domain, entity_types, action_type,
             success, strategy_count, outcome, goal_text, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (sig.task_id, sig.intent_type, sig.target_domain,
              json.dumps(list(sig.entity_types)), sig.action_type,
              int(sig.success), sig.strategy_count, sig.outcome,
              sig.goal_text, sig.timestamp))
        conn.commit()
        conn.close()

    def record_task(
        self,
        intent_type: str,
        target_domain: str,
        entity_types: List[str],
        action_type: str,
        success: bool,
        outcome: str = "",
        goal_text: str = "",
        strategy_count: int = 1
    ) -> TaskSignature:
        """Record a completed task's structural signature."""
        sig = TaskSignature(
            task_id=uuid4().hex[:12],
            intent_type=intent_type,
            target_domain=target_domain,
            entity_types=tuple(entity_types),
            action_type=action_type,
            success=success,
            strategy_count=strategy_count,
            outcome=outcome,
            goal_text=goal_text[:200]
        )
        self._signatures.append(sig)
        self._save_to_db(sig)
        return sig

    def find_analogies(
        self,
        intent_type: str,
        target_domain: str,
        entity_types: List[str],
        exclude_action: Optional[str] = None,
        limit: int = 5,
        min_similarity: Optional[float] = None
    ) -> List[AnalogyMatch]:
        """
        Find past tasks structurally similar to the described task.
        Returns matches sorted by similarity (highest first).
        """
        threshold = min_similarity or self.MIN_SIMILARITY
        query_sig = TaskSignature(
            task_id="query", intent_type=intent_type, target_domain=target_domain,
            entity_types=tuple(entity_types), action_type="",
            success=True, strategy_count=0, outcome="", goal_text=""
        )

        matches: List[AnalogyMatch] = []
        for past in self._signatures:
            if exclude_action and past.action_type == exclude_action:
                continue
            sim = query_sig.similarity_to(past)
            if sim >= threshold:
                insight = self._generate_insight(past)
                matches.append(AnalogyMatch(past_task=past, similarity=sim, insight=insight))

        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches[:limit]

    def _generate_insight(self, past: TaskSignature) -> str:
        """Generate a human-readable insight from a past task."""
        if past.success:
            return f"Previously succeeded using '{past.action_type}' for similar {past.intent_type} task in {past.target_domain}"
        else:
            return f"Previously failed using '{past.action_type}' ({past.outcome}) for similar {past.intent_type} task"

    def what_worked_for(self, intent_type: str, target_domain: str) -> Optional[Dict[str, Any]]:
        """
        Find the most successful strategy for structurally similar tasks.
        Returns the action_type and context of the best past success.
        """
        successes = [
            sig for sig in self._signatures
            if sig.intent_type == intent_type
            and sig.target_domain == target_domain
            and sig.success
        ]
        if not successes:
            return None

        # Group by action_type and count successes
        action_counts: Dict[str, int] = {}
        for sig in successes:
            action_counts[sig.action_type] = action_counts.get(sig.action_type, 0) + 1

        best_action = max(action_counts, key=action_counts.get)
        return {
            "action_type": best_action,
            "times_succeeded": action_counts[best_action],
            "intent_type": intent_type,
            "target_domain": target_domain,
        }

    def what_failed_for(self, intent_type: str, target_domain: str) -> List[Dict[str, Any]]:
        """Find all strategies that failed for structurally similar tasks."""
        failures = [
            sig for sig in self._signatures
            if sig.intent_type == intent_type
            and sig.target_domain == target_domain
            and not sig.success
        ]

        action_failures: Dict[str, Dict[str, Any]] = {}
        for sig in failures:
            if sig.action_type not in action_failures:
                action_failures[sig.action_type] = {
                    "action_type": sig.action_type,
                    "times_failed": 0,
                    "outcomes": set(),
                }
            action_failures[sig.action_type]["times_failed"] += 1
            if sig.outcome:
                action_failures[sig.action_type]["outcomes"].add(sig.outcome)

        result = []
        for info in action_failures.values():
            info["outcomes"] = list(info["outcomes"])
            result.append(info)
        result.sort(key=lambda x: x["times_failed"], reverse=True)
        return result

    def total_signatures(self) -> int:
        return len(self._signatures)
