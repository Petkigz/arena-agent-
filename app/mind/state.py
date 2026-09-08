"""BeanieState — the unified internal-state skeleton (MISSING item M2, Phase 1).

The roadmap's target object::

    BeanieState
    ├── self            ├── current_goals     ├── predictions
    ├── owner           ├── beliefs           ├── uncertainty
    ├── world           ├── hypotheses        ├── emotions/social context
    ├── working_memory  ├── plans             ├── learned knowledge
    ├── active_perception  ├── actions        └── attention

Phase 1 ships the SKELETON: a read-only, fail-open view assembled from the
organs the CognitiveRuntime already owns. Nothing here mutates cognition —
later phases grow each room from a view into a working organ.

Honesty rule (AGENT_INVARIANTS §7): a room whose organ cannot be read
reports ``status: "unavailable"`` with the reason — it never fabricates a
value, and it never raises into the caller.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

# The exact field set from docs/AGI_ROADMAP.md (Phase 1 restructuring order,
# item 3). Tests pin this list — adding a room is a roadmap decision.
STATE_FIELDS = (
    "self",
    "owner",
    "world",
    "working_memory",
    "active_perception",
    "current_goals",
    "beliefs",
    "hypotheses",
    "plans",
    "actions",
    "predictions",
    "uncertainty",
    "emotions_social",
    "learned_knowledge",
    "attention",
)


def _probe(obj: Any, names=("summary", "introspect", "snapshot", "to_dict", "status")) -> Optional[Dict[str, Any]]:
    """First successful no-arg (or limit=) dict/list read, else None."""
    for name in names:
        fn = getattr(obj, name, None)
        if not callable(fn):
            continue
        try:
            value = fn()
        except TypeError:
            try:
                value = fn(limit=10)
            except Exception:
                continue
        except Exception:
            continue
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"items": value[:10], "count_shown": len(value)}
    return None


def _jsonable(value: Any) -> Any:
    """Force JSON-serializability without losing the payload silently."""
    try:
        json.dumps(value)
        return value
    except Exception:
        try:
            return json.loads(json.dumps(value, default=str))
        except Exception:
            return str(value)


class BeanieState:
    """Read-only unified view over the runtime's internal state."""

    def __init__(self, runtime: Any, identity: Any = None, mind: Any = None) -> None:
        self.runtime = runtime
        self.identity = identity
        # Phase 3–5 organs of the mind (world/self/memory facades). Optional:
        # the skeleton degrades honestly without them.
        self.mind = mind

    # ── room builders (each fail-open) ───────────────────────────────────
    def _room(self, component: Any, data: Optional[Dict[str, Any]] = None,
              status: str = "ok") -> Dict[str, Any]:
        room: Dict[str, Any] = {
            "status": status,
            "component": type(component).__name__ if component is not None else None,
        }
        if data is not None:
            room["data"] = _jsonable(data)
        return room

    def _self(self) -> Dict[str, Any]:
        rt = self.runtime
        data: Dict[str, Any] = {}
        if self.identity is not None:
            try:
                rec = self.identity.to_dict()
                data["identity"] = {
                    "name": rec.get("name"),
                    "kind": rec.get("kind"),
                    "born": rec.get("born"),
                    "milestones": len(rec.get("milestones", [])),
                }
            except Exception:
                pass
        # Phase 4: capability awareness through the mind's self facade.
        if self.mind is not None:
            try:
                caps = self.mind.self_model.capabilities()
                data["capabilities_count"] = caps.get("count")
                data["capabilities_by_safety_level"] = caps.get("by_safety_level")
            except Exception:
                pass
            # Phase 17: the developing personality — identity plus traits
            # derived from evidence (additive; the Phase-1/4 keys above
            # keep their contract).
            try:
                personality = self.mind.personality.snapshot()
                if personality:
                    data["personality"] = personality
            except Exception:
                pass
        probed = _probe(getattr(rt, "self_model", None))
        if probed:
            data["self_model"] = probed
        if not data:
            return self._room(getattr(rt, "self_model", None), None, "unavailable")
        return self._room(getattr(rt, "self_model", None), data)

    def _owner(self) -> Dict[str, Any]:
        # Phase 16: the owner room shows BOTH surfaces honestly — the
        # runtime's user_state snapshot (the Phase-1 contract) and the
        # mind's Social relationship model (facets/routines/style/history).
        store = getattr(self.runtime, "user_state", None)
        social = getattr(self.mind, "social", None) if self.mind is not None else None
        data: Dict[str, Any] = {}
        component: Any = None
        if store is not None:
            try:
                data["snapshot"] = store.snapshot()
            except Exception:
                probed = _probe(store)
                if probed:
                    data.update(probed)
            component = store
        if social is not None:
            relationship = _probe(social, names=("snapshot", "model", "summary"))
            if relationship:
                data["relationship"] = relationship
                if component is None:
                    component = social
        if not data:
            return self._room(component, None, "unavailable")
        return self._room(component, data)

    def _world(self) -> Dict[str, Any]:
        world = getattr(self.runtime, "world", None)
        data: Dict[str, Any] = {}
        try:
            data["entity_count"] = len(world.find_entities())
        except Exception:
            pass
        try:
            data["recent_observations"] = len(world.recent_observations(limit=50))
        except Exception:
            pass
        # Phase 3: typed ontology coverage through the mind's world facade —
        # only when the world store is actually wired (no organ → no data).
        if self.mind is not None and getattr(self.mind.world, "world", None) is not None:
            try:
                stats = self.mind.world.stats()
                data["by_type"] = stats.get("by_type")
                data["ontology_size"] = stats.get("ontology_size")
            except Exception:
                pass
        if not data:
            return self._room(world, None, "unavailable")
        return self._room(world, data)

    def _working_memory(self) -> Dict[str, Any]:
        wm = getattr(self.runtime, "working_memory", None)
        try:
            items = wm.snapshot(limit=9)
            return self._room(wm, {"capacity": 9, "items": items, "count": len(items)})
        except Exception:
            return self._room(wm, None, "unavailable")

    def _active_perception(self) -> Dict[str, Any]:
        # The silent watcher (charter §5④) runs in the server lifespan; the
        # mind only reports its configured standing here. Wiring the observer
        # through the mind is the Phase-13/14 attention slice.
        try:
            from app.config import settings
            data = {
                "background_observer": settings.ARENA_BACKGROUND_OBSERVER,
                "screen_watcher": settings.ARENA_SCREEN_WATCHER,
                "note": "observation feeds enter the mind here from Phase 13",
            }
            return self._room(object(), data, status="wired")
        except Exception:
            return self._room(None, None, "unavailable")

    def _current_goals(self) -> Dict[str, Any]:
        commitments = getattr(self.runtime, "commitments", None)
        data = _probe(commitments)
        if data is None:
            return self._room(commitments, None, "unavailable")
        return self._room(commitments, data)

    def _beliefs(self) -> Dict[str, Any]:
        beliefs = getattr(self.runtime, "beliefs", None)
        data: Dict[str, Any] = {}
        try:
            data["stale_beliefs"] = len(beliefs.stale_beliefs())
        except Exception:
            pass
        if not data:
            return self._room(beliefs, None, "unavailable")
        return self._room(beliefs, data)

    def _hypotheses(self) -> Dict[str, Any]:
        incubation = getattr(self.runtime, "incubation_queue", None)
        data = _probe(incubation, names=("summary", "snapshot", "to_dict", "pending", "list_pending"))
        if data is None:
            return self._room(incubation, None, "wired")
        return self._room(incubation, data)

    def _plans(self) -> Dict[str, Any]:
        # Approved-plan freshness + commitments are the plan surface today.
        plans = getattr(self.runtime, "plan_freshness", None)
        data = _probe(plans)
        status = "ok" if data else "wired"
        return self._room(plans, data, status)

    def _actions(self) -> Dict[str, Any]:
        selector = getattr(self.runtime, "actions", None)
        data = _probe(selector)
        status = "ok" if data else "wired"
        return self._room(selector, data, status)

    def _predictions(self) -> Dict[str, Any]:
        prediction = getattr(self.runtime, "prediction", None)
        data = _probe(prediction)
        status = "ok" if data else "wired"
        return self._room(prediction, data, status)

    def _uncertainty(self) -> Dict[str, Any]:
        calibrator = getattr(self.runtime, "confidence_calibrator", None)
        data = _probe(calibrator)
        status = "ok" if data else "wired"
        return self._room(calibrator, data, status)

    def _emotions_social(self) -> Dict[str, Any]:
        affect = getattr(self.runtime, "functional_affect", None)
        data = _probe(affect)
        status = "ok" if data else "wired"
        return self._room(affect, data, status)

    def _learned_knowledge(self) -> Dict[str, Any]:
        memory = getattr(self.runtime, "memory", None)
        lessons = getattr(self.runtime, "lessons", None)
        data: Dict[str, Any] = {}
        try:
            data["unconsolidated_episodes"] = len(memory.unconsolidated_episodes(limit=100))
        except Exception:
            pass
        lesson_probe = _probe(lessons)
        if lesson_probe:
            data["lessons"] = lesson_probe
        # Phase 5: the unified memory landscape (all eight kinds) — only
        # when a memory store is actually wired.
        if self.mind is not None and getattr(self.mind.memory, "memory", None) is not None:
            try:
                data["unified_memory_counts"] = self.mind.memory.counts()
            except Exception:
                pass
        if not data:
            return self._room(memory, None, "unavailable")
        return self._room(memory, data)

    def _attention(self) -> Dict[str, Any]:
        # Phase 14: the mind's Attention organ is the authoritative
        # arbitrator (one cognitive authority); the runtime's in-cycle
        # AttentionManager stays wired as the legacy fallback.
        attention = getattr(self.mind, "attention", None) if self.mind is not None else None
        if attention is None:
            attention = getattr(self.runtime, "attention", None)
        data = _probe(attention, names=("snapshot", "to_dict", "summary", "current_focus"))
        focus = getattr(attention, "current", None) or getattr(attention, "focus", None)
        if focus is not None:
            try:
                data = dict(data or {})
                data["current_focus"] = _jsonable(getattr(focus, "target_name", str(focus)))
            except Exception:
                pass
        status = "ok" if data else "wired"
        return self._room(attention, data, status)

    # ── the snapshot ─────────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        """The full BeanieState skeleton. Every room is present, JSON-safe,
        and honestly marked (ok / wired / unavailable)."""
        builders = {
            "self": self._self,
            "owner": self._owner,
            "world": self._world,
            "working_memory": self._working_memory,
            "active_perception": self._active_perception,
            "current_goals": self._current_goals,
            "beliefs": self._beliefs,
            "hypotheses": self._hypotheses,
            "plans": self._plans,
            "actions": self._actions,
            "predictions": self._predictions,
            "uncertainty": self._uncertainty,
            "emotions_social": self._emotions_social,
            "learned_knowledge": self._learned_knowledge,
            "attention": self._attention,
        }
        state: Dict[str, Any] = {}
        for field in STATE_FIELDS:
            try:
                state[field] = builders[field]()
            except Exception as exc:  # a room must never kill the snapshot
                state[field] = {
                    "status": "unavailable",
                    "component": None,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
        return state
