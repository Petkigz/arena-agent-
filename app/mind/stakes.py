"""Stakes — post-roadmap growth (audit item #22): effort calibrated to
what a task costs if it fails.

"Does she try equally hard at everything, or does effort follow
stakes?" One uniform effort level is either wasteful on trivia or
careless with what matters. ``assess(task)`` computes the stakes of a
request from FOUR deterministic signals out of her own record — never
from vibes:

1. RISK MARKERS in the words themselves — destroying data, moving
   money, contacting people on the owner's behalf;
2. OWNER EMPHASIS — the owner said it matters ("important",
   "carefully", "exactly", …);
3. HER OWN VERIFIED FAILURE HISTORY on the topic — a place she has
   failed verified 2+ times is exactly where casual effort is least
   affordable;
4. THE OWNER'S AUTHORITY RULES touching the topic — the owner wrote a
   rule about it because it matters.

Score → level: ROUTINE (0–1), CAREFUL (2–3), CRITICAL (4+). Each level
carries a concrete, auditable EFFORT PLAN — what extra care the level
buys: re-reading her own record before acting, verifying the result
against the ledger, running the shadow advocate before relying on a
conclusion, confirming irreversible steps with the owner. The plans
NEST: critical includes careful includes routine.

Honesty rules:
- stakes are computed from evidence on file, never invented;
- the organ ASSESSES and RECORDS — it never executes, never vetoes;
  the decision still belongs to the owner's authority;
- a low-stakes verdict is honest too: not everything needs ceremony.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mind.authority import _content_terms
from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

# Evidence gate for "her own record touches this topic" — same spirit
# as the learning loop / scrutiny gates.
_OVERLAP_THRESHOLD = 0.3

# Words in the request itself that mark what failure would cost.
_RISK_CATEGORIES: Dict[str, List[str]] = {
    "destroys_data": ["delete", "erase", "format", "wipe", "uninstall",
                      "drop", "purge", "overwrite"],
    "money": ["pay", "purchase", "buy", "charge", "transfer", "invoice",
              "refund", "subscription"],
    "outward_comms": ["send", "email", "message", "post", "publish",
                      "reply", "notify", "announce"],
}

# The owner said it matters.
_EMPHASIS_MARKERS = {
    "important", "critical", "crucial", "vital", "urgent", "careful",
    "carefully", "exactly", "precisely", "must", "definitely",
}

_LEVELS = (("routine", 2), ("careful", 4), ("critical", None))

_EFFORT_PLANS: Dict[str, List[str]] = {
    "routine": [
        "run the standard cycle",
        "record the outcome honestly — attempted is not succeeded",
    ],
    "careful": [
        "re-read her own record on this topic before acting",
        "verify the result against the ledger before calling it done",
    ],
    "critical": [
        "run the shadow advocate (scrutiny) on any conclusion about it "
        "before relying on it",
        "confirm irreversible steps with the owner first — the decision "
        "belongs to the owner",
    ],
}


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


class Stakes:
    """Effort follows stakes: assesses what a task costs if it fails
    from evidence on file, and returns the effort plan the level buys.
    Assesses and records — never executes, never vetoes."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_stakes (
                    stake_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    task TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    level TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    reasons TEXT NOT NULL,
                    effort_plan TEXT NOT NULL,
                    acted INTEGER NOT NULL DEFAULT 0
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Stakes ledger unavailable: {exc}")

    # ── the assessment ──────────────────────────────────────────────────
    def assess(self, task: str) -> Dict[str, Any]:
        """Compute stakes from four deterministic signals out of her own
        record. Never invents risk; never executes."""
        task = str(task or "").strip()
        if not task:
            return {"success": False, "acted": False,
                    "reason": "nothing to assess"}
        score = 0
        reasons: List[str] = []
        lowered = task.lower()
        words = set(_terms(lowered)) | {
            w.strip(".,!?;:'\"()") for w in lowered.split()}
        for category, markers in sorted(_RISK_CATEGORIES.items()):
            hits = sorted({m for m in markers if m in words})
            if hits:
                score += 2
                reasons.append(f"risk markers ({category}): "
                               f"{', '.join(hits[:3])}")
        emphasis = sorted(_EMPHASIS_MARKERS & words)
        if emphasis:
            score += 2
            reasons.append("owner emphasis: " + ", ".join(emphasis[:3]))
        fails = self._verified_failures_on(task)
        if fails >= 2:
            score += 2
            reasons.append(f"her own record: {fails} verified failure(s) "
                           f"on this topic")
        rule = self._authority_rule_on(task)
        if rule:
            score += 1
            reasons.append(f"owner rule touches this topic: "
                           f"'{rule[:80]}'")
        level = self._level(score)
        plan = self.effort_plan(level)
        row_id = self._record(task, score, level, reasons, plan)
        return {"success": True, "acted": False,
                "epistemic_kind": "stakes",
                "stake_id": row_id, "task": task[:300],
                "level": level, "score": score,
                "reasons": reasons, "effort_plan": plan,
                "policy_note": "effort follows stakes — assessed from "
                               "evidence on file; the organ describes, "
                               "the decision belongs to the owner"}

    def effort_plan(self, level: str) -> List[str]:
        """The concrete care each level buys. Plans NEST: critical
        includes careful includes routine."""
        level = str(level or "routine")
        if level == "critical":
            return ([*_EFFORT_PLANS["routine"],
                     *_EFFORT_PLANS["careful"],
                     *_EFFORT_PLANS["critical"]])
        if level == "careful":
            return [*_EFFORT_PLANS["routine"], *_EFFORT_PLANS["careful"]]
        return list(_EFFORT_PLANS["routine"])

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._rows(limit=int(limit))

    def current(self) -> Optional[Dict[str, Any]]:
        rows = self._rows(limit=1)
        return rows[0] if rows else None

    # ── the four signals (her own record only) ──────────────────────────
    @staticmethod
    def _level(score: int) -> str:
        for name, cap in _LEVELS:
            if cap is None or score < cap:
                return name
        return "routine"

    def _verified_failures_on(self, task: str) -> int:
        key = _norm(task)
        worst = 0
        try:
            for g in self.mind.improvement.detect_gaps():
                if _related(key, str(g.get("norm") or "")):
                    worst = max(worst,
                                int(g.get("verified_failures") or 0))
        except Exception:
            pass
        return worst

    def _authority_rule_on(self, task: str) -> Optional[str]:
        """Read-only: does the owner's rulebook touch this topic? Never
        opens asks — judging stakes is not asking permission."""
        try:
            authority = self.mind.authority
            with sqlite3.connect(authority.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT scope FROM beanie_authority_rules").fetchall()
        except Exception:
            return None
        task_terms = _content_terms(task)
        if not task_terms:
            return None
        for row in rows:
            scope = str(row["scope"] or "")
            rule_terms = _content_terms(scope)
            if not rule_terms:
                continue
            need = 1 if len(rule_terms) <= 1 else 2
            if len(task_terms & rule_terms) >= need:
                return scope
        return None

    # ── surfaces ────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        rows = self._rows(limit=10000)
        by_level: Dict[str, int] = {}
        for r in rows:
            by_level[r["level"]] = by_level.get(r["level"], 0) + 1
        return {"assessments": len(rows), "by_level": by_level,
                "levels": [name for name, _ in _LEVELS],
                "policy": "effort follows stakes: risk markers, owner "
                          "emphasis, her own verified failure history, "
                          "and the owner's rules — all from evidence on "
                          "file; the organ assesses and records, never "
                          "executes, never vetoes"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "stakes", **self.stats(),
                "stream": self.recent(limit=20)}

    # ── internals ────────────────────────────────────────────────────────
    def _record(self, task: str, score: int, level: str,
                reasons: List[str], plan: List[str]) -> Optional[int]:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "INSERT INTO beanie_stakes (created_at, task, norm,"
                    " level, score, reasons, effort_plan, acted) VALUES "
                    "(?,?,?,?,?,?,?,0)",
                    (_now_iso(), task[:500], _norm(task)[:500], level,
                     score, json.dumps(reasons, default=str)[:4000],
                     json.dumps(plan, default=str)[:4000]))
                conn.commit()
                return int(cur.lastrowid)
        except Exception as exc:
            app_logger.warning(f"Stakes record failed (non-fatal): {exc}")
            return None

    def _rows(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM beanie_stakes ORDER BY "
                    "stake_id DESC LIMIT ?", (int(limit),))]
        except Exception:
            return []
        for r in rows:
            for key in ("reasons", "effort_plan"):
                try:
                    r[key] = json.loads(r[key])
                except Exception:
                    pass
            r["acted"] = bool(r["acted"])
        return rows
