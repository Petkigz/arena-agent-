"""Phase 2 (owner plan 2026-09-10): authoritative application identity.

The app-launch executor already extracts an app name and calls the
SystemAppInventory tier matcher — per-query keyword/fuzzy guessing against a
volatile cache. This organ adds the missing piece in FRONT of that path:
PERSISTENT target resolution against the WorldModel, so the owner's spoken
form ('richst') binds once to its canonical entity ('Richie TV') with
confidence and evidence — before any fallback can derail the request.

Contract (owner rules, standing):
  * FAIL-OPEN: any error degrades to the legacy inventory matcher — identity
    resolution must never fail a launch.
  * KILL SWITCH: ``ARENA_APP_IDENTITY=0`` restores pre-Phase-2 behavior
    exactly (the inventory matcher still asks honestly on a miss).
  * AMBIGUITY IS A QUESTION, NEVER A GUESS: competing candidates produce a
    focused selection question (classified TARGET_AMBIGUOUS by the round-5
    park-reason taxonomy, which keys on the word 'ambiguous').
  * EVIDENCE: every resolution carries per-candidate evidence; learned
    aliases and install/process facts are recorded with provenance.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Policy constants (deliberately explicit — this is the 'sure' boundary):
RESOLVE_CONFIDENT = 0.9   # a single candidate at/above this auto-resolves
AMBIGUOUS_FLOOR = 0.5     # candidates at/above this compete for selection
WINNER_MARGIN = 0.12      # confidence gap that makes the top candidate clear


def _enabled() -> bool:
    try:
        from app.config import settings
        raw = str(getattr(settings, "ARENA_APP_IDENTITY", "1")).strip().lower()
        return raw not in ("0", "false", "off", "no", "")
    except Exception:
        return True  # fail-open: a settings glitch must not disable identity


def resolve_app_target(query: str, world: Optional[Any]) -> Dict[str, Any]:
    """Resolve an app reference against the persistent world model.

    Returns a deterministic verdict:
      resolved  → {name, entity_id, confidence, evidence}
      ambiguous → {question, candidates[]}  (focused selection ask)
      unknown   → legacy inventory matching should proceed.
    """
    out: Dict[str, Any] = {"status": "unknown", "query": str(query or ""), "candidates": []}
    if not _enabled():
        out["reason"] = "identity resolution disabled (ARENA_APP_IDENTITY=0)"
        return out
    if world is None:
        out["reason"] = "world model not wired"
        return out
    try:
        ranked = world.resolve_candidates(query, entity_type="application")
    except Exception:
        return out  # fail-open — the legacy matcher takes over
    live = [c for c in ranked if c["confidence"] >= AMBIGUOUS_FLOOR]
    out["candidates"] = [
        {"name": c["entity"].name, "confidence": c["confidence"],
         "evidence": c["evidence"], "entity_id": c["entity"].id}
        for c in live[:4]
    ]
    if not live:
        return out
    top = live[0]
    clear = (
        top["confidence"] >= RESOLVE_CONFIDENT
        or len(live) == 1
        or (top["confidence"] - live[1]["confidence"]) >= WINNER_MARGIN
    )
    if clear:
        out.update(status="resolved", entity_id=top["entity"].id,
                   name=top["entity"].name, confidence=top["confidence"],
                   evidence=top["evidence"])
        return out
    names = " or ".join(f"'{c['name']}'" for c in out["candidates"][:3])
    out.update(
        status="ambiguous",
        question=(
            f"Target ambiguous — {len(live)} installed apps match: {names}. "
            "Which one did you mean? Reply with the name."
        ),
    )
    return out


def remember_app(name: str, world: Optional[Any], *, executable: str = "",
                 source: str = "app_inventory",
                 alias: Optional[str] = None) -> Optional[str]:
    """Persist an app entity with installation evidence (+ alias binding).

    Installation is an OBSERVATION (state with provenance), never an
    attribute claim — the world model's honesty invariant.
    """
    name = str(name or "").strip()
    if world is None or not name:
        return None
    try:
        attrs: Dict[str, Any] = {}
        if executable:
            attrs["executable"] = str(executable)
        entity = world.upsert_entity(name=name, entity_type="application",
                                     attributes=attrs, confidence=1.0)
        from uuid import uuid4
        from app.cognition.world_model import Observation
        world.observe(Observation(
            id=uuid4().hex, subject=entity.name, predicate="installed",
            value=True, source=str(source), observation_type="direct",
        ))
        if alias and str(alias).strip():
            world.add_alias(entity.id, str(alias).strip(), source=str(source))
        return entity.id
    except Exception:
        return None  # fail-open — learning must never fail a task


def record_process_state(name: str, running: bool, world: Optional[Any],
                         source: str = "psutil_scan") -> bool:
    """Timestamped process-state observation; freshness rules apply at read
    time (get_entity_state with max_age) — a stale 'running' is never
    served as current fact."""
    name = str(name or "").strip()
    if world is None or not name:
        return False
    try:
        from uuid import uuid4
        from app.cognition.world_model import Observation
        world.observe(Observation(
            id=uuid4().hex, subject=name, predicate="process_state",
            value="running" if running else "not_running",
            source=str(source), observation_type="direct",
        ))
        return True
    except Exception:
        return False  # fail-open
