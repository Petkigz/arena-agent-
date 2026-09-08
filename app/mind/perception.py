"""Perception — Phase 13 (Beanie AGI roadmap): continuous perception.

The SENSE side of the embodiment diagram: screen, camera, microphone, phone
state, desktop state, network/environment → perception → attention →
significance. This phase builds the perception stage and the roadmap's
relevance question: "Is this relevant to what we're doing?" — she shouldn't
react to everything.

Mechanics (deterministic, no LLM):
- ``perceive(modality, content)`` — a perception is a TYPED statement about
  a sense channel. It enters the Phase-6 loop as an ``observation``
  experience: novelty decides what is stored (novel → knowledge; repeated →
  rehearsed, not re-stored — the loop's dedupe IS the "don't react to
  everything" mechanism).
- significance is computed honestly from three evidence sources:
  urgency (what the probe itself declared), curiosity (does it touch an
  open unknown?), novelty (did the learning loop call it novel?);
- ``drain_background_observer()`` — the existing silent watcher
  (BackgroundObserver) probes the environment continuously; this organ
  ingests its buffered EnvironmentChanges into perceptions. Called at the
  mind door on every interaction and available to the owner — perceptions
  land when she is awake to them;
- recording + judging only. Perceiving NEVER acts.

Honesty rules:
- a perception is not a belief and never an action — the epistemic label
  'perception' rides on every record;
- unknown modalities are rejected typed;
- significance carries its REASONS — inspectable, not vibes;
- every perception keeps provenance (which probe/channel said it).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

# the roadmap's sense channels
MODALITIES = {
    "screen", "camera", "audio", "phone", "desktop", "network",
    "environment", "owner",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Perception:
    """Sense channels in; typed, significance-judged perceptions out."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_perceptions (
                    perception_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    novelty TEXT,
                    significant INTEGER NOT NULL DEFAULT 0,
                    reasons TEXT,
                    stored_memory_id TEXT
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Perception ledger unavailable: {exc}")

    # ── the typed perception ─────────────────────────────────────────────
    def perceive(self, modality: str, content: str, source: str = "",
                 urgent: bool = False) -> Dict[str, Any]:
        """Register one perception. Typed on the channel; honest about
        novelty; explicit about significance."""
        modality = str(modality or "").strip().lower()
        content = str(content or "").strip()
        source = str(source or "").strip() or modality
        if modality not in MODALITIES:
            return {"success": False,
                    "reason": f"unknown sense channel '{modality}'",
                    "modalities": sorted(MODALITIES)}
        if not content:
            return {"success": False, "reason": "perception has no content"}

        # which open unknowns this touches — captured BEFORE the learning
        # door runs, because that door may close them on intake
        touched_unknowns = self._curiosity_matches(content)

        # the Phase-6 loop judges novelty and stores (deduped) knowledge
        rec: Dict[str, Any] = {}
        try:
            rec = self.mind.learn({
                "kind": "observation", "content": content,
                "source": f"{modality}:{source}"[:160], "success": None,
            })
        except Exception as exc:
            app_logger.warning(f"Perception not fed to learning loop: {exc}")
        novelty = rec.get("novelty")
        significant, reasons = self._significance(
            novelty=novelty, urgent=urgent, unknowns=touched_unknowns)
        self._persist(modality, content, source, novelty, significant,
                      reasons, rec.get("stored_memory_id"))
        return {"success": True, "epistemic_kind": "perception",
                "modality": modality, "content": content[:300],
                "source": source, "novelty": novelty,
                "significant": significant, "reasons": reasons,
                "stored_memory_id": rec.get("stored_memory_id"),
                "acted": False}  # perceiving never acts

    def _significance(self, novelty: Optional[str], urgent: bool,
                      unknowns: List[str]) -> Tuple[bool, List[str]]:
        """The roadmap's question: 'Is this relevant to what we're doing?'
        Evidence-based, with reasons surfaced."""
        reasons: List[str] = []
        if urgent:
            reasons.append("the probe declared it urgent")
        if novelty == "novel":
            reasons.append("novel — never perceived before")
        if unknowns:
            reasons.append("touches open unknown(s): " + ", ".join(unknowns[:2]))
        significant = bool(reasons)
        if not significant:
            reasons.append("background — known and not relevant to anything open")
        return significant, reasons

    def _curiosity_matches(self, content: str) -> List[str]:
        """Scan the open unknowns broadly — a perception is exactly how a
        buried unknown gets noticed, so priority order must not hide it."""
        try:
            open_unknowns = self.mind.curiosity.curiosities(limit=200)
        except Exception:
            return []
        content_terms = set(_terms(content))
        hits: List[str] = []
        for row in open_unknowns:
            topic_terms = set(_terms(str(row.get("topic", ""))))
            need = 1 if len(topic_terms) <= 1 else 2
            if len(content_terms & topic_terms) >= need:
                hits.append(str(row.get("topic")))
        return hits

    # ── the silent watcher feeds the sense ───────────────────────────────
    def drain_background_observer(self, limit: int = 20) -> Dict[str, Any]:
        """Ingest buffered EnvironmentChanges from the existing
        BackgroundObserver into perceptions. Deterministic translation:
        change_type + subject + states → perception content; probe priority
        → urgency."""
        try:
            import app.perception.background_observer as bo
        except Exception as exc:
            return {"success": False,
                    "reason": f"background observer unavailable: {exc}"}
        observer = getattr(bo, "observer_instance", None)
        if observer is None:
            return {"success": True, "ingested": 0,
                    "note": "the silent watcher is not running"}
        try:
            changes = observer.get_changes(clear=True)
        except Exception as exc:
            return {"success": False,
                    "reason": f"could not read environment changes: {exc}"}
        ingested = 0
        for change in changes[-int(limit):]:
            content = (f"{getattr(change, 'change_type', 'change')}: "
                       f"{getattr(change, 'subject', 'unknown')} is now "
                       f"{getattr(change, 'current_state', '?')}")
            urgent = getattr(change, "priority", "normal") == "urgent"
            try:
                rec = self.perceive("environment", content,
                                    source=str(getattr(change, "source", "probe")),
                                    urgent=urgent)
                if rec.get("success"):
                    ingested += 1
            except Exception as exc:
                app_logger.warning(f"Environment change not perceived: {exc}")
        return {"success": True, "ingested": ingested,
                "buffered_seen": len(changes)}

    # ── surfaces ─────────────────────────────────────────────────────────
    def stream(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_perceptions ORDER BY "
                    "perception_id DESC LIMIT ?", (int(limit),)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["significant"] = bool(d["significant"])
                d["reasons"] = [x for x in str(d.get("reasons") or "").split("|") if x]
                out.append(d)
            return out
        except Exception:
            return []

    def stats(self) -> Dict[str, Any]:
        by_modality: Dict[str, int] = {}
        total = significant = 0
        for row in self.stream(limit=10000):
            total += 1
            significant += 1 if row["significant"] else 0
            m = row["modality"]
            by_modality[m] = by_modality.get(m, 0) + 1
        return {"perceptions": total, "significant": significant,
                "background": total - significant,
                "by_modality": by_modality,
                "policy": "perceive → judge significance → never react to "
                          "everything (perception ≠ belief ≠ action)"}

    # ── internals ────────────────────────────────────────────────────────
    def _persist(self, modality: str, content: str, source: str,
                 novelty: Optional[str], significant: bool,
                 reasons: List[str], stored_memory_id: Optional[str]) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_perceptions
                       (recorded_at, modality, content, source, novelty,
                        significant, reasons, stored_memory_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (_now_iso(), modality, content[:500], source[:160],
                     novelty, int(significant), "|".join(reasons),
                     stored_memory_id))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Perception not persisted: {exc}")
