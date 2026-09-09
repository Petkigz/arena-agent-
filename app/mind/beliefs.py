"""Beliefs — post-roadmap growth (audit item #20): false-belief theory
of mind.

"Can it hold the concept that YOU hold a false belief about a
situation, and choose to guide you WITHOUT correcting you — because it
understands that correction isn't what you need right now? Can it track
what you think it knows?"

The belief model tracks what the OWNER believes — separately from what
the evidence shows — and chooses the gracious response:

- ``note(owner_text)`` captures belief statements ("I think X works",
  "I believe Y is broken…") with their sentiment — the owner's words,
  never inferred beyond markers; restated beliefs compound;
- ``check(subject)`` sets the owner's belief against her OWN record of
  verified outcomes for the same thing: corroborated by evidence,
  CONTESTED by evidence (a false belief, in either direction), or
  UNKNOWN — nothing on record either way, said plainly;
- ``guide(subject)`` is the behavior the audit asked for: a contested
  belief is met with acknowledgment + her own record + the decision
  left to the owner — never "you are wrong"; a corroborated belief is
  affirmed; an unknown one says so and offers to find out together.

The door captures beliefs from the owner's speech (best-effort). She
models the owner's mind; she never edits it.

Honesty rules:
- beliefs come from what the owner SAID, never mind-read beyond
  markers;
- a belief is contested only by VERIFIED evidence (the verifier's
  word), never by opinion;
- guidance acknowledges first; the decision stays the owner's.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

_OVERLAP_THRESHOLD = 0.3

# Deterministic markers: belief grammar and sentiment vocabulary.
_BELIEF_MARKERS = (
    "i think", "i believe", "i feel like", "i assume", "i guess",
    "i thought", "i expect", "i'm sure", "i am sure", "in my opinion",
    "seems to me", "looks to me", "the way i see it", "if you ask me",
)
_POSITIVE = frozenset({
    "works", "work", "working", "fine", "good", "great", "ok", "okay",
    "stable", "reliable", "fast", "solid", "fixed", "healthy",
    "perfect", "smooth",
})
_NEGATIVE = frozenset({
    "broken", "breaks", "fails", "fail", "failing", "failed", "crash",
    "crashes", "crashing", "slow", "slower", "buggy", "busted", "dead",
    "unstable", "unreliable", "wrong", "bad", "awful", "never",
})
_SENTIMENT_STOP = frozenset({
    "i", "think", "believe", "feel", "like", "assume", "guess",
    "thought", "expect", "sure", "am", "in", "my", "opinion", "seems",
    "to", "me", "looks", "the", "way", "see", "it", "if", "you", "ask",
    "is", "are", "was", "were", "be", "that", "really", "just", "still",
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join(sorted(_terms(str(text))))


def _subject_terms(text: str) -> List[str]:
    return [t for t in _terms(str(text)) if t not in _SENTIMENT_STOP]


def _related(a: str, b: str) -> bool:
    ta = set(a.split()) if a else set()
    tb = set(b.split()) if b else set()
    if not ta or not tb:
        return False
    shared = ta & tb
    return bool(shared) and len(shared) / len(ta | tb) >= _OVERLAP_THRESHOLD


class BeliefModel:
    """What the owner believes, held separately from what the evidence
    shows — and the gracious way to bridge the two."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_beliefs (
                    belief_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    content TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    subject_norm TEXT NOT NULL,
                    sentiment TEXT NOT NULL,
                    times_stated INTEGER NOT NULL DEFAULT 1,
                    last_stated TEXT NOT NULL
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Belief ledger unavailable: {exc}")

    # ── capture: what the owner said they believe ────────────────────────
    def note(self, owner_text: str) -> Optional[Dict[str, Any]]:
        """Capture a belief statement if the owner's words carry belief
        markers — never inferred beyond that. Restated beliefs
        compound."""
        text = str(owner_text or "").strip()
        low = text.lower()
        if not text or not any(m in low for m in _BELIEF_MARKERS):
            return None
        tokens = _terms(text)
        sentiment = "neutral"
        if any(t in _POSITIVE for t in tokens):
            sentiment = "positive"
        if any(t in _NEGATIVE for t in tokens):
            sentiment = ("mixed" if sentiment == "positive" else "negative")
        subject = " ".join(sorted(_subject_terms(text)))
        norm = _norm(text)
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT belief_id, times_stated FROM beanie_beliefs "
                    "WHERE norm=?", (norm,)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE beanie_beliefs SET times_stated=?,"
                        " last_stated=? WHERE belief_id=?",
                        (row["times_stated"] + 1, _now_iso(),
                         row["belief_id"]))
                    conn.commit()
                    return {"captured": True, "compounded": True,
                            "belief_id": row["belief_id"],
                            "times_stated": row["times_stated"] + 1,
                            "sentiment": sentiment}
                cur = conn.execute(
                    "INSERT INTO beanie_beliefs (created_at, content,"
                    " norm, subject_norm, sentiment, times_stated,"
                    " last_stated) VALUES (?,?,?,?,?,1,?)",
                    (_now_iso(), text[:500], norm, subject, sentiment,
                     _now_iso()))
                conn.commit()
                return {"captured": True, "compounded": False,
                        "belief_id": int(cur.lastrowid),
                        "times_stated": 1, "sentiment": sentiment,
                        "acted": False, "epistemic_kind": "belief"}
        except Exception as exc:
            app_logger.warning(f"Belief note skipped (non-fatal): {exc}")
            return None

    def beliefs(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                return [dict(r) for r in conn.execute(
                    "SELECT * FROM beanie_beliefs ORDER BY belief_id "
                    "DESC LIMIT ?", (int(limit),))]
        except Exception:
            return []

    # ── check: the owner's belief vs her verified record ─────────────────
    def check(self, subject: str) -> Dict[str, Any]:
        """Set what the owner believes against what the verifier has
        actually said about the same thing."""
        subject = str(subject or "").strip()
        if not subject:
            return {"success": False, "reason": "nothing to check"}
        belief = self._belief_about(subject)
        if belief is None:
            return {"success": False,
                    "reason": "no belief of the owner's on record about "
                              "this — nothing to hold against the "
                              "evidence"}
        fails = successes = 0
        try:
            for row in self.mind.learning.events(limit=1000):
                ev_norm = _norm(str(row.get("content") or ""))
                if not _related(belief["subject_norm"], ev_norm):
                    continue
                if row.get("success") is False:
                    fails += 1
                elif row.get("success") is True:
                    successes += 1
        except Exception:
            pass
        sentiment = belief["sentiment"]
        if fails == 0 and successes == 0:
            stance = "unknown"
            statement = ("the owner believes it, and her record has "
                         "nothing on it either way — UNKNOWN, plainly")
        elif sentiment in ("positive", "mixed") and fails >= 2 \
                and fails > successes:
            stance = "contested"
            statement = (f"the owner's belief runs against "
                         f"{fails} verified failure(s) on record — a "
                         f"false belief, detected from evidence")
        elif sentiment == "negative" and successes >= 1 and fails == 0:
            stance = "contested"
            statement = (f"the owner's belief runs against "
                         f"{successes} verified success(es) and no "
                         f"failures on record — a false belief, "
                         f"detected from evidence")
        elif sentiment == "positive" and successes >= 1:
            stance = "corroborated"
            statement = (f"the evidence backs the owner's belief "
                         f"({successes} verified success(es))")
        elif sentiment == "negative" and fails >= 1:
            stance = "corroborated"
            statement = (f"the evidence backs the owner's belief "
                         f"({fails} verified failure(s))")
        else:
            stance = "inconclusive"
            statement = ("there is evidence, but it neither clearly "
                         "backs nor clearly contests the belief")
        return {"success": True, "acted": False,
                "epistemic_kind": "belief_check",
                "belief": {"content": belief["content"],
                           "sentiment": sentiment,
                           "times_stated": belief["times_stated"]},
                "evidence": {"verified_failures": fails,
                             "verified_successes": successes},
                "stance": stance, "statement": statement}

    # ── guide: acknowledge first, never "you are wrong" ──────────────────
    def guide(self, subject: str) -> Dict[str, Any]:
        """The behavior the audit asked for: a contested belief is met
        with acknowledgment, her own record, and the decision left to
        the owner — guidance, not blunt correction."""
        checked = self.check(subject)
        if not checked.get("success"):
            return checked
        stance = checked["stance"]
        belief_text = checked["belief"]["content"]
        evidence = checked["evidence"]
        if stance == "contested":
            approach = "guide_without_correcting"
            message = (f"you told me you believe: \"{belief_text}\" — I "
                       f"hold that respectfully. My own record shows "
                       f"{evidence['verified_failures']} verified "
                       f"failure(s) and "
                       f"{evidence['verified_successes']} verified "
                       f"success(es) about it. I'm not going to tell "
                       f"you you're wrong — this is what I've seen; the "
                       f"call is yours.")
        elif stance == "corroborated":
            approach = "affirm"
            message = (f"you told me you believe: \"{belief_text}\" — "
                       f"my record agrees with you "
                       f"({evidence['verified_failures']} verified "
                       f"failure(s), "
                       f"{evidence['verified_successes']} verified "
                       f"success(es)).")
        elif stance == "unknown":
            approach = "admit_and_offer"
            message = (f"you told me you believe: \"{belief_text}\" — I "
                       f"have nothing on record about it either way. "
                       f"Tell me if you'd like us to find out together.")
        else:
            approach = "hold_both"
            message = (f"you told me you believe: \"{belief_text}\" — "
                       f"my record is mixed on it; I'll hold both "
                       f"views until the evidence settles.")
        return {"success": True, "acted": False,
                "epistemic_kind": "belief_guidance",
                "stance": stance, "approach": approach,
                "message": message,
                "policy": "acknowledge first; the decision stays the "
                          "owner's — guidance, never blunt correction"}

    # ── surfaces ────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        rows = self.beliefs(limit=10000)
        by_sentiment: Dict[str, int] = {}
        for r in rows:
            by_sentiment[r["sentiment"]] = by_sentiment.get(
                r["sentiment"], 0) + 1
        return {"beliefs": len(rows), "by_sentiment": by_sentiment,
                "policy": "beliefs come from what the owner SAID; a "
                          "belief is contested only by VERIFIED "
                          "evidence; guidance acknowledges first — the "
                          "decision stays the owner's"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "beliefs", **self.stats(),
                "beliefs": self.beliefs(limit=20)}

    # ── internals ────────────────────────────────────────────────────────
    def _belief_about(self, subject: str) -> Optional[Dict[str, Any]]:
        key = " ".join(sorted(_subject_terms(subject))) or _norm(subject)
        best = None
        for b in self.beliefs(limit=500):
            if _related(key, b["subject_norm"]) or \
                    _related(_norm(subject), b["norm"]):
                if best is None or \
                        b["times_stated"] > best["times_stated"]:
                    best = b
        return best
