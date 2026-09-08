"""BeanieMind — the one canonical entry point (AGI roadmap Phase 1).

Deliverable, in the roadmap's words: "one canonical entry point:
``BeanieMind.process(...)``. Whether input comes from voice, text, Android,
desktop, screen observation, camera, or another process — it enters the same
mind."

What this class IS and IS NOT:

- It is the IDENTITY + STATE + DOOR of the mind.
- It is NOT a second cognitive runtime. The brain remains the
  ``CognitiveRuntime`` singleton (AGENT_INVARIANTS §1 — one brain, always).
  BeanieMind never constructs a runtime; it resolves the singleton lazily,
  and every call path lands in ``runtime.process_cognitive_cycle`` exactly
  as before — Phase 1 changes WHO the input enters through, not HOW the
  cycle runs.

Entry ledger: every input through the door is recorded (modality,
conversation, time, short summary) in SQLite, fail-open. This ledger is the
raw material the Phase-13/14 attention system will arbitrate — observations
and autonomous ticks will enter here too.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.mind.curiosity import CuriosityEngine
from app.mind.embodiment import Embodiment
from app.mind.identity import BeanieIdentity
from app.mind.imagination import Imagination
from app.mind.learning_loop import GeneralLearningEngine
from app.mind.media_learning import MediaLearning
from app.mind.memory_facade import SocialMemoryStore, UnifiedMemory
from app.mind.os_concepts import OSConceptLayer
from app.mind.perception import Perception
from app.mind.self_facade import SelfModelFacade
from app.mind.state import BeanieState
from app.mind.teaching import DemonstrationTeaching
from app.mind.world_facade import WorldModelFacade
from app.mind.world_first import WorldFirstReasoning
from app.utils.logger import app_logger

# The door's vocabulary. Unknown modalities are accepted but flagged —
# honesty over strictness (a new client must never be refused at the door).
MODALITIES = {
    "text",       # WebSocket chat (frontend / desktop / Android text)
    "voice",      # voice pipeline transcript (primary interface)
    "rest",       # REST /chat
    "android",    # reserved: Android-native intents
    "desktop",    # reserved: desktop-native intents
    "observation",  # reserved Phase 13: perception feeds
    "autonomous",   # reserved Phase 15: motivation ticks
    "process",      # reserved: other processes / APIs
}

_MAX_SUMMARY = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BeanieMind:
    """The one door of the one mind."""

    _instance: Optional["BeanieMind"] = None
    _instance_lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None, runtime: Any = None) -> None:
        self.db_path = str(db_path or settings.DB_PATH)
        self._runtime = runtime  # injected (tests/bound views) or None → singleton
        self._lock = threading.RLock()
        self._identity: Optional[BeanieIdentity] = None
        self._world: Optional[WorldModelFacade] = None
        self._self_model: Optional[SelfModelFacade] = None
        self._memory: Optional[UnifiedMemory] = None
        self._world_first: Optional[WorldFirstReasoning] = None
        self._learning: Optional[GeneralLearningEngine] = None
        self._teaching: Optional[DemonstrationTeaching] = None
        self._media_learning: Optional[MediaLearning] = None
        self._curiosity: Optional[CuriosityEngine] = None
        self._imagination: Optional[Imagination] = None
        self._embodiment: Optional[Embodiment] = None
        self._os_concepts: Optional[OSConceptLayer] = None
        self._perception: Optional[Perception] = None
        self._entry_count = 0
        # Phase 2: the most recent world-first briefs (owner-inspectable).
        self._briefs: List[Dict[str, Any]] = []
        self._briefs_cap = 50
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS beanie_mind_entries (
                        entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        recorded_at TEXT NOT NULL,
                        modality TEXT NOT NULL,
                        known_modality INTEGER NOT NULL,
                        conversation_id TEXT,
                        summary TEXT NOT NULL,
                        epoch REAL NOT NULL
                    )"""
                )
                conn.commit()
        except Exception as exc:  # storage failure never blocks the door
            app_logger.warning(f"BeanieMind entry ledger unavailable: {exc}")

    # ── singleton + binding ──────────────────────────────────────────────
    @classmethod
    def get_instance(cls, db_path: Optional[str] = None, runtime: Any = None) -> "BeanieMind":
        """The shared mind. If a caller holds a SPECIFIC runtime (the server
        wiring, a test stub), the returned mind is bound to that same brain —
        never to a different one. One brain, always."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(db_path=db_path, runtime=runtime)
            shared = cls._instance
            # First explicit brain binds the shared mind WITHOUT resolving the
            # runtime property (never construct a CognitiveRuntime here — a
            # test stub must not drag up the real brain, and vice versa).
            if runtime is not None and shared._runtime is None:
                shared._runtime = runtime
        if runtime is not None and shared._runtime is not None and shared._runtime is not runtime:
            # Bound view for a different brain instance (test fixtures):
            # intentionally NOT cached — the singleton stays authoritative.
            return cls(db_path=db_path, runtime=runtime)
        return shared

    @classmethod
    def reset_instance(cls) -> None:
        """Test-only escape hatch (mirrors CognitiveRuntime test support)."""
        with cls._instance_lock:
            cls._instance = None

    @property
    def runtime(self) -> Any:
        """The brain. Resolved lazily so importing this module never spins
        up a CognitiveRuntime; resolved through the singleton so there is
        exactly one brain in the process."""
        if self._runtime is None:
            from app.cognition.runtime import CognitiveRuntime
            self._runtime = CognitiveRuntime.get_instance()
        return self._runtime

    # ── identity & state ─────────────────────────────────────────────────
    @property
    def identity(self) -> BeanieIdentity:
        with self._lock:
            if self._identity is None:
                self._identity = BeanieIdentity(self.db_path)
            return self._identity

    def state(self) -> Dict[str, Any]:
        """The BeanieState snapshot (M2): every room, honestly marked."""
        return BeanieState(self.runtime, identity=self.identity, mind=self).snapshot()

    # ── the mind's organs (Phases 3–5): world, self, unified memory ──────
    @property
    def world(self) -> WorldModelFacade:
        """Phase 3: reasoning about the persistent world model."""
        with self._lock:
            if self._world is None:
                self._world = WorldModelFacade(getattr(self.runtime, "world", None))
            return self._world

    @property
    def self_model(self) -> SelfModelFacade:
        """Phase 4: capabilities, limitations, and genuine self-assessment."""
        with self._lock:
            if self._self_model is None:
                from app.tools.manifest import get_tool_manifest
                self._self_model = SelfModelFacade(
                    manifest_getter=get_tool_manifest,
                    memory=getattr(self.runtime, "memory", None),
                    hardware_self_model=getattr(self.runtime, "hardware_self_model", None),
                    identity=self.identity,
                )
            return self._self_model

    @property
    def memory(self) -> UnifiedMemory:
        """Phase 5: one view over every memory kind (working, episodic,
        semantic, procedural, lesson, social, preference, autobiographical,
        meta)."""
        with self._lock:
            if self._memory is None:
                self._memory = UnifiedMemory(
                    memory=getattr(self.runtime, "memory", None),
                    working=getattr(self.runtime, "working_memory", None),
                    social=SocialMemoryStore(self.db_path),
                    identity=self.identity,
                    preferences=getattr(self.runtime, "phase7_preferences", None),
                )
            return self._memory

    @property
    def world_first(self) -> WorldFirstReasoning:
        """Phase 2: world-first brief assembly (world → self → memory) before
        the cycle identifies any capability."""
        with self._lock:
            if self._world_first is None:
                self._world_first = WorldFirstReasoning(self)
            return self._world_first

    def briefs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Recent world-first briefs, newest first (owner-inspectable)."""
        return list(reversed(self._briefs[-int(limit):]))

    @property
    def learning(self) -> GeneralLearningEngine:
        """Phase 6: the one learning loop every experience passes through."""
        with self._lock:
            if self._learning is None:
                self._learning = GeneralLearningEngine(self)
            return self._learning

    def learn(self, experience: Dict[str, Any]) -> Dict[str, Any]:
        """The canonical learning door (mirrors process() for inputs). Every
        kind of experience — action outcomes, conversations, corrections,
        observations, media, demonstrations, experiments — enters here and runs
        the same ten-stage loop."""
        rec = self.learning.learn(experience)
        # Phase 9: incoming knowledge can close open unknowns. Best-effort —
        # curiosity bookkeeping never fails the learning itself.
        if isinstance(rec, dict) and rec.get("success"):
            self._close_unknowns_from_knowledge(rec.get("content") or "")
        return rec

    def _close_unknowns_from_knowledge(self, content: str) -> None:
        if str(getattr(settings, "ARENA_CURIOSITY", "1")) == "0":
            return
        try:
            self.curiosity.notify_knowledge(content)
        except Exception as exc:
            app_logger.warning(f"Curiosity notification skipped (non-fatal): {exc}")

    @property
    def teaching(self) -> DemonstrationTeaching:
        """Phase 7: conversation is the teaching interface ("watch this")."""
        with self._lock:
            if self._teaching is None:
                self._teaching = DemonstrationTeaching(self)
            return self._teaching

    @property
    def media_learning(self) -> MediaLearning:
        """Phase 8: images/video/web enter the one loop as media experiences."""
        with self._lock:
            if self._media_learning is None:
                self._media_learning = MediaLearning(self)
            return self._media_learning

    @property
    def curiosity(self) -> CuriosityEngine:
        """Phase 9: the internal UNKNOWN system."""
        with self._lock:
            if self._curiosity is None:
                self._curiosity = CuriosityEngine(self)
            return self._curiosity

    @property
    def imagination(self) -> Imagination:
        """Phase 10: simulate before acting; compare prediction vs reality."""
        with self._lock:
            if self._imagination is None:
                self._imagination = Imagination(self)
            return self._imagination

    @property
    def embodiment(self) -> Embodiment:
        """Phase 11: concepts in, ranked motor pathways out — never
        execution (the cycle's authorization path keeps acting)."""
        with self._lock:
            if self._embodiment is None:
                self._embodiment = Embodiment(self)
            return self._embodiment

    @property
    def os_concepts(self) -> OSConceptLayer:
        """Phase 12: one platform-free concept layer over all bodies
        (M10) — express intents as concepts, transfer procedures across
        bodies."""
        with self._lock:
            if self._os_concepts is None:
                self._os_concepts = OSConceptLayer(self)
            return self._os_concepts

    @property
    def perception(self) -> Perception:
        """Phase 13: the SENSE side — typed perceptions, significance
        judged, never reacted to blindly."""
        with self._lock:
            if self._perception is None:
                self._perception = Perception(self)
            return self._perception

    # ── THE DOOR ─────────────────────────────────────────────────────────
    def process(
        self,
        user_text: str,
        *,
        modality: str = "text",
        conversation_id: Optional[str] = None,
        **cycle_kwargs: Any,
    ) -> Dict[str, Any]:
        """Every conversational input enters the mind here.

        Phase 2 (world-first): before delegating to the brain's closed loop,
        the mind assembles a deterministic brief — world context, self state,
        relevant memory — and offers it to the brain's working-memory
        scratchpad (the channel the cycle already reads when it builds its
        prompt). The capability layer is therefore consulted with the world
        already understood, not instead of it.

        The brief is best-effort and fail-open: if assembly or delivery
        fails, the cycle runs exactly as before. The returned dict is the
        runtime's typed result, UNCHANGED (attempted ≠ succeeded, UNKNOWN
        preserved — the honesty invariants live one floor down).
        """
        self._record_entry(modality, conversation_id, user_text)
        self._run_world_first(user_text, modality)
        self._drain_perceptions()
        result = self.runtime.process_cognitive_cycle(
            user_text=user_text,
            session_id=conversation_id,
            **cycle_kwargs,
        )
        self._learn_from_cycle(user_text, modality, result)
        return result

    def _learn_from_cycle(self, user_text: str, modality: str, result: Any) -> None:
        """Phase 6: a completed cycle is an experience. Success is taken ONLY
        from the verifier's word (goal_verified) — attempted ≠ succeeded, and
        a missing verdict stays UNKNOWN rather than being guessed. Best-effort:
        learning never fails the task."""
        if str(getattr(settings, "ARENA_LEARNING_LOOP", "1")) == "0":
            return
        if not isinstance(result, dict):
            return
        verified = result.get("goal_verified")
        if verified is not None and not isinstance(verified, bool):
            verified = None
        experience = {
            "kind": "action",
            "content": user_text,
            "source": f"cycle:{modality}",
            "outcome": str(result.get("goal_lifecycle_state") or "") or None,
            "success": verified,  # True / False / None(unknown) — never guessed
            "predicted_confidence": result.get("predicted_confidence"),
            "goal_type": str(result.get("reasoning_action") or ""),
        }
        try:
            self.learning.learn(experience)
        except Exception as exc:
            app_logger.warning(f"Cycle experience not learned (non-fatal): {exc}")
        # Phase 10: prediction vs reality. Only when the verifier gave a
        # definite word AND an action actually ran — waiting-for-evidence is
        # not a comparison. Failures become training data. Kill switch:
        # ARENA_IMAGINATION=0 (the owner surface keeps working).
        action_type = str(result.get("action_type") or "").strip()
        if (str(getattr(settings, "ARENA_IMAGINATION", "1")) != "0"
                and action_type and isinstance(verified, bool)
                and not result.get("verification_unknown")):
            try:
                self.imagination.compare(
                    action_type, verified,
                    surprisal=result.get("prediction_surprisal"),
                    source="cycle")
            except Exception as exc:
                app_logger.warning(f"Prediction-vs-reality skipped (non-fatal): {exc}")

    def _run_world_first(self, user_text: str, modality: str) -> None:
        """Assemble + deliver the Phase-2 brief. Never raises into the door."""
        if str(getattr(settings, "ARENA_WORLD_FIRST", "1")) == "0":
            return
        record: Dict[str, Any] = {"text": str(user_text or "")[:200], "modality": modality}
        try:
            brief = self.world_first.assemble_brief(user_text)
            delivery = self.world_first.deliver(user_text, brief)
            record.update({
                "chars": brief.get("chars", 0),
                "has_positive_content": brief.get("has_positive_content"),
                "delivered": delivery.get("delivered"),
                "delivery_reason": delivery.get("reason"),
                "rendered": brief.get("rendered", ""),
            })
            # Phase 9: gaps in the world model are unknowns — register them
            # so curiosity compounds and investigation can close them later.
            self._feed_gaps_to_curiosity(
                (brief.get("world") or {}).get("gaps") or [], user_text)
        except Exception as exc:  # the door must never fail on context
            record.update({"delivered": False,
                           "delivery_reason": f"brief failed: {type(exc).__name__}: {exc}"})
            app_logger.warning(f"World-first brief skipped: {exc}")
        self._briefs.append(record)
        if len(self._briefs) > self._briefs_cap * 2:
            self._briefs = self._briefs[-self._briefs_cap:]
        try:
            from app.utils import decision_trace
            decision_trace.record(
                "beanie_mind", "world_first_brief",
                f"delivered={record.get('delivered')} chars={record.get('chars', 0)}"
                + (f" ({record.get('delivery_reason')})" if record.get("delivery_reason") else ""),
                conversation_id="", modality=modality,
            )
        except Exception:
            pass

    def _drain_perceptions(self) -> None:
        """Phase 13: while she is awake to the world, buffered environment
        changes from the silent watcher become perceptions. Best-effort;
        perception never fails the task."""
        if str(getattr(settings, "ARENA_PERCEPTION", "1")) == "0":
            return
        try:
            self.perception.drain_background_observer()
        except Exception as exc:
            app_logger.warning(f"Perception drain skipped (non-fatal): {exc}")

    def _feed_gaps_to_curiosity(self, gaps: List[str], user_text: str) -> None:
        """Phase 9: 'not yet in world model' → open unknowns. Best-effort;
        curiosity never breaks the brief."""
        if str(getattr(settings, "ARENA_CURIOSITY", "1")) == "0":
            return
        for gap in gaps[:6]:
            try:
                self.curiosity.register(
                    str(gap), source="world_first_gap",
                    context=str(user_text or "")[:120])
            except Exception as exc:
                app_logger.warning(f"Gap not registered as unknown (non-fatal): {exc}")

    def observe(
        self,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perception/autonomy lane (Phases 13–15). Phase 1 records the
        observation at the door; attention decides later what deserves
        thought. Recording-only: observing must never act."""
        summary = f"observation from {source}"
        if isinstance(payload, dict):
            hint = payload.get("summary") or payload.get("event") or ""
            if hint:
                summary = f"observation from {source}: {str(hint)[:_MAX_SUMMARY]}"
        self._record_entry("observation", conversation_id, summary)
        # Phase 13: the observation also becomes a typed perception judged
        # for significance (best-effort; recording never fails the door).
        perception_note: Optional[Dict[str, Any]] = None
        try:
            modality = "owner"
            if isinstance(payload, dict) and payload.get("modality"):
                modality = str(payload["modality"])
            perception_note = self.perception.perceive(
                modality, summary, source=source)
        except Exception as exc:
            app_logger.warning(f"Perception pass skipped (non-fatal): {exc}")
        result: Dict[str, Any] = {"success": True, "recorded": True,
                                  "source": source, "acted": False}
        if perception_note is not None:
            result["perception"] = perception_note
        return result

    # ── entry ledger ─────────────────────────────────────────────────────
    def _record_entry(self, modality: str, conversation_id: Optional[str], summary: str) -> None:
        """Best-effort entry recording. A failed write degrades to an
        in-process counter and never fails the cycle."""
        known = modality in MODALITIES
        entry_summary = str(summary or "")[:_MAX_SUMMARY]
        self._entry_count += 1
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_mind_entries
                       (recorded_at, modality, known_modality, conversation_id, summary, epoch)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (_now_iso(), str(modality), 1 if known else 0,
                     conversation_id, entry_summary, time.time()),
                )
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"BeanieMind entry not persisted: {exc}")

    def entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Most recent inputs through the door (owner-visible)."""
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                rows = conn.execute(
                    """SELECT recorded_at, modality, known_modality, conversation_id, summary
                       FROM beanie_mind_entries ORDER BY entry_id DESC LIMIT ?""",
                    (int(limit),),
                ).fetchall()
            return [
                {
                    "recorded_at": r[0],
                    "modality": r[1],
                    "known_modality": bool(r[2]),
                    "conversation_id": r[3],
                    "summary": r[4],
                }
                for r in rows
            ]
        except Exception:
            return []

    def entry_stats(self) -> Dict[str, Any]:
        """Per-modality counts since process start + ledger size."""
        per_modality: Dict[str, int] = {}
        total = 0
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                rows = conn.execute(
                    "SELECT modality, COUNT(*) FROM beanie_mind_entries GROUP BY modality"
                ).fetchall()
            per_modality = {r[0]: r[1] for r in rows}
            total = sum(per_modality.values())
        except Exception:
            total = self._entry_count
        return {"total_entries": total, "per_modality": per_modality}

    # ── owner-facing description ─────────────────────────────────────────
    def describe(self) -> Dict[str, Any]:
        """Who is answering, and through which doors input arrives."""
        return {
            "success": True,
            "identity": self.identity.to_dict(),
            "identity_statement": self.identity.identity_statement(),
            "entry_stats": self.entry_stats(),
            "modalities": sorted(MODALITIES),
        }
