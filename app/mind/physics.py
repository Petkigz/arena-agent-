"""Physics — post-roadmap growth (Domain A of the audit): intuitive
physics grounded in her own observations.

"Does she hold expectations about how the physical world behaves — and
notice when the world violates them?" The honest version of intuitive
physics for a desk-bound mind is not a simulated rigid-body engine; it
is the OLDEST physical law there is, applied to her own record:

    PERSISTENCE — what she observed is still so, until a recorded
    event changes it.

``place(subject, state)`` records where or how something is.
``expect(subject)`` says what persistence implies RIGHT NOW, citing the
observation the expectation stands on — or says plainly that she has
no observation on file (physics has nothing to say about what she has
never seen). ``report(subject, observed)`` sets the world against the
expectation:

- match → CONFIRMED — persistence held, the tally grows;
- mismatch → VIOLATION — expected here, observed otherwise, and NO
  recorded event explains the change. That is physical surprise, and
  it is recorded exactly as it is: the world did something her record
  cannot account for. The observation WINS (state updates — the world
  outranks the model), and the unexplained gap is handed to
  curiosity as an open unknown;
- ``explain(subject, cause)`` closes the loop when the owner supplies
  the missing event ("I moved them") — the violation is marked
  explained; surprises are not buried, they are resolved on file.

Honesty rules:
- expectations cite the observation they stand on — never invented;
- a violation is never explained away silently;
- no observation, no expectation — UNKNOWN stays unknown.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

# Door grammar: placement reports and disappearance reports, strictly.
_PLACE_RE = re.compile(
    r"^(?:the\s+)?(?P<subject>[\w][\w .'-]*?)\s+(?:is|are)\s+"
    r"(?P<prep>on|in|at|under|next to)\s+(?P<loc>[\w][\w .'-]*?)\s*[.!?]?$",
    re.IGNORECASE)
_GONE_RE = re.compile(
    r"^(?:the\s+)?(?P<subject>[\w][\w .'-]*?)\s+(?:is|are)\s+"
    r"(?P<gone>gone|missing)\s*[.!?]?$", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    words = str(text).lower().split()
    if words[:1] == ["the"]:
        words = words[1:]
    return " ".join(words)


class IntuitivePhysics:
    """Persistence against her own record: expectations that cite
    their evidence, violations that stay visible until explained.
    Describes; never acts on the world."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_physics_states (
                    state_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    updated_at TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    norm TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    source TEXT NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_physics_checks (
                    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    principle TEXT NOT NULL,
                    expected TEXT,
                    observed TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    explained INTEGER NOT NULL DEFAULT 0,
                    cause TEXT,
                    statement TEXT NOT NULL,
                    acted INTEGER NOT NULL DEFAULT 0
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Physics ledger unavailable: {exc}")

    # ── record where the world is ────────────────────────────────────────
    def place(self, subject: str, state: str,
              source: str = "owner") -> Dict[str, Any]:
        """Record an observed state; persistence takes over from
        here."""
        subject = str(subject or "").strip()
        state = str(state or "").strip()
        if not subject or not state:
            return {"success": False, "acted": False,
                    "reason": "a placement needs a subject and a state"}
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    "INSERT INTO beanie_physics_states (updated_at,"
                    " subject, norm, state, source) VALUES (?,?,?,?,?)"
                    " ON CONFLICT(norm) DO UPDATE SET updated_at ="
                    " excluded.updated_at, subject = excluded.subject,"
                    " state = excluded.state, source = excluded.source",
                    (_now_iso(), subject[:200], _norm(subject)[:200],
                     state[:300], str(source)[:100]))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Physics placement failed (non-fatal): "
                               f"{exc}")
            return {"success": False, "acted": False,
                    "reason": "state ledger unavailable"}
        return {"success": True, "acted": False,
                "epistemic_kind": "physics",
                "subject": subject[:200], "state": state[:300],
                "principle": "persistence",
                "statement": f"recorded — persistence now holds that "
                             f"'{subject[:120]}' is {state[:120]} until "
                             f"a recorded event says otherwise"}

    def expect(self, subject: str) -> Dict[str, Any]:
        """What persistence implies RIGHT NOW — citing the observation
        it stands on. No observation, no expectation."""
        subject = str(subject or "").strip()
        if not subject:
            return {"success": False, "reason": "nothing to expect"}
        row = self._state(_norm(subject))
        if row is None:
            return {"success": True, "acted": False,
                    "epistemic_kind": "physics",
                    "subject": subject[:200], "expected": None,
                    "principle": "persistence",
                    "statement": "no observation on file — physics has "
                                 "nothing to say about what she has "
                                 "never seen"}
        return {"success": True, "acted": False,
                "epistemic_kind": "physics",
                "subject": subject[:200],
                "expected": row["state"],
                "basis_observed_at": row["updated_at"],
                "basis_source": row["source"],
                "principle": "persistence",
                "statement": f"persistence holds that '{subject[:120]}' "
                             f"is {row['state'][:120]} (last observed "
                             f"{row['updated_at']})"}

    # ── the world against the expectation ───────────────────────────────
    def report(self, subject: str, observed: str,
               source: str = "owner") -> Dict[str, Any]:
        """Set the observed world against the expectation. The world
        outranks the model: the state updates either way; a mismatch
        with no recorded cause stays VISIBLE as an unexplained
        violation."""
        subject = str(subject or "").strip()
        observed = str(observed or "").strip()
        if not subject or not observed:
            return {"success": False, "acted": False,
                    "reason": "a report needs a subject and an "
                              "observation"}
        prior = self._state(_norm(subject))
        if prior is None:
            self.place(subject, observed, source=source)
            verdict = "no_prior"
            statement = ("first observation — no expectation to test; "
                         f"'{subject[:120]}' recorded as "
                         f"{observed[:120]}")
            expected = None
        elif _norm(observed) == _norm(prior["state"]):
            verdict = "confirmed"
            expected = prior["state"]
            statement = (f"confirmed — persistence held: "
                         f"'{subject[:120]}' was expected to be "
                         f"{expected[:120]} and was observed so")
        else:
            verdict = "violation"
            expected = prior["state"]
            statement = (f"violation — expected '{subject[:120]}' to be "
                         f"{expected[:120]} (last observed "
                         f"{prior['updated_at']}); observed "
                         f"{observed[:120]}; no recorded event explains "
                         f"the change — unexplained")
        row_id = self._check(subject, expected, observed, verdict,
                             statement)
        if verdict == "violation":
            # The world outranks the model.
            self.place(subject, observed, source=source)
            self._ask_curiosity(subject, expected, observed)
        return {"success": True, "acted": False,
                "epistemic_kind": "physics",
                "check_id": row_id, "subject": subject[:200],
                "principle": "persistence",
                "expected": expected, "observed": observed[:300],
                "verdict": verdict, "statement": statement}

    def explain(self, subject: str, cause: str) -> Dict[str, Any]:
        """The owner supplies the missing event: the most recent
        violation on this subject is marked explained. Surprises are
        resolved on file, never buried."""
        subject = str(subject or "").strip()
        cause = str(cause or "").strip()
        if not subject or not cause:
            return {"success": False, "acted": False,
                    "reason": "an explanation needs a subject and a "
                              "cause"}
        key = _norm(subject)
        target = None
        for c in self._checks(limit=500):
            if c["norm"] == key and c["verdict"] == "violation" \
                    and not c["explained"]:
                target = c
                break
        if target is None:
            return {"success": False, "acted": False,
                    "reason": "no unexplained violation on file for "
                              f"'{subject[:120]}'"}
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    "UPDATE beanie_physics_checks SET explained = 1,"
                    " cause = ? WHERE check_id = ?",
                    (cause[:300], target["check_id"]))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Physics explanation failed "
                               f"(non-fatal): {exc}")
            return {"success": False, "acted": False,
                    "reason": "check ledger unavailable"}
        return {"success": True, "acted": False,
                "epistemic_kind": "physics",
                "check_id": target["check_id"],
                "subject": subject[:200], "cause": cause[:300],
                "statement": f"explained — the missing event was: "
                             f"{cause[:160]}"}

    def note(self, text: str) -> Optional[Dict[str, Any]]:
        """The door's grammar, strictly: placement reports ('the keys
        are on the hook') become expectations; disappearance reports
        ('the keys are gone') are tested against them. Anything else —
        nothing, never guessed."""
        text = str(text or "").strip()
        if not text:
            return None
        m = _PLACE_RE.match(text)
        if m:
            return self.place(m.group("subject").strip(),
                              f"{m.group('prep')} {m.group('loc').strip()}",
                              source="owner_speech")
        m = _GONE_RE.match(text)
        if m:
            return self.report(m.group("subject").strip(),
                               m.group("gone").lower(),
                               source="owner_speech")
        return None

    def checks(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._checks(limit=int(limit))

    # ── surfaces ────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        rows = self._checks(limit=10000)
        by_verdict: Dict[str, int] = {}
        for r in rows:
            by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
        unexplained = sum(1 for r in rows
                          if r["verdict"] == "violation"
                          and not r["explained"])
        return {"checks": len(rows), "by_verdict": by_verdict,
                "unexplained_violations": unexplained,
                "states_tracked": len(self._states()),
                "policy": "persistence: what she observed is still so "
                          "until a recorded event changes it; "
                          "expectations cite their evidence; a "
                          "violation with no recorded cause stays "
                          "visible until explained; no observation, no "
                          "expectation"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "physics", **self.stats(),
                "stream": self.checks(limit=20),
                "states": self._states()[:20]}

    # ── internals ────────────────────────────────────────────────────────
    def _ask_curiosity(self, subject: str, expected: str,
                       observed: str) -> None:
        """Physical surprise is an open unknown — hand it to curiosity,
        fail-open."""
        try:
            self.mind.curiosity.register(
                f"why did '{subject[:80]}' change from "
                f"{expected[:60]} to {observed[:60]} with no recorded "
                f"event",
                source="physics_violation",
                context="intuitive physics: persistence violated")
        except Exception as exc:
            app_logger.warning(f"Physics curiosity handoff failed "
                               f"(non-fatal): {exc}")

    def _state(self, norm: str) -> Optional[Dict[str, Any]]:
        for s in self._states():
            if s["norm"] == norm:
                return s
        return None

    def _states(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                return [dict(r) for r in conn.execute(
                    "SELECT * FROM beanie_physics_states ORDER BY "
                    "state_id DESC LIMIT 500")]
        except Exception:
            return []

    def _check(self, subject: str, expected: Optional[str],
               observed: str, verdict: str,
               statement: str) -> Optional[int]:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "INSERT INTO beanie_physics_checks (created_at,"
                    " subject, norm, principle, expected, observed,"
                    " verdict, explained, statement, acted) VALUES "
                    "(?,?,?,?,?,?,?,0,?,0)",
                    (_now_iso(), subject[:200], _norm(subject)[:200],
                     "persistence", expected, observed[:300], verdict,
                     statement))
                conn.commit()
                return int(cur.lastrowid)
        except Exception as exc:
            app_logger.warning(f"Physics check record failed "
                               f"(non-fatal): {exc}")
            return None

    def _checks(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM beanie_physics_checks ORDER BY "
                    "check_id DESC LIMIT ?", (int(limit),))]
        except Exception:
            return []
        for r in rows:
            r["explained"] = bool(r["explained"])
            r["acted"] = bool(r["acted"])
        return rows
