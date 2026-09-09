"""Paradigms — post-roadmap growth (audit item #21): ontological
paradigm shifts.

"Can she overturn a deep assumption when verified evidence breaks it —
or does she only patch exceptions forever?" Patching the same broken
rule once is adaptation; the SECOND verified counter-example means the
rule itself was wrong. That is when a paradigm shift happens: the
assumption is not edited quietly, it is marked OVERTURNED, the
counter-evidence is kept on file, and the replacement says plainly
what changed.

Where assumptions come from (never invented):

- ``assume(statement)`` captures UNIVERSAL claims from markers in the
  owner's own words — "always", "every time", "whenever", "never" —
  the same discipline as the beliefs organ: no markers, nothing
  captured. Imperatives addressed at HER ("never delete… without
  asking") are the AUTHORITY organ's lane, not ontology, and are
  skipped;
- ``generalize(subject)`` lets her form a PROVISIONAL universal from
  her OWN verified record — a subject with 3+ verified successes and
  zero verified failures may be held as "has held so far" — a
  generalization she can later be wrong about.

``scan()`` sets every held paradigm against the verified ledger:
positive universals are broken by verified FAILURES, negative
universals by verified SUCCESSES (vocabulary overlap gate, same
spirit as the learning loop). One counter-example → STRAINED (noted,
still held). Two or more → OVERTURNED: recorded exactly once, with
the counter-evidence and a replacement that names the shift.

Honesty rules:
- paradigms come from markers or from her own verified tally — never
  from vibes;
- overturning is evidence-driven and permanent in the ledger — she
  does not quietly forget what broke;
- the organ describes the shift; it never executes anything on it.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

# Evidence gate: counter-evidence must share this much vocabulary with
# the paradigm — loose hits do not manufacture a shift.
_OVERLAP_THRESHOLD = 0.3

# Universal-claim markers in the owner's own words. "all" is
# deliberately absent — too noisy ("delete all the files").
_UNIVERSAL_MARKERS = ("always", "every time", "whenever", "constantly",
                      "invariably", "never")
_NEGATIVE_MARKERS = ("never", "cannot", "can't")

# Imperative cues: a rule ADDRESSED AT HER is the authority organ's
# lane, not an ontological claim about the world.
_IMPERATIVE_CUES = ("you", "your", "please", "don't", "do not",
                    "without asking")

# How many verified successes with zero failures before she may hold
# a provisional universal from her own record.
_GENERALIZE_SUCCESSES = 3

# How many verified counter-examples overturn a paradigm.
_OVERTURN_THRESHOLD = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join(sorted(_terms(str(text))))


# Universal markers are grammar, not content — matching a paradigm
# against the record uses the CONTENT terms only, so "always" never
# dilutes (or inflates) the overlap.
_MATCH_STOPS = frozenset(_UNIVERSAL_MARKERS) | {"every", "time"}


def _match_terms(statement: str) -> set:
    return {t for t in _terms(str(statement)) if t not in _MATCH_STOPS}


def _related(norm_a: str, norm_b: str) -> bool:
    ta = set(norm_a.split()) if norm_a else set()
    tb = set(norm_b.split()) if norm_b else set()
    if not ta or not tb:
        return False
    shared = ta & tb
    if not shared:
        return False
    return len(shared) / len(ta | tb) >= _OVERLAP_THRESHOLD


class Paradigms:
    """Deep assumptions, held separately from the cases that test them.
    One counter-example strains a paradigm; two verified counter-
    examples OVERTURN it — the shift is recorded with its evidence.
    Describes; never executes."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_paradigms (
                    paradigm_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    polarity TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    anomalies TEXT NOT NULL,
                    overturned_at TEXT,
                    replacement TEXT,
                    acted INTEGER NOT NULL DEFAULT 0
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Paradigms ledger unavailable: {exc}")

    # ── where assumptions come from ─────────────────────────────────────
    def assume(self, statement: str) -> Optional[Dict[str, Any]]:
        """Capture a universal claim from markers in the owner's own
        words. No markers → nothing captured; imperatives addressed at
        her belong to the authority organ, not ontology."""
        statement = str(statement or "").strip()
        if not statement:
            return None
        lowered = statement.lower()
        if not any(m in lowered for m in _UNIVERSAL_MARKERS):
            return None
        if any(c in lowered for c in _IMPERATIVE_CUES):
            return None
        polarity = "negative" if any(
            m in lowered for m in _NEGATIVE_MARKERS) else "positive"
        key = _norm(statement)
        if self._find(key) is not None:
            return {"captured": False, "compounded": True,
                    "reason": "this universal is already on file"}
        row_id = self._record(statement, key, polarity, "owner_teaching",
                              "held", [])
        return {"captured": True, "acted": False,
                "epistemic_kind": "paradigm",
                "paradigm_id": row_id, "statement": statement[:300],
                "polarity": polarity, "source": "owner_teaching",
                "status": "held",
                "note": "a universal claim, held until the verified "
                        "record says otherwise"}

    def generalize(self, subject: str) -> Dict[str, Any]:
        """Form a PROVISIONAL universal from her OWN verified record:
        a subject with 3+ verified successes and zero verified
        failures may be held as 'has held so far' — a generalization
        she can later be wrong about. Never formed otherwise."""
        subject = str(subject or "").strip()
        if not subject:
            return {"success": False, "acted": False,
                    "reason": "nothing to generalize about"}
        key = _norm(subject)
        existing = self._find_by_subject(key)
        if existing is not None:
            return {"success": True, "acted": False, "formed": False,
                    "reason": "a paradigm about this subject is already "
                              "on file", "paradigm": existing}
        succ = fail = 0
        try:
            for ev in self.mind.learning.events(limit=500):
                if not _related(key, _norm(str(ev.get("content") or ""))):
                    continue
                if ev.get("success") is True:
                    succ += 1
                elif ev.get("success") is False:
                    fail += 1
        except Exception:
            pass
        if fail > 0 or succ < _GENERALIZE_SUCCESSES:
            return {"success": True, "acted": False, "formed": False,
                    "reason": f"no provisional universal: {succ} verified "
                              f"success(es), {fail} verified failure(s) — "
                              f"needs {_GENERALIZE_SUCCESSES} successes "
                              f"and zero failures"}
        statement = (f"{subject} has held so far: {succ} verified "
                     f"success(es), 0 verified failures")
        row_id = self._record(statement, key, "positive", "own_record",
                              "held", [])
        return {"success": True, "acted": False, "formed": True,
                "epistemic_kind": "paradigm",
                "paradigm_id": row_id, "statement": statement[:300],
                "polarity": "positive", "source": "own_record",
                "status": "held",
                "note": "provisional — held only until the record says "
                        "otherwise"}

    # ── the shift mechanism ──────────────────────────────────────────────
    def scan(self) -> Dict[str, Any]:
        """Set every held paradigm against the verified ledger. One
        counter-example → strained (noted, still held); two or more →
        OVERTURNED, recorded exactly once with its evidence."""
        strained, overturned = [], []
        for p in self._rows(limit=10000):
            if p["status"] == "overturned":
                continue
            counter = self._counter_examples(p)
            if not counter:
                if p["status"] != "held" or p["anomalies"]:
                    self._set_state(p["paradigm_id"], "held", [])
                continue
            if len(counter) >= _OVERTURN_THRESHOLD:
                replacement = self._replacement(p, counter)
                self._overturn(p["paradigm_id"], counter, replacement)
                overturned.append({**p, "anomalies": counter,
                                   "replacement": replacement})
            else:
                self._set_state(p["paradigm_id"], "strained", counter)
                strained.append({**p, "anomalies": counter})
        return {"success": True, "acted": False,
                "epistemic_kind": "paradigm_scan",
                "held": len([p for p in self._rows(limit=10000)
                             if p["status"] == "held"]),
                "strained": len(strained),
                "overturned_now": len(overturned),
                "overturned_total": len(self.shifts()),
                "strained_paradigms": strained,
                "overturned": overturned,
                "statement": (f"{len(overturned)} paradigm(s) overturned "
                              f"this scan" if overturned else
                              "no paradigm overturned this scan")}

    def shifts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """The shift history: only OVERTURNED paradigms, with the
        counter-evidence and the replacement that named the change."""
        return [p for p in self._rows(limit=int(limit))
                if p["status"] == "overturned"]

    def paradigms(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._rows(limit=int(limit))

    # ── counter-evidence hunter (her own record only) ───────────────────
    def _counter_examples(self, p: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Positive universals are broken by verified FAILURES;
        negative universals by verified SUCCESSES."""
        wanted = False if p["polarity"] == "positive" else True
        pt = _match_terms(p["statement"])
        found = []
        try:
            for ev in self.mind.learning.events(limit=500):
                if ev.get("success") is not wanted:
                    continue
                et = set(_terms(str(ev.get("content") or "")))
                union = pt | et
                if not (pt & et) or not union:
                    continue
                if len(pt & et) / len(union) < _OVERLAP_THRESHOLD:
                    continue
                found.append({"content": str(ev.get("content"))[:160],
                              "recorded_at": ev.get("recorded_at"),
                              "verified": True})
        except Exception:
            pass
        return found[:8]

    @staticmethod
    def _replacement(p: Dict[str, Any],
                     counter: List[Dict[str, Any]]) -> str:
        n = len(counter)
        return (f"no longer universal — '{p['statement'][:160]}' broke "
                f"against {n} verified counter-example(s); treat it "
                f"case-by-case, not as law")

    # ── surfaces ────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        rows = self._rows(limit=10000)
        by_status: Dict[str, int] = {}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        return {"paradigms": len(rows), "by_status": by_status,
                "overturn_threshold": _OVERTURN_THRESHOLD,
                "generalize_after": _GENERALIZE_SUCCESSES,
                "policy": "paradigms come from markers in the owner's "
                          "words or from her own verified tally — never "
                          "invented; one counter-example strains, two "
                          "verified counter-examples overturn; the "
                          "shift is recorded with its evidence; the "
                          "organ describes, never executes"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "paradigms", **self.stats(),
                "stream": self.paradigms(limit=20)}

    # ── internals ────────────────────────────────────────────────────────
    def _find(self, norm: str) -> Optional[Dict[str, Any]]:
        for p in self._rows(limit=10000):
            if p["norm"] == norm:
                return p
        return None

    def _find_by_subject(self, norm: str) -> Optional[Dict[str, Any]]:
        for p in self._rows(limit=10000):
            if p["norm"] == norm or _related(norm, p["norm"]):
                return p
        return None

    def _record(self, statement: str, norm: str, polarity: str,
                source: str, status: str,
                anomalies: List[Dict[str, Any]]) -> Optional[int]:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "INSERT INTO beanie_paradigms (created_at, statement,"
                    " norm, polarity, source, status, anomalies, acted)"
                    " VALUES (?,?,?,?,?,?,?,0)",
                    (_now_iso(), statement[:500], norm[:500], polarity,
                     source, status,
                     json.dumps(anomalies, default=str)[:8000]))
                conn.commit()
                return int(cur.lastrowid)
        except Exception as exc:
            app_logger.warning(f"Paradigm record failed (non-fatal): "
                               f"{exc}")
            return None

    def _set_state(self, paradigm_id: int, status: str,
                   anomalies: List[Dict[str, Any]]) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    "UPDATE beanie_paradigms SET status = ?, anomalies = ?"
                    " WHERE paradigm_id = ?",
                    (status, json.dumps(anomalies, default=str)[:8000],
                     paradigm_id))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Paradigm state update failed "
                               f"(non-fatal): {exc}")

    def _overturn(self, paradigm_id: int,
                  anomalies: List[Dict[str, Any]],
                  replacement: str) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    "UPDATE beanie_paradigms SET status = 'overturned',"
                    " anomalies = ?, overturned_at = ?, replacement = ?"
                    " WHERE paradigm_id = ? AND status != 'overturned'",
                    (json.dumps(anomalies, default=str)[:8000],
                     _now_iso(), replacement, paradigm_id))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Paradigm overturn failed (non-fatal): "
                               f"{exc}")

    def _rows(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM beanie_paradigms ORDER BY "
                    "paradigm_id DESC LIMIT ?", (int(limit),))]
        except Exception:
            return []
        for r in rows:
            try:
                r["anomalies"] = json.loads(r["anomalies"])
            except Exception:
                pass
            r["acted"] = bool(r["acted"])
        return rows
