"""Reflection — Phase 19 (Beanie AGI roadmap): the bridge between
experience and development.

"After important experiences: What happened? Why? What did I believe? Was
I correct? What surprised me? What did I learn? Should I change my model?
Should I remember this?"

Mechanics (deterministic, no LLM): ``reflect_on(experience)`` answers
every one of those questions from REAL evidence — never narration:
- what happened: the experience itself (kind, content, outcome);
- what I believed: the imagination ledger's prediction for that action,
  when she simulated it (expected + confidence); nothing invented when
  she didn't;
- was I correct: the VERIFIER's word only — True / False / UNKNOWN
  (an unverified outcome is never called correct or wrong);
- what surprised me: a refuted prediction, or declared surprisal;
- what I learned: the learning loop's own record (novelty, verdict,
  stored memory);
- should I change my model: honest counsel — a refuted prediction says
  expectations need updating; a REPEATED verified failure becomes an
  open unknown registered with curiosity ("why does this keep
  failing?") so the mind keeps working on it;
- should I remember this: what the learning loop already decided
  (stored vs rehearsed).

Triggers: verified actions (the verifier gave a definite word) are
important experiences; the door reflects on them automatically. The
reflection is recorded with the epistemic label 'reflection' and never
acts.

Honesty rules:
- no verdict without the verifier's word — UNKNOWN is preserved;
- counsel describes what the evidence supports, nothing more;
- reflecting performs nothing.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

_SURPRISE_THRESHOLD = 0.5  # declared surprisal above this reads as surprise


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join(sorted(_terms(str(text))))


class Reflection:
    """After important experiences, answer the roadmap's questions from
    evidence. Records; never acts."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_reflections (
                    reflection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reflected_at TEXT NOT NULL,
                    content TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    kind TEXT,
                    what_happened TEXT NOT NULL,
                    what_i_believed TEXT,
                    was_i_correct TEXT,
                    what_surprised_me TEXT,
                    what_i_learned TEXT,
                    should_change_model TEXT,
                    should_remember TEXT,
                    acted INTEGER NOT NULL DEFAULT 0
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Reflection ledger unavailable: {exc}")

    # ── the reflection ───────────────────────────────────────────────────
    def reflect_on(self, experience: Dict[str, Any]) -> Dict[str, Any]:
        """One experience → the roadmap's questions, answered from
        evidence."""
        content = str(experience.get("content") or "").strip()
        if not content:
            return {"success": False, "reason": "no experience to reflect on"}
        kind = str(experience.get("kind") or "experience")
        success = experience.get("success")
        action_type = str(experience.get("goal_type") or "").strip()

        happened = (f"{kind}: '{content[:160]}'"
                    + (f" → outcome '{experience.get('outcome')}'"
                       if experience.get("outcome") else ""))

        believed = self._belief(action_type, content)
        correct = self._correctness(success)
        surprised = self._surprise(success, believed, experience)
        learned = self._learning(content)
        change = self._counsel(content, success, believed)
        remember = self._memory_decision(learned)

        row = {"content": content[:400], "kind": kind,
               "what_happened": happened,
               "what_i_believed": believed.get("statement"),
               "was_i_correct": correct.get("verdict"),
               "what_surprised_me": surprised.get("statement"),
               "what_i_learned": learned.get("statement"),
               "should_change_model": change.get("statement"),
               "should_remember": remember}
        self._persist(row)
        return {"success": True, "epistemic_kind": "reflection",
                "what_happened": happened,
                "what_i_believed": believed,
                "was_i_correct": correct,
                "what_surprised_me": surprised,
                "what_i_learned": learned,
                "should_change_model": change,
                "should_remember": remember,
                "acted": False}  # reflecting performs nothing

    # ── each question, from evidence ─────────────────────────────────────
    def _belief(self, action_type: str, content: str) -> Dict[str, Any]:
        """What she predicted — only when she actually simulated."""
        if not action_type:
            return {"known": False,
                    "statement": "no simulation recorded — nothing believed "
                                 "in advance"}
        try:
            records = self.mind.imagination.records(limit=100)
        except Exception:
            records = []
        for row in records:
            if str(row.get("action_type")) == action_type:
                return {"known": True,
                        "statement": (f"I expected: {row.get('expected')} "
                                      f"(confidence {row.get('confidence')})"),
                        "expected": row.get("expected"),
                        "confidence": row.get("confidence")}
        return {"known": False,
                "statement": f"no simulation recorded for '{action_type}'"}

    @staticmethod
    def _correctness(success: Any) -> Dict[str, Any]:
        """The verifier's word only — attempted ≠ succeeded, and a missing
        verdict stays UNKNOWN."""
        if success is True:
            return {"verdict": "correct", "known": True,
                    "statement": "the verifier confirmed success"}
        if success is False:
            return {"verdict": "wrong", "known": True,
                    "statement": "the verifier said it did not succeed"}
        return {"verdict": None, "known": False,
                "statement": "no verifier's word — correctness stays "
                             "UNKNOWN (never guessed)"}

    def _surprise(self, success: Any, believed: Dict[str, Any],
                  experience: Dict[str, Any]) -> Dict[str, Any]:
        """Surprise = reality against expectation, evidenced."""
        surprisal = experience.get("surprisal")
        if isinstance(surprisal, (int, float)) \
                and float(surprisal) >= _SURPRISE_THRESHOLD:
            return {"surprised": True,
                    "statement": f"declared surprisal {float(surprisal):.2f}"}
        if believed.get("known") and success is False:
            return {"surprised": True,
                    "statement": "I expected to succeed; the verifier "
                                 "refuted it"}
        if believed.get("known") and success is True:
            return {"surprised": False,
                    "statement": "reality matched the prediction"}
        return {"surprised": False,
                "statement": "no expectation recorded — nothing to be "
                             "surprised by"}

    def _learning(self, content: str) -> Dict[str, Any]:
        """What the one learning loop recorded about this experience."""
        try:
            events = self.mind.learning.events(limit=100)
        except Exception:
            events = []
        key = _norm(content)
        for row in events:
            if _norm(str(row.get("content") or "")) == key:
                return {"known": True,
                        "statement": (f"novelty: {row.get('novelty')}; "
                                      f"verdict: {row.get('verdict')}"),
                        "novelty": row.get("novelty"),
                        "stored_memory_id": row.get("stored_memory_id")}
        return {"known": False,
                "statement": "not (yet) in the learning ledger"}

    def _counsel(self, content: str, success: Any,
                 believed: Dict[str, Any]) -> Dict[str, Any]:
        """Should she change her model? Evidence-driven counsel; a repeated
        verified failure becomes an open unknown the mind keeps working
        on."""
        if believed.get("known") and success is False:
            return {"change": True,
                    "statement": "the prediction was refuted — expectations "
                                 "for this action need updating (the "
                                 "training data already records it)"}
        if success is False:
            # The ledger already holds this failure (learning runs before
            # reflection at the door), so the count INCLUDES the current
            # one: one failure is data, two verified failures are a
            # pattern.
            fails = self._prior_failures(content)
            if fails >= 2:
                self._register_unknown(content, fails)
                return {"change": True,
                        "statement": (f"this has now failed {fails}× "
                                      f"(verified) — registered as an open "
                                      f"unknown so the mind keeps working "
                                      f"on it")}
            return {"change": False,
                    "statement": "a single verified failure — data, not yet "
                                 "a pattern"}
        if success is True:
            return {"change": False,
                    "statement": "verified success — the current model "
                                 "holds"}
        return {"change": False,
                "statement": "no verified outcome — no model change is "
                             "justified"}

    def _prior_failures(self, content: str) -> int:
        key = _norm(content)
        count = 0
        try:
            for row in self.mind.learning.events(limit=200):
                if row.get("success") is False and \
                        _norm(str(row.get("content") or "")) == key:
                    count += 1
        except Exception:
            pass
        return count

    def _register_unknown(self, content: str, times: int) -> None:
        try:
            self.mind.curiosity.register(
                f"why does this keep failing: {content[:120]}",
                source="reflection",
                context=f"verified failure ×{times}")
        except Exception as exc:
            app_logger.warning(f"Failure-pattern unknown not registered "
                               f"(non-fatal): {exc}")

    @staticmethod
    def _memory_decision(learned: Dict[str, Any]) -> str:
        if learned.get("stored_memory_id"):
            return "yes — stored as durable memory"
        if learned.get("known") and learned.get("novelty") == "reinforces":
            return "rehearsed, not re-stored — the loop dedupes"
        return "no storage decision recorded"

    # ── surfaces ─────────────────────────────────────────────────────────
    def reflections(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_reflections ORDER BY "
                    "reflection_id DESC LIMIT ?", (int(limit),)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def lessons(self, limit: int = 30) -> List[Dict[str, Any]]:
        """The model-changing reflections — what she decided to carry
        forward."""
        def _is_lesson(row: Dict[str, Any]) -> bool:
            counsel = str(row.get("should_change_model") or "")
            return "need updating" in counsel or "open unknown" in counsel
        return [r for r in self.reflections(limit=200)
                if _is_lesson(r)][:int(limit)]

    def stats(self) -> Dict[str, Any]:
        rows = self.reflections(limit=10000)
        by_verdict: Dict[str, int] = {}
        surprised = changed = 0
        for r in rows:
            key = r.get("was_i_correct") or "unknown"
            by_verdict[key] = by_verdict.get(key, 0) + 1
            surprise_line = str(r.get("what_surprised_me") or "")
            if surprise_line and "matched" not in surprise_line \
                    and "nothing to be" not in surprise_line:
                surprised += 1
            counsel = str(r.get("should_change_model") or "")
            if "need updating" in counsel or "open unknown" in counsel:
                changed += 1
        return {"reflections": len(rows), "by_verdict": by_verdict,
                "surprises": surprised, "model_changes": changed,
                "policy": "reflect after important experiences; the "
                          "verifier's word only — UNKNOWN preserved; "
                          "reflecting performs nothing"}

    def snapshot(self) -> Dict[str, Any]:
        return self.stats()

    # ── internals ────────────────────────────────────────────────────────
    def _persist(self, row: Dict[str, Any]) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_reflections
                       (reflected_at, content, norm, kind, what_happened,
                        what_i_believed, was_i_correct, what_surprised_me,
                        what_i_learned, should_change_model, should_remember,
                        acted)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (_now_iso(), row["content"], _norm(row["content"]),
                     row.get("kind"), row["what_happened"],
                     row.get("what_i_believed"), row.get("was_i_correct"),
                     row.get("what_surprised_me"),
                     row.get("what_i_learned"),
                     row.get("should_change_model"),
                     row.get("should_remember")))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Reflection not persisted: {exc}")
