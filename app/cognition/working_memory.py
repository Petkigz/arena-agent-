"""Working memory: a capacity-limited, decaying attention scratchpad.

Long-term stores persist; working memory is deliberately VOLATILE — it holds
the small set of currently-attended items the reasoning loop needs right now,
exactly like human working memory: limited capacity (~7±2), fading activation,
rehearsal refresh, and attention gating (only salient, goal-relevant, novel
items get in).

Honesty rules:
  * Every item carries its source evidence (user query, perception summary,
    retrieved memory id, grounding id) — nothing enters without provenance.
  * Displacement and decay are measured and reportable, not vibes: activation
    halves every half_life seconds; items below the forgetting floor drop;
    over-capacity inserts evict the lowest-activation item.
  * The scratchpad dies with the process by design — that is what working
    memory IS; durable knowledge belongs to the long-term stores.
"""
from __future__ import annotations

import math
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.config import settings
from app.utils.logger import app_logger


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorkingMemoryItem:
    item_id: str
    content: str
    kind: str  # user_query | observation | retrieved_memory | grounding | goal | system
    source: str  # provenance evidence string
    salience: float
    activation: float = 1.0
    access_count: int = 0
    created_at: str = field(default_factory=lambda: _now_dt().isoformat())
    last_refreshed_at: str = field(default_factory=lambda: _now_dt().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorkingMemory:
    """Volatile attention scratchpad with capacity, decay, rehearsal, gating."""

    KINDS = {"user_query", "observation", "retrieved_memory", "grounding", "goal", "system"}

    def __init__(self, capacity: Optional[int] = None, half_life_seconds: float = 90.0,
                 forgetting_floor: float = 0.05, attention_threshold: float = 0.20) -> None:
        self.capacity = max(3, int(capacity or getattr(settings, "ARENA_WORKING_MEMORY_CAPACITY", 9)))
        self.half_life_seconds = max(5.0, float(half_life_seconds))
        self.forgetting_floor = float(forgetting_floor)
        self.attention_threshold = float(attention_threshold)
        self._items: Dict[str, WorkingMemoryItem] = {}
        self._current_goal: str = ""
        self._lock = threading.RLock()

    # ── attention scoring ────────────────────────────────────────────────────
    @staticmethod
    def _tokens(text: str) -> set:
        return set(re.findall(r"[a-z0-9]+", (text or "").lower()))

    _STOPWORDS = {
        "the", "a", "an", "is", "are", "was", "to", "of", "in", "on", "for",
        "and", "or", "it", "this", "that", "with", "at", "by",
    }

    def _goal_relevance(self, content: str) -> float:
        if not self._current_goal:
            return 0.0
        goal_tokens = self._tokens(self._current_goal) - self._STOPWORDS
        if not goal_tokens:
            return 0.0
        content_tokens = self._tokens(content)
        if not content_tokens:
            return 0.0
        return len(goal_tokens & content_tokens) / len(goal_tokens)

    def _novelty(self, content: str) -> float:
        content_key = " ".join(sorted(self._tokens(content)))
        for item in self._items.values():
            if " ".join(sorted(self._tokens(item.content))) == content_key:
                return 0.0  # duplicate: not novel
        return 1.0

    def set_goal(self, goal_text: str) -> None:
        with self._lock:
            self._current_goal = str(goal_text or "")[:500]

    # ── operations ───────────────────────────────────────────────────────────
    def encode(self, content: str, *, kind: str, source: str, salience: float,
               goal_text: Optional[str] = None) -> Dict[str, Any]:
        """Attention gate + insert with displacement. Returns the decision."""
        if kind not in self.KINDS:
            return {"accepted": False, "reason": f"unknown kind '{kind}'"}
        content = str(content or "").strip()
        if not content:
            return {"accepted": False, "reason": "empty content"}
        with self._lock:
            if goal_text is not None:
                self.set_goal(goal_text)
            relevance = self._goal_relevance(content)
            novelty = self._novelty(content)
            if novelty == 0.0:
                # Duplicate content = rehearsal of the existing item instead.
                for item in self._items.values():
                    if content[:200] == item.content[:200]:
                        self.refresh(item.item_id)
                        return {"accepted": True, "rehearsed": True, "item_id": item.item_id}
            # Goal relevance is the primary driver of attention; raw salience
            # alone (loud noise) cannot outrank an on-topic item.
            effective = max(0.0, min(1.0, 0.35 * float(salience) + 0.5 * relevance + 0.15 * novelty))
            if effective < self.attention_threshold:
                return {"accepted": False, "reason": "below attention threshold",
                        "effective_salience": round(effective, 4)}
            item = WorkingMemoryItem(
                item_id=f"wm_{uuid4().hex[:12]}",
                content=content[:2000], kind=kind, source=str(source or "unknown")[:500],
                salience=round(effective, 4),
            )
            self._items[item.item_id] = item
            evicted = None
            if len(self._items) > self.capacity:
                weakest = min(self._items.values(), key=lambda i: (i.activation * i.salience, i.created_at))
                evicted = weakest.item_id
                del self._items[weakest.item_id]
            result: Dict[str, Any] = {
                "accepted": True, "item_id": item.item_id,
                "effective_salience": item.salience, "evicted": evicted,
            }
            if evicted:
                result["note"] = "capacity limit: lowest-activation item displaced"
            return result

    def refresh(self, item_id: str) -> bool:
        """Rehearsal: restore activation and touch the item."""
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                return False
            item.activation = 1.0
            item.access_count += 1
            item.last_refreshed_at = _now_dt().isoformat()
            return True

    def decay(self, *, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Activation halves each half-life; items under the floor are forgotten."""
        now = now or _now_dt()
        with self._lock:
            forgotten = []
            for item in list(self._items.values()):
                refreshed = datetime.fromisoformat(item.last_refreshed_at)
                elapsed = max(0.0, (now - refreshed).total_seconds())
                halvings = elapsed / self.half_life_seconds
                item.activation = max(0.0, math.pow(0.5, halvings))
                if item.activation < self.forgetting_floor:
                    forgotten.append(item.item_id)
                    del self._items[item.item_id]
            return {"remaining": len(self._items), "forgotten": forgotten}

    def snapshot(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            ranked = sorted(
                self._items.values(),
                key=lambda i: (i.activation * i.salience, i.created_at),
                reverse=True,
            )
            return [item.to_dict() for item in ranked[: limit or len(ranked)]]

    def context_text(self, max_chars: int = 1200) -> str:
        """Compact rendering for the reasoning loop's prompt context."""
        lines = []
        budget = max(200, int(max_chars))
        for item in sorted(self._items.values(),
                           key=lambda i: (i.activation * i.salience), reverse=True):
            line = f"[{item.kind}|act={item.activation:.2f}|sal={item.salience:.2f}] {item.content[:160]}"
            if sum(len(l) for l in lines) + len(line) > budget:
                break
            lines.append(line)
        return "\n".join(lines)

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self._items.get(item_id)
            return item.to_dict() if item else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
