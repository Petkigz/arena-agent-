"""SelfModelFacade — Phase 4 (Beanie AGI roadmap): a genuine self model.

The roadmap's acceptance example::

    "I don't know how to configure this application."
    must become a genuine internal state:
        knowledge: unknown
        confidence: 0.08
        possible_actions: investigate / ask owner / observe demonstration / search

``assess(task)`` produces exactly that shape — deterministically, from REAL
evidence, never from vibes:

1. capability awareness — does the capability catalog cover this? (the
   manifest is authoritative; charter §18: authority ≠ intelligence — a
   Level-3 capability still counts as something she UNDERSTANDS how to do,
   even when she is not currently authorized to do it);
2. memory — has she done or learned this before? (episodic success,
   procedural records, lessons);
3. the two combine into knowledge ∈ {known, partial, unknown} with a
   rule-based confidence, and a typed ``possible_actions`` list.

The facade is dependency-injected (manifest getter, memory store, hardware
self-model, identity) so the mind wires the real organs and tests stay fast.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

UNKNOWN_CONFIDENCE = 0.08  # the roadmap's number for genuine ignorance
PARTIAL_BASE = 0.35
KNOWN_BASE = 0.75

POSSIBLE_ACTIONS_UNKNOWN = ["investigate", "ask_owner", "observe_demonstration", "search"]
POSSIBLE_ACTIONS_PARTIAL = ["attempt_with_verification", "investigate", "ask_owner"]
POSSIBLE_ACTIONS_KNOWN = ["execute", "verify_after"]


_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "your", "you", "are", "was", "were", "can", "could", "would", "should",
    "please", "into", "onto", "not", "but", "all", "any", "her", "his",
})


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]{3,}", str(text).lower())
            if t not in _STOPWORDS}


class SelfModelFacade:
    """The mind's persistent model of herself."""

    def __init__(
        self,
        manifest_getter: Optional[Callable[[], Dict[str, Dict[str, Any]]]] = None,
        memory: Any = None,
        hardware_self_model: Optional[Dict[str, Any]] = None,
        identity: Any = None,
    ) -> None:
        self._manifest_getter = manifest_getter
        self.memory = memory
        self.hardware_self_model = hardware_self_model or {}
        self.identity = identity

    # ── capabilities (knowledge ≠ authorization — charter §18) ───────────
    def capabilities(self) -> Dict[str, Any]:
        """What she CAN do — understanding, independent of current
        permission. Safety levels are reported so the owner sees both."""
        catalog: Dict[str, Dict[str, Any]] = {}
        error = None
        if self._manifest_getter is not None:
            try:
                catalog = self._manifest_getter() or {}
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        by_category: Dict[str, int] = {}
        by_safety: Dict[str, int] = {}
        for entry in catalog.values():
            cat = str(entry.get("category", "uncategorized"))
            by_category[cat] = by_category.get(cat, 0) + 1
            lvl = str(entry.get("safety_level", "?"))
            by_safety[f"L{lvl}"] = by_safety.get(f"L{lvl}", 0) + 1
        result: Dict[str, Any] = {
            "count": len(catalog),
            "by_category": by_category,
            "by_safety_level": by_safety,
            "note": "capability = understanding; execution still passes the owner's authority gates",
        }
        if error:
            result["catalog_error"] = error
        return result

    def _capability_matches(self, task_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Deterministic token-overlap match against the catalog (name,
        category, description). No LLM — Phase 4 is about the STATE, and the
        state must be inspectable."""
        if self._manifest_getter is None:
            return []
        try:
            catalog = self._manifest_getter() or {}
        except Exception:
            return []
        task_terms = _tokens(task_text)
        if not task_terms:
            return []
        scored: List[Dict[str, Any]] = []
        for action_type, entry in catalog.items():
            entry_terms = _tokens(
                f"{action_type} {entry.get('name', '')} {entry.get('category', '')} "
                f"{entry.get('description', '')}"
            )
            overlap = task_terms & entry_terms
            if not overlap:
                continue
            score = len(overlap) / max(1, min(len(task_terms), 8))
            if score >= 0.25:
                scored.append({
                    "action_type": action_type,
                    "name": entry.get("name"),
                    "category": entry.get("category"),
                    "safety_level": entry.get("safety_level"),
                    "score": round(score, 3),
                    "matched_terms": sorted(overlap)[:6],
                })
        scored.sort(key=lambda m: m["score"], reverse=True)
        return scored[:limit]

    def _memory_hits(self, task_text: str, kinds=("procedural", "episodic", "lesson"),
                     limit: int = 5) -> List[Dict[str, Any]]:
        if self.memory is None:
            return []
        try:
            records = self.memory.search(task_text, kinds=set(kinds), limit=limit)
        except Exception:
            return []
        hits: List[Dict[str, Any]] = []
        for rec in records:
            hits.append({
                "memory_id": getattr(rec, "memory_id", None),
                "kind": getattr(rec, "kind", None),
                "content": str(getattr(rec, "content", ""))[:160],
                "success": getattr(rec, "success", None),
                "source": getattr(rec, "source", None),
            })
        return hits

    # ── THE assessment (roadmap example, exactly) ────────────────────────
    def assess(self, task_text: str) -> Dict[str, Any]:
        """Genuine internal state for 'can I do this?' — knowledge,
        confidence, evidence, possible actions."""
        capability_matches = self._capability_matches(task_text)
        memory_hits = self._memory_hits(task_text)
        successful_experience = [
            h for h in memory_hits if h.get("kind") == "episodic" and h.get("success") is True
        ]
        procedural_knowledge = [h for h in memory_hits if h.get("kind") in ("procedural", "lesson")]

        strong_capability = bool(capability_matches) and capability_matches[0]["score"] >= 0.5
        if strong_capability and (successful_experience or procedural_knowledge):
            knowledge = "known"
            confidence = min(0.95, KNOWN_BASE + 0.05 * len(successful_experience)
                             + 0.03 * len(procedural_knowledge))
            possible_actions = list(POSSIBLE_ACTIONS_KNOWN)
        elif strong_capability or memory_hits:
            knowledge = "partial"
            confidence = min(0.7, PARTIAL_BASE
                             + (0.15 if strong_capability else 0.0)
                             + 0.05 * len(memory_hits))
            possible_actions = list(POSSIBLE_ACTIONS_PARTIAL)
        else:
            knowledge = "unknown"
            confidence = UNKNOWN_CONFIDENCE
            possible_actions = list(POSSIBLE_ACTIONS_UNKNOWN)

        return {
            "task": str(task_text),
            "knowledge": knowledge,
            "confidence": round(confidence, 3),
            "possible_actions": possible_actions,
            "evidence": {
                "capability_matches": capability_matches,
                "memory_hits": memory_hits,
                "successful_experience_count": len(successful_experience),
            },
            "note": "understanding ≠ authorization: even 'known' passes the owner's gates before execution",
        }

    # ── limitations (honest hardware truth) ──────────────────────────────
    def limitations(self) -> Dict[str, Any]:
        hw = dict(self.hardware_self_model or {})
        return {
            "hardware_self_model": hw or {"status": "unavailable"},
            "note": "local inference on owner hardware; token budgets and model "
                    "routing are hardware-aware by design (invariant #3)",
        }

    # ── the full profile ─────────────────────────────────────────────────
    def profile(self, memory_counts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        identity = {}
        if self.identity is not None:
            try:
                rec = self.identity.to_dict()
                identity = {
                    "name": rec.get("name"), "kind": rec.get("kind"),
                    "born": rec.get("born"),
                    "development_milestones": len(rec.get("milestones", [])),
                }
            except Exception:
                identity = {"status": "unavailable"}
        return {
            "success": True,
            "identity": identity,
            "capabilities": self.capabilities(),
            "limitations": self.limitations(),
            "experiences": memory_counts or {},
            "personality": "develops through interaction (roadmap Phase 17); "
                           "seed persona today, owner values only",
        }
