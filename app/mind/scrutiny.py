"""Scrutiny — post-roadmap growth (audit item #25): the devil's advocate.

"In your reasoning chain, is there a dedicated subroutine that actively
tries to disprove its own favorite conclusions, assigning a shadow
advocate to every high-confidence decision? True intelligence doubts
itself."

``scrutinize(conclusion)`` argues the OPPOSITE case — using only
evidence from her own ledgers, never invented counter-arguments:

- verified FAILURES of overlapping content (the learning ledger);
- reflections where the verifier called her WRONG about it;
- predictions the verifier REFUTED (the imagination ledger);
- improvement gaps still open on it (repeated verified failure);
- open UNKNOWNS touching it — what she herself admits she doesn't
  know about it.

Any counter-evidence CONTESTS the conclusion; none found means it
SURVIVED this scrutiny — and that is reported exactly as it is: the
absence of counter-evidence, never proof. The doubt ledger keeps only
contested conclusions; every scrutiny is recorded either way.

The door runs the shadow advocate on VERIFIED SUCCESSES — success in
the face of contrary history is exactly when survivorship bias bites,
so that is when the doubt is most valuable. Scrutiny describes; it
never acts, never vetoes.

Honesty rules:
- counter-arguments come from her own record, never fabricated;
- surviving scrutiny is not proof — it is only the absence of a
  counter-case on file;
- the advocate doubts; the decision still belongs to the owner's
  authority and the verifier's word.
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

# The evidence gate: counter-evidence must share this much vocabulary
# with the conclusion (same spirit as the learning loop's evidence
# gate) — loose hits do not manufacture doubt.
_OVERLAP_THRESHOLD = 0.3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join(sorted(_terms(str(text))))


def _related(norm_a: str, norm_b: str) -> bool:
    ta = set(norm_a.split()) if norm_a else set()
    tb = set(norm_b.split()) if norm_b else set()
    if not ta or not tb:
        return False
    shared = ta & tb
    if not shared:
        return False
    return len(shared) / len(ta | tb) >= _OVERLAP_THRESHOLD


class Scrutiny:
    """The shadow advocate: argues the opposite case from her own
    record; records whether the conclusion survived. Doubts, never
    acts."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_scrutinies (
                    scrutiny_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    conclusion TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    source TEXT NOT NULL,
                    survived INTEGER NOT NULL,
                    counter_evidence TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    acted INTEGER NOT NULL DEFAULT 0
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Scrutiny ledger unavailable: {exc}")

    # ── the advocate ─────────────────────────────────────────────────────
    def scrutinize(self, conclusion: str, source: str = "owner_surface"
                   ) -> Dict[str, Any]:
        """Argue the opposite case from her own ledgers. Never invents
        counter-evidence; never claims proof."""
        conclusion = str(conclusion or "").strip()
        if not conclusion:
            return {"success": False, "acted": False,
                    "reason": "nothing to scrutinize"}
        key = _norm(conclusion)
        counter: List[Dict[str, Any]] = []
        counter.extend(self._contrary_failures(key))
        counter.extend(self._wrong_reflections(key))
        counter.extend(self._refuted_predictions(key))
        counter.extend(self._open_gaps(key))
        counter.extend(self._touching_unknowns(key))
        survived = not counter
        if survived:
            statement = ("no counter-evidence on file — the conclusion "
                         "survived THIS scrutiny (absence of a "
                         "counter-case, never proof)")
        else:
            kinds = sorted({c["kind"] for c in counter})
            statement = (f"contested — {len(counter)} piece(s) of her "
                         f"own record argue against it "
                         f"({', '.join(kinds)}); doubt before relying "
                         f"on it")
        row_id = self._record(conclusion, key, str(source)[:100],
                              survived, counter, statement)
        return {"success": True, "acted": False,
                "epistemic_kind": "scrutiny",
                "scrutiny_id": row_id, "conclusion": conclusion,
                "survived": survived,
                "confidence_after": "uncontested" if survived
                else "contested",
                "counter_evidence": counter,
                "statement": statement}

    def doubts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Only CONTESTED conclusions — the live doubt ledger."""
        return [r for r in self._rows(limit=500)
                if not r["survived"]][:int(limit)]

    def scrutinies(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._rows(limit=int(limit))

    # ── counter-evidence hunters (her own record only) ───────────────────
    def _contrary_failures(self, key: str) -> List[Dict[str, Any]]:
        found = []
        try:
            for row in self.mind.learning.events(limit=300):
                if row.get("success") is not False:
                    continue
                if _related(key, _norm(str(row.get("content") or ""))):
                    found.append({"kind": "verified_failure",
                                  "content": str(row.get("content"))[:160],
                                  "recorded_at": row.get("recorded_at")})
        except Exception:
            pass
        return found[:5]

    def _wrong_reflections(self, key: str) -> List[Dict[str, Any]]:
        found = []
        try:
            for r in self.mind.reflection.reflections(limit=300):
                if r.get("was_i_correct") != "wrong":
                    continue
                if _related(key, _norm(str(r.get("content") or ""))):
                    found.append({"kind": "was_wrong_before",
                                  "content": str(r.get("content"))[:160],
                                  "counsel": str(r.get(
                                      "should_change_model") or "")[:160]})
        except Exception:
            pass
        return found[:5]

    def _refuted_predictions(self, key: str) -> List[Dict[str, Any]]:
        found = []
        try:
            for r in self.mind.imagination.records(limit=300):
                if r.get("verdict") != "refuted":
                    continue
                if _related(key, _norm(str(r.get("action_type") or ""))):
                    found.append({"kind": "refuted_prediction",
                                  "content": str(r.get("action_type"))[:160],
                                  "expected": r.get("expected")})
        except Exception:
            pass
        return found[:5]

    def _open_gaps(self, key: str) -> List[Dict[str, Any]]:
        found = []
        try:
            for g in self.mind.improvement.detect_gaps():
                if _related(key, str(g.get("norm") or "")):
                    found.append({"kind": "open_gap",
                                  "content": str(g.get("content"))[:160],
                                  "verified_failures":
                                      g.get("verified_failures")})
        except Exception:
            pass
        return found[:5]

    def _touching_unknowns(self, key: str) -> List[Dict[str, Any]]:
        found = []
        try:
            for u in self.mind.curiosity.curiosities(limit=200):
                topic = str(u.get("topic") or "")
                if _related(key, _norm(topic)):
                    found.append({"kind": "admitted_unknown",
                                  "content": topic[:160],
                                  "context": u.get("context")})
        except Exception:
            pass
        return found[:5]

    # ── surfaces ────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        rows = self._rows(limit=10000)
        contested = sum(1 for r in rows if not r["survived"])
        return {"scrutinies": len(rows), "doubts": contested,
                "survived": len(rows) - contested,
                "policy": "the advocate argues from her own record, "
                          "never invents; surviving scrutiny is the "
                          "absence of a counter-case, never proof; "
                          "doubt describes — the decision belongs to "
                          "the owner's authority and the verifier's "
                          "word"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "scrutiny", **self.stats(),
                "doubts": self.doubts(limit=20)}

    # ── internals ────────────────────────────────────────────────────────
    def _record(self, conclusion: str, norm: str, source: str,
                survived: bool, counter: List[Dict[str, Any]],
                statement: str) -> Optional[int]:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "INSERT INTO beanie_scrutinies (created_at,"
                    " conclusion, norm, source, survived, counter_evidence,"
                    " statement, acted) VALUES (?,?,?,?,?,?,?,0)",
                    (_now_iso(), conclusion[:500], norm, source,
                     1 if survived else 0,
                     json.dumps(counter, default=str)[:8000], statement))
                conn.commit()
                return int(cur.lastrowid)
        except Exception as exc:
            app_logger.warning(f"Scrutiny record failed (non-fatal): "
                               f"{exc}")
            return None

    def _rows(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM beanie_scrutinies ORDER BY "
                    "scrutiny_id DESC LIMIT ?", (int(limit),))]
        except Exception:
            return []
        for r in rows:
            try:
                r["counter_evidence"] = json.loads(r["counter_evidence"])
            except Exception:
                pass
            r["survived"] = bool(r["survived"])
            r["acted"] = bool(r["acted"])
        return rows
