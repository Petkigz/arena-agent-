"""GeneralLearningEngine — Phase 6 (Beanie AGI roadmap): one learning loop.

The roadmap's loop, deterministic end-to-end::

    experience → observe → interpret → compare with existing knowledge
    → detect novelty → form hypothesis → test → observe outcome
    → update model → store knowledge → update confidence

Every KIND of experience enters through the same door (BeanieMind.learn):
conversations, observations, media, demonstrations, mistakes, successful
actions, owner corrections, experiments. Documents/videos/websites will
submit through this same door when the Phase-8 media learners land — the
loop does not multiply per source.

Honesty rules (they ARE the engine):

- ``success`` must be EVIDENCE the caller has, never a default: verified
  success is True, verified failure is False, and missing verification is
  UNKNOWN — never coerced to either side (attempted ≠ succeeded).
- Every stored record keeps provenance (source) and its novelty class.
- Reinforcement does not duplicate knowledge (rehearsal is counted, the
  store is not spammed); contradictions become explicit hypotheses and
  lessons, not silent overwrites.
- The engine is best-effort for the caller: learning never fails the task.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

EXPERIENCE_KINDS = {
    "action", "conversation", "correction", "observation",
    "media", "demonstration", "experiment",
}
NOVELTY_CLASSES = ("novel", "reinforces", "contradicts")

_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "your", "you", "are", "was", "were", "can", "could", "would", "should",
    "please", "into", "onto", "not", "but", "all", "any", "her", "his",
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terms(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]{3,}", str(text).lower())
            if t not in _STOPWORDS]


class GeneralLearningEngine:
    """The one loop every experience passes through."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_learning_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    novelty TEXT NOT NULL,
                    content TEXT NOT NULL,
                    outcome TEXT,
                    success INTEGER,
                    hypothesis TEXT,
                    verdict TEXT,
                    stored_memory_id TEXT,
                    related_count INTEGER NOT NULL DEFAULT 0
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Learning event ledger unavailable: {exc}")

    # ── THE LOOP ─────────────────────────────────────────────────────────
    def learn(self, experience: Dict[str, Any]) -> Dict[str, Any]:
        """Run one experience through the ten stages. Typed and fail-fast on
        the CONTRACT (kind/content/source), fail-open on storage."""
        # stage 1 — observe: typed intake, provenance required
        kind = str(experience.get("kind", "")).strip()
        content = str(experience.get("content", "")).strip()
        source = str(experience.get("source", "")).strip()
        if kind not in EXPERIENCE_KINDS:
            return {"success": False,
                    "reason": f"unknown experience kind '{kind}'",
                    "valid_kinds": sorted(EXPERIENCE_KINDS)}
        if not content:
            return {"success": False, "reason": "experience has no content"}
        if not source:
            return {"success": False, "reason": "experience has no source (provenance)"}
        # success is EVIDENCE: True / False / None(unknown). Never guessed.
        success = experience.get("success")
        if success is not None and not isinstance(success, bool):
            return {"success": False,
                    "reason": "success must be bool evidence or absent (UNKNOWN)"}

        # stage 2 — interpret: concepts present in the experience
        terms = _terms(content)[:12]

        # stage 3 — compare with existing knowledge
        related = self._related_knowledge(content)

        # stage 4 — detect novelty
        novelty = self._classify_novelty(related, success)

        # stage 5 — hypothesize (contradictions and experiments only)
        hypothesis = self._form_hypothesis(kind, content, novelty, experience)

        # stage 6 — test (experiments carry a declared prediction)
        verdict = self._verdict(kind, hypothesis, success)

        # stage 7 — outcome semantics are exactly what the caller evidenced
        outcome = str(experience.get("outcome", "") or "")[:200]

        # stage 8+9 — update model + store knowledge (provenance-tagged,
        # deduplicated — reinforcement rehearses, it does not duplicate)
        stored = self._store(kind, content, source, success, novelty, hypothesis, terms)

        # stage 10 — update confidence (calibrator + local evidence tally)
        self._update_confidence(experience, success, kind)

        record = {
            "success": True,
            "kind": kind,
            "content": content[:300],
            "source": source,
            "outcome": outcome or None,
            "success_evidence": success,
            "terms": terms,
            "related_knowledge": related,
            "novelty": novelty,
            "hypothesis": hypothesis,
            "verdict": verdict,
            "stored_memory_id": stored.get("memory_id"),
            "store_note": stored.get("note"),
        }
        self._persist_event(record)
        return record

    # ── stages ───────────────────────────────────────────────────────────
    def _related_knowledge(self, content: str) -> List[Dict[str, Any]]:
        """Search is recall-broad by design, but novelty verdicts need an
        evidence gate: a record only counts as related when it shares real
        content terms with the experience (or IS the experience). Otherwise
        loose n-gram hits would flip 'novel' into fake 'reinforces'."""
        memory = getattr(self.mind.memory, "memory", None)
        if memory is None:
            return []
        try:
            records = memory.search(content, limit=5)
        except Exception:
            return []
        exp_terms = set(_terms(content))
        related: List[Dict[str, Any]] = []
        for r in records:
            rec_content = str(getattr(r, "content", ""))
            rec_terms = set(_terms(rec_content))
            if not (exp_terms & rec_terms
                    or rec_content.strip().lower() == content.strip().lower()):
                continue  # loose retrieval noise, not knowledge about this
            related.append({
                "memory_id": getattr(r, "memory_id", None),
                "kind": getattr(r, "kind", None),
                "content": rec_content[:160],
                "success": getattr(r, "success", None),
            })
        return related

    @staticmethod
    def _classify_novelty(related: List[Dict[str, Any]],
                          success: Optional[bool]) -> str:
        if not related:
            return "novel"
        with_outcome = [r for r in related if r.get("success") is not None]
        if not with_outcome or success is None:
            return "reinforces"  # no comparable outcome → not a contradiction
        top = with_outcome[0]
        if top.get("success") is not success:
            return "contradicts"
        return "reinforces"

    @staticmethod
    def _form_hypothesis(kind: str, content: str, novelty: str,
                         experience: Dict[str, Any]) -> Optional[str]:
        if novelty == "contradicts":
            return (
                "the outcome of this may depend on conditions not yet modeled — "
                "investigate before trusting either side"
            )
        if kind == "experiment" and experience.get("prediction"):
            return f"predicted: {str(experience['prediction'])[:160]}"
        return None

    @staticmethod
    def _verdict(kind: str, hypothesis: Optional[str],
                 success: Optional[bool]) -> Optional[str]:
        if kind != "experiment" or not hypothesis or success is None:
            return None
        return "confirmed" if success else "refuted"

    def _store(self, kind: str, content: str, source: str,
               success: Optional[bool], novelty: str,
               hypothesis: Optional[str], terms: List[str]) -> Dict[str, Any]:
        mem = self.mind.memory
        tags = [f"learning:{novelty}", f"exp:{kind}"] + terms[:4]
        # contradictions become explicit lessons, never silent overwrites
        if novelty == "contradicts":
            lesson = f"Contradiction learned: {content}"
            if hypothesis:
                lesson += f" | hypothesis: {hypothesis}"
            out = mem.remember("lesson", lesson, importance=0.7,
                               source=source, tags=tags)
            return {"memory_id": out.get("memory_id"),
                    "note": "contradiction stored as lesson"}
        if kind == "correction":
            out = mem.remember("lesson", f"Owner correction: {content}",
                               importance=0.8, source=source, tags=tags)
            return {"memory_id": out.get("memory_id"),
                    "note": "owner correction stored as lesson"}
        if kind in ("action", "experiment") and success is True:
            out = mem.remember("episodic", content, importance=0.6,
                               source=source, tags=tags,
                               outcome="verified_success", success=True)
            return {"memory_id": out.get("memory_id"),
                    "note": "verified success stored as episode"}
        if kind in ("action", "experiment") and success is False:
            out = mem.remember("episodic", content, importance=0.55,
                               source=source, tags=tags,
                               outcome="verified_failure", success=False)
            return {"memory_id": out.get("memory_id"),
                    "note": "verified failure stored as episode (mistakes are data)"}
        if kind in ("conversation", "observation", "media", "demonstration"):
            # reinforcement rehearses, it does not duplicate
            try:
                if mem.memory is not None and mem.memory.find_exact("semantic", content):
                    return {"note": "already known — rehearsed, not duplicated"}
            except Exception:
                pass
            if novelty == "reinforces":
                return {"note": "reinforced existing knowledge (rehearsed)"}
            out = mem.remember("semantic", content, importance=0.4,
                               source=source, tags=tags)
            return {"memory_id": out.get("memory_id"),
                    "note": "novel knowledge stored as semantic memory"}
        return {"note": "nothing durable to store for this experience"}

    def _update_confidence(self, experience: Dict[str, Any],
                           success: Optional[bool], kind: str) -> None:
        predicted = experience.get("predicted_confidence")
        calibrator = getattr(self.mind.runtime, "confidence_calibrator", None)
        if calibrator is None or success is None or predicted is None:
            return  # missing observation is not a negative sample
        try:
            calibrator.record(
                action_type=str(experience.get("action_type") or kind),
                predicted_confidence=float(predicted),
                actual_outcome=success,
                goal_type=str(experience.get("goal_type") or ""),
            )
        except Exception as exc:
            app_logger.warning(f"Confidence calibration skipped: {exc}")

    # ── ledger + stats ───────────────────────────────────────────────────
    def _persist_event(self, record: Dict[str, Any]) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_learning_events
                       (recorded_at, kind, novelty, content, outcome, success,
                        hypothesis, verdict, stored_memory_id, related_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (_now_iso(), record["kind"], record["novelty"],
                     record["content"], record.get("outcome"),
                     None if record["success_evidence"] is None
                     else int(record["success_evidence"]),
                     record.get("hypothesis"), record.get("verdict"),
                     record.get("stored_memory_id"),
                     len(record.get("related_knowledge", []))),
                )
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Learning event not persisted: {exc}")

    def events(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT * FROM beanie_learning_events
                       ORDER BY event_id DESC LIMIT ?""", (int(limit),),
                ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                d["success"] = None if d["success"] is None else bool(d["success"])
                out.append(d)
            return out
        except Exception:
            return []

    def stats(self) -> Dict[str, Any]:
        by_kind: Dict[str, int] = {}
        by_novelty: Dict[str, int] = {}
        total = 0
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                for kind, n in conn.execute(
                        "SELECT kind, COUNT(*) FROM beanie_learning_events GROUP BY kind"):
                    by_kind[kind] = n
                    total += n
                for novelty, n in conn.execute(
                        "SELECT novelty, COUNT(*) FROM beanie_learning_events GROUP BY novelty"):
                    by_novelty[novelty] = n
        except Exception:
            pass
        return {"total_experiences": total, "by_kind": by_kind,
                "by_novelty": by_novelty,
                "novelty_classes": list(NOVELTY_CLASSES),
                "experience_kinds": sorted(EXPERIENCE_KINDS),
                "loop": "experience → observe → interpret → compare → novelty → "
                        "hypothesis → test → outcome → update model → store → "
                        "update confidence"}
