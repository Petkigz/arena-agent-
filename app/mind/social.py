"""Social — Phase 16 (Beanie AGI roadmap): the persistent owner model.

The goal is helper + secretary + friend, so she keeps a relationship model:
preferences, habits, communication style, goals, routines, interests,
relationships, boundaries, emotional/contextual cues, history with Beanie.
"This shouldn't mean pretending to be human. It means developing a
persistent relationship model."

Mechanics (deterministic, no LLM):
- ``note(text)`` extracts typed facets from ONE owner utterance using
  explicit markers — preferences ("I like/love/hate/prefer"), boundaries
  ("never …", "don't ever …"), emotion cues ("I'm frustrated/happy/…"),
  relationship mentions ("my wife Ana") which are registered in the
  Phase-5 social store with provenance, and interest nouns worth
  remembering. Every facet carries its evidence (the owner's words).
- routines, communication style, and history are MEASURED from the real
  door ledger (entry timestamps and text), never invented: most-active
  hour needs ≥10 interactions before she claims it; style is average
  length + question/politeness rates; history is first-contact, total
  interactions, days together.
- repeated observations COMPOUND (times_observed), they never duplicate;
- ``model()`` is the current relationship with evidence and counts;
  confidence is observation count, nothing more.

Honesty rules:
- the owner model is a model built from observed evidence — she never
  pretends to be human and never claims a fact she did not observe;
- an empty history yields an empty model (no cold-read);
- boundaries are recorded exactly as said (enforcement is the Phase-18
  authority layer's job; this organ remembers them faithfully).
"""

from __future__ import annotations

import re
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

# facet categories (the roadmap's owner-model checklist)
FACETS = (
    "preference", "boundary", "emotion_cue", "interest", "person",
    "routine", "communication_style", "history",
)

_PREFERENCE_PATTERNS = (
    r"i(?:'m|\s+am)?\s+(?:really\s+|absolutely\s+)?(?:like|love|prefer|hate|enjoy)\b",
    r"i\s+don'?t\s+like\b",
    r"my\s+favo(?:u)rite\b",
    r"always\s+use\b",
)
_BOUNDARY_MARKERS = (
    "never ", "don't ever", "dont ever", "stop doing", "don't do that",
    "dont do that", "not allowed", "forbidden", "don't touch", "dont touch",
)
_EMOTION_WORDS = {
    "frustrated", "happy", "sad", "tired", "stressed", "excited",
    "annoyed", "worried", "proud", "overwhelmed", "calm", "angry",
}
_RELATION_WORDS = {
    "wife", "husband", "partner", "son", "daughter", "brother", "sister",
    "mum", "mom", "mother", "dad", "father", "friend", "boss", "manager",
    "colleague", "neighbor", "neighbour",
}
_STYLE_MIN_ENTRIES = 10  # she won't describe a style from a glance

_PERSON_RE = re.compile(
    r"\bmy\s+(" + "|".join(sorted(_RELATION_WORDS)) + r")\s+([A-Z][a-z]+)",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Social:
    """The persistent owner-relationship model: facets with evidence,
    routines/style/history measured from the real door ledger."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_owner_model (
                    facet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    facet TEXT NOT NULL,
                    key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    times_observed INTEGER NOT NULL DEFAULT 1,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                )""")
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_owner_model_key "
                    "ON beanie_owner_model (facet, key)")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Owner-model ledger unavailable: {exc}")

    # ── one owner utterance → typed facets ───────────────────────────────
    def note(self, text: str) -> Dict[str, Any]:
        """Extract facets from one thing the owner said. Markers only —
        what is not said is not known."""
        text = str(text or "").strip()
        if not text:
            return {"success": False, "reason": "nothing said"}
        low = text.lower()
        found: List[Dict[str, Any]] = []
        marked = False

        for pattern in _PREFERENCE_PATTERNS:
            if re.search(pattern, low):
                found.append(self._facet("preference", text))
                marked = True
                break
        for marker in _BOUNDARY_MARKERS:
            if marker in low:
                found.append(self._facet("boundary", text))
                marked = True
                break
        for word in _EMOTION_WORDS:
            # "i'm frustrated", "i am so frustrated", "feeling a bit tired"
            if re.search(rf"\b(i'?m|i am|feeling|feel)\s+(?:\w+\s+){{0,2}}{word}\b",
                         low):
                found.append(self._facet("emotion_cue", text, key=word))
                marked = True
                break
        for match in _PERSON_RE.finditer(text):
            relation = match.group(1).lower()
            name = match.group(2)
            found.append(self._facet(
                "person", f"owner's {relation}: {name}",
                key=name.lower()))
            self._register_person(name, relation, text)
            marked = True
        # interests come from statements ABOUT something, not from every
        # evaluative sentence: only when no evaluative marker fired
        if not marked:
            for term in self._interest_terms(text)[:3]:
                found.append(self._facet("interest", term, key=term))

        return {"success": True, "epistemic_kind": "owner_model",
                "facets": [f["facet"] for f in found], "notes": found,
                "acted": False}  # listening never acts

    def _facet(self, facet: str, content: str,
               key: Optional[str] = None) -> Dict[str, Any]:
        key = (key or content).strip().lower()[:200]
        content = content.strip()[:400]
        now = _now_iso()
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                row = conn.execute(
                    "SELECT facet_id, times_observed FROM beanie_owner_model "
                    "WHERE facet = ? AND key = ?", (facet, key)).fetchone()
                if row is not None:
                    conn.execute(
                        """UPDATE beanie_owner_model SET content = ?,
                           evidence = ?, times_observed = times_observed + 1,
                           last_seen = ? WHERE facet_id = ?""",
                        (content, content, now, row[0]))
                    times = row[1] + 1
                else:
                    conn.execute(
                        """INSERT INTO beanie_owner_model
                           (facet, key, content, evidence, times_observed,
                            first_seen, last_seen)
                           VALUES (?, ?, ?, ?, 1, ?, ?)""",
                        (facet, key, content, content, now, now))
                    times = 1
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Owner-model facet not persisted: {exc}")
            times = 1
        return {"facet": facet, "key": key, "content": content,
                "times_observed": times}

    def _register_person(self, name: str, relation: str, evidence: str) -> None:
        """The Phase-5 social store holds people; provenance says where the
        knowledge came from."""
        social = getattr(self.mind.memory, "social", None)
        if social is None:
            return
        try:
            existing = social.recall(name)
            if existing is None:
                social.remember(name, kind="person",
                                relationship=f"owner's {relation}",
                                notes=f"mentioned by owner: '{evidence[:120]}'",
                                provenance="owner_conversation")
        except Exception as exc:
            app_logger.warning(f"Person not registered (non-fatal): {exc}")

    @staticmethod
    def _interest_terms(text: str) -> List[str]:
        """Long, non-stopword content words the owner brings up — candidate
        interests. Conservative: length ≥6 keeps out most small talk."""
        counts = Counter(t for t in _terms(text) if len(t) >= 6)
        return [term for term, _ in counts.most_common(3)]

    # ── measured from the real door ledger ───────────────────────────────
    def routines(self) -> Dict[str, Any]:
        """When is she usually needed? Measured from entry timestamps —
        claimed only with enough evidence."""
        hours: List[int] = []
        try:
            entries = self.mind.entries(limit=200)
            for e in entries:
                when = self._parse(e.get("recorded_at"))
                if when is not None:
                    hours.append(when.hour)
        except Exception:
            entries = []
        if len(hours) < _STYLE_MIN_ENTRIES:
            return {"known": False,
                    "reason": f"needs ≥{_STYLE_MIN_ENTRIES} interactions to "
                              f"claim a routine (have {len(hours)})"}
        top_hour, top_n = Counter(hours).most_common(1)[0]
        return {"known": True, "most_active_hour": top_hour,
                "interactions_at_hour": top_n, "measured": len(hours)}

    def style(self) -> Dict[str, Any]:
        """How the owner talks: measured averages, not impressions."""
        try:
            entries = [e for e in self.mind.entries(limit=100)
                       if e.get("modality") != "observation"]
        except Exception:
            entries = []
        texts = [str(e.get("summary") or "") for e in entries if e.get("summary")]
        if len(texts) < _STYLE_MIN_ENTRIES:
            return {"known": False,
                    "reason": f"needs ≥{_STYLE_MIN_ENTRIES} interactions to "
                              f"describe a style (have {len(texts)})"}
        avg_len = sum(len(t) for t in texts) / len(texts)
        questions = sum(1 for t in texts if "?" in t) / len(texts)
        please = sum(1 for t in texts if "please" in t.lower()) / len(texts)
        return {"known": True, "measured": len(texts),
                "avg_message_chars": round(avg_len, 1),
                "question_rate": round(questions, 2),
                "politeness_rate": round(please, 2),
                "summary": ("terse" if avg_len < 40 else
                            "verbose" if avg_len > 160 else "conversational")}

    def history(self) -> Dict[str, Any]:
        """The relationship itself: first contact, total interactions,
        days together."""
        try:
            entries = self.mind.entries(limit=500)
        except Exception:
            entries = []
        if not entries:
            return {"known": False, "reason": "no shared history yet"}
        times = sorted(self._parse(e.get("recorded_at"))
                       for e in entries if self._parse(e.get("recorded_at")))
        if not times:
            return {"known": False, "reason": "history has no timestamps"}
        first = times[0]
        days = max(0, (datetime.now(timezone.utc) - first).days)
        return {"known": True, "interactions": len(entries),
                "first_contact": first.isoformat(), "days_together": days}

    # ── the model ────────────────────────────────────────────────────────
    def model(self) -> Dict[str, Any]:
        """The current relationship with evidence. Confidence is observation
        count, nothing more."""
        facets: Dict[str, List[Dict[str, Any]]] = {}
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_owner_model ORDER BY facet,"
                    " times_observed DESC").fetchall()
            for r in rows:
                facets.setdefault(r["facet"], []).append(dict(r))
        except Exception:
            pass
        people: List[Dict[str, Any]] = []
        social = getattr(self.mind.memory, "social", None)
        if social is not None:
            try:
                people = social.list_people(limit=20)
            except Exception:
                pass
        return {"facets": facets,
                "facet_counts": {k: len(v) for k, v in facets.items()},
                "people": people,
                "routines": self.routines(),
                "communication_style": self.style(),
                "history": self.history(),
                "policy": "owner model = observed evidence with counts; she "
                          "never pretends to be human and never claims what "
                          "she did not observe"}

    def snapshot(self) -> Dict[str, Any]:
        """Compact surface for the state skeleton's owner room."""
        m = self.model()
        return {"facet_counts": m["facet_counts"],
                "people": len(m["people"]),
                "routines": m["routines"],
                "communication_style": m["communication_style"],
                "history": m["history"]}

    # ── internals ────────────────────────────────────────────────────────
    @staticmethod
    def _parse(ts: Any) -> Optional[datetime]:
        try:
            dt = datetime.fromisoformat(str(ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
