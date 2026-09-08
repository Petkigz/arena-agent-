"""Motivation — Phase 15 (Beanie AGI roadmap): goals from evidence, never
from randomness.

The roadmap: needs, curiosity, unfinished goals, owner goals, environment
opportunities, learning opportunities → candidate goals → evaluate
relevance → prioritize → act. And the scenario: "You mentioned yesterday
that you wanted to organize the project. I noticed the files are still
scattered. Do you want me to handle that?"

Mechanics (deterministic, no LLM):
- ``gather()`` collects candidate goals from SIX real evidence sources in
  her own state — open unknowns (curiosity), parked goals waiting for
  evidence (unfinished), goal-shaped owner speech in the door ledger
  (owner goals), important changes and anomalies attention already judged
  (environment), verified-false attempts in the learning ledger (learning
  opportunities), and the anticipation engine's learned-rhythm predictions
  (needs). No evidence → no candidate: goals are never generated randomly.
- relevance is a sum of NAMED contributions (source base, recurrence,
  recency, current-task overlap) — inspectable, not vibes;
- ``prioritize()`` ranks; ``propose()`` turns the top candidate into an
  owner-facing ask built only from its evidence, and offers it to working
  memory (the channel the cognitive cycle already reads). Proposing is a
  question, not an action — ``acted: False`` on every verdict, and an
  accepted goal executes only through the normal door, where the owner's
  authority applies (goal approval ≠ action authorization);
- ``refresh(task)`` is the door pass: gather, rank, and — only when the top
  candidate is strong enough AND the proposal cooldown has elapsed —
  propose once. Declined goals are never re-proposed.

Honesty rules:
- every goal carries its source type and its evidence strings;
- repeated evidence compounds recurrence instead of duplicating goals;
- motivation suggests; it never executes.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

# the roadmap's six sources → deterministic base relevance
SOURCE_BASE = {
    "unfinished_goal": 3.0,   # she already committed; it is parked
    "owner_goal": 3.0,        # the owner asked for it
    "curiosity": 2.0,         # an open unknown that compounds
    "environment": 2.0,       # something important changed
    "learning": 2.0,          # a verified failure is training data
    "need": 1.0,              # a learned-rhythm anticipation
}

# goal-shaped owner speech (the door ledger is scanned for these markers)
_OWNER_GOAL_MARKERS = (
    "want", "need", "please", "should", "todo", "to-do", "remind",
    "tomorrow", "later", "don't forget", "dont forget", "make sure",
    "organize", "when you can", "sometime",
)

AUTO_PROPOSE_SCORE = 5.0     # top candidate must earn this before she asks
AUTO_PROPOSE_COOLDOWN = 10   # interactions between auto-proposals

_OPEN_STATUSES = ("candidate", "proposed")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join(sorted(_terms(str(text))))


def _parse_iso(ts: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


class Motivation:
    """Candidate goals from evidence → relevance → priority → owner-facing
    proposal. Suggests only; never acts."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        self._interactions = 0
        self._last_proposal_interaction = -10**9
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_goals (
                    goal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    evidence TEXT,
                    reasons TEXT,
                    score REAL NOT NULL DEFAULT 0,
                    recurrence INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    ask TEXT
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Motivation ledger unavailable: {exc}")

    # ── the six evidence sources (each fail-open, each honest) ───────────
    def gather(self) -> List[Dict[str, Any]]:
        """Collect candidate goals from her own state. Sources without
        evidence contribute nothing — no random goals."""
        candidates: List[Dict[str, Any]] = []
        for collector in (self._from_curiosity, self._from_unfinished,
                          self._from_owner, self._from_environment,
                          self._from_learning, self._from_needs):
            try:
                candidates.extend(collector())
            except Exception as exc:
                app_logger.warning(f"Goal source skipped (non-fatal): {exc}")
        for cand in candidates:
            self._upsert(cand)
        return candidates

    def _from_curiosity(self) -> List[Dict[str, Any]]:
        out = []
        for row in self.mind.curiosity.curiosities(limit=20):
            topic = str(row.get("topic") or "").strip()
            if not topic:
                continue
            seen = row.get("times_encountered") or 1
            out.append({
                "source": "curiosity", "title": topic[:300],
                "evidence": (f"open unknown; encountered {seen}×; last seen "
                             f"{row.get('last_seen') or '?'}"),
                "recorded_at": row.get("last_seen"),
                "recurrence": int(seen),
            })
        return out

    def _from_unfinished(self) -> List[Dict[str, Any]]:
        from app.cognition.parked_goal_recheck import collect_parked_goals
        out = []
        for row in collect_parked_goals(limit=5):
            goal = str(row.get("goal") or "").strip()
            if not goal:
                continue
            out.append({
                "source": "unfinished_goal", "title": goal[:300],
                "evidence": (f"parked waiting for evidence since "
                             f"{row.get('created_at') or '?'}"),
                "recorded_at": row.get("created_at"), "recurrence": 1,
            })
        return out

    def _from_owner(self) -> List[Dict[str, Any]]:
        out = []
        for row in self.mind.entries(limit=40):
            if row.get("modality") == "observation":
                continue  # the recording lane, not owner speech
            summary = str(row.get("summary") or "")
            low = summary.lower()
            if not any(marker in low for marker in _OWNER_GOAL_MARKERS):
                continue
            out.append({
                "source": "owner_goal", "title": summary[:300],
                "evidence": (f"owner said ({row.get('recorded_at') or '?'}): "
                             f"'{summary[:160]}'"),
                "recorded_at": row.get("recorded_at"), "recurrence": 1,
            })
        return out

    def _from_environment(self) -> List[Dict[str, Any]]:
        out = []
        for row in self.mind.attention.focus_history(limit=30):
            if row.get("level") not in ("important_change", "anomaly"):
                continue
            out.append({
                "source": "environment", "title": str(row.get("content") or "")[:300],
                "evidence": (f"attention verdict: {row.get('level')} "
                             f"({row.get('decided_at') or '?'})"),
                "recorded_at": row.get("decided_at"), "recurrence": 1,
            })
        return out

    def _from_learning(self) -> List[Dict[str, Any]]:
        out = []
        for row in self.mind.learning.events(limit=40):
            if row.get("kind") != "action" or row.get("success") is not False:
                continue  # only VERIFIED failures are learning opportunities
            out.append({
                "source": "learning", "title": str(row.get("content") or "")[:300],
                "evidence": (f"attempt verified false ({row.get('recorded_at') or '?'}); "
                             f"failure is training data"),
                "recorded_at": row.get("recorded_at"), "recurrence": 1,
            })
        return out

    def _from_needs(self) -> List[Dict[str, Any]]:
        from app.perception.anticipation_engine import AnticipationEngine
        engine = AnticipationEngine(db_path=self.db_path)
        out = []
        for p in engine.predict_next(limit=3):
            action = str(getattr(p, "predicted_action", "") or "").strip()
            if not action:
                continue
            out.append({
                "source": "need", "title": f"prepare for: {action}"[:300],
                "evidence": (f"learned rhythm: {getattr(p, 'reason', '?')} "
                             f"(confidence {getattr(p, 'confidence', 0):.2f})"),
                "recorded_at": None, "recurrence": 1,
            })
        return out

    # ── relevance: named contributions, inspectable ──────────────────────
    def evaluate(self, source: str, evidence: str, recurrence: int,
                 recorded_at: Any, task: str = "") -> Tuple[float, List[str]]:
        reasons: List[str] = [f"source '{source}' base "
                              f"{SOURCE_BASE.get(source, 0.0):.1f}"]
        score = SOURCE_BASE.get(source, 0.0)
        extra = max(0, int(recurrence) - 1)
        if extra:
            bonus = float(min(extra, 3))
            score += bonus
            reasons.append(f"recurrence ×{int(recurrence)} (+{bonus:.1f})")
        when = _parse_iso(recorded_at)
        if when is not None and datetime.now(timezone.utc) - when < timedelta(hours=24):
            score += 1.0
            reasons.append("recent evidence (<24h) (+1.0)")
        task_terms = set(_terms(task)) if task else set()
        if task_terms:
            overlap = set(_terms(evidence)) & task_terms
            if overlap:
                score += 1.0
                reasons.append("overlaps the current task (+1.0)")
        return round(score, 2), reasons

    # ── ledger upsert: recurrence compounds, goals don't duplicate ───────
    def _upsert(self, cand: Dict[str, Any]) -> None:
        source = cand["source"]
        title = str(cand["title"]).strip()
        if not title or source not in SOURCE_BASE:
            return
        norm = _norm(f"{source} {title}")
        score, reasons = self.evaluate(source, cand.get("evidence", ""),
                                       cand.get("recurrence", 1),
                                       cand.get("recorded_at"))
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                row = conn.execute(
                    "SELECT goal_id, recurrence FROM beanie_goals WHERE "
                    "norm = ? AND status IN ('candidate', 'proposed')",
                    (norm,)).fetchone()
                now = _now_iso()
                if row is not None:
                    conn.execute(
                        """UPDATE beanie_goals SET recurrence = recurrence + 1,
                           evidence = ?, reasons = ?, score = ?, updated_at = ?
                           WHERE goal_id = ?""",
                        (cand.get("evidence", ""), "|".join(reasons),
                         score, now, row[0]))
                else:
                    conn.execute(
                        """INSERT INTO beanie_goals
                           (created_at, updated_at, source, title, norm,
                            evidence, reasons, score, recurrence, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate')""",
                        (now, now, source, title[:400], norm,
                         cand.get("evidence", ""), "|".join(reasons),
                         score, int(cand.get("recurrence", 1))))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Goal not persisted: {exc}")

    # ── prioritize / propose / decide ────────────────────────────────────
    def prioritize(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT * FROM beanie_goals WHERE status IN ('candidate',
                       'proposed') ORDER BY score DESC, updated_at DESC
                       LIMIT ?""", (int(limit),)).fetchall()
            return [self._hydrate(r) for r in rows]
        except Exception:
            return []

    def propose(self, goal_id: Optional[int] = None) -> Dict[str, Any]:
        """Turn a candidate into an owner-facing question built only from
        its evidence. Proposing never acts."""
        goal = self._goal(goal_id) if goal_id is not None else None
        if goal_id is not None and goal is None:
            return {"success": False, "reason": f"no goal #{goal_id}"}
        if goal is None:
            for cand in self.prioritize():
                if cand["status"] == "candidate":
                    goal = cand
                    break
        if goal is None:
            return {"success": False,
                    "reason": "no candidate goal to propose — nothing honest "
                              "to ask about yet"}
        if goal["status"] == "proposed":
            return {"success": True, "already_proposed": True, **goal}
        ask = self._ask(goal)
        self._set_status(goal["goal_id"], "proposed", ask=ask)
        self._last_proposal_interaction = self._interactions
        self._deliver(ask)
        return {"success": True, "epistemic_kind": "goal_proposal",
                "goal_id": goal["goal_id"], "title": goal["title"],
                "source": goal["source"], "ask": ask,
                "evidence": goal["evidence"], "score": goal["score"],
                "acted": False}  # a proposal is a question, never an action

    def decide(self, goal_id: int, accept: bool) -> Dict[str, Any]:
        """The owner answers. Accepted goals stay on the books — execution
        goes through the normal door, where her authority applies. Declined
        goals are never re-proposed."""
        goal = self._goal(goal_id)
        if goal is None:
            return {"success": False, "reason": f"no goal #{goal_id}"}
        status = "accepted" if accept else "declined"
        self._set_status(goal_id, status)
        note = ("owner approved — execution proceeds by asking through the "
                "normal door (goal approval ≠ action authorization)"
                if accept else "owner declined — will not be re-proposed")
        return {"success": True, "goal_id": goal_id, "status": status,
                "note": note, "acted": False}

    def refresh(self, task: str = "") -> Dict[str, Any]:
        """The door pass: gather, rank, and auto-propose only when the top
        candidate earned it and the cooldown elapsed."""
        self._interactions += 1
        self.gather()
        ranked = self.prioritize()
        proposed: Optional[Dict[str, Any]] = None
        if ranked:
            top = ranked[0]
            cooled = (self._interactions - self._last_proposal_interaction
                      >= AUTO_PROPOSE_COOLDOWN)
            if (top["status"] == "candidate"
                    and top["score"] >= AUTO_PROPOSE_SCORE and cooled):
                proposed = self.propose(top["goal_id"])
        return {"success": True, "candidates": len(ranked),
                "top": ranked[0]["title"] if ranked else None,
                "proposed": bool(proposed),
                "proposal": proposed if proposed else None}

    # ── surfaces ─────────────────────────────────────────────────────────
    def goals(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_goals ORDER BY goal_id DESC "
                    "LIMIT ?", (int(limit),)).fetchall()
            return [self._hydrate(r) for r in rows]
        except Exception:
            return []

    def stats(self) -> Dict[str, Any]:
        by_source: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for row in self.goals(limit=10000):
            by_source[row["source"]] = by_source.get(row["source"], 0) + 1
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        return {"goals": sum(by_status.values()), "by_source": by_source,
                "by_status": by_status,
                "policy": "goals from evidence only (never random); "
                          "relevance = named contributions; propose = ask, "
                          "never act; accepted goals execute through the "
                          "normal door under owner authority"}

    # ── internals ────────────────────────────────────────────────────────
    @staticmethod
    def _ask(goal: Dict[str, Any]) -> str:
        source, title = goal["source"], goal["title"]
        if source == "owner_goal":
            return (f"You said: '{title}'. It's still open — do you want me "
                    f"to handle that?")
        if source == "curiosity":
            return (f"'{title}' is still unresolved ({goal.get('recurrence', 1)}× "
                    f"encountered). Do you want me to look into it?")
        if source == "unfinished_goal":
            return (f"'{title}' is parked waiting for evidence. Do you want "
                    f"me to re-check it now?")
        if source == "environment":
            return f"I noticed: {title}. Do you want me to look into it?"
        if source == "learning":
            return (f"'{title}' didn't work last time (verified). Do you "
                    f"want me to retry it and learn?")
        return f"Your rhythms suggest '{title}' is coming up. Prepare it?"

    def _deliver(self, ask: str) -> None:
        working = getattr(self.mind.runtime, "working_memory", None)
        if working is None:
            return
        try:
            working.encode(ask, kind="retrieved_memory",
                           source="beanie_goal_proposal", salience=0.85,
                           goal_text=ask[:80])
        except Exception as exc:
            app_logger.warning(f"Proposal not delivered to working memory "
                               f"(non-fatal): {exc}")

    def _goal(self, goal_id: int) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM beanie_goals WHERE goal_id = ?",
                    (int(goal_id),)).fetchone()
            return self._hydrate(row) if row is not None else None
        except Exception:
            return None

    @staticmethod
    def _hydrate(row: Any) -> Dict[str, Any]:
        d = dict(row)
        d["reasons"] = [x for x in str(d.get("reasons") or "").split("|") if x]
        return d

    def _set_status(self, goal_id: int, status: str,
                    ask: Optional[str] = None) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                if ask is not None:
                    conn.execute("UPDATE beanie_goals SET status = ?, ask = ?,"
                                 " updated_at = ? WHERE goal_id = ?",
                                 (status, ask, _now_iso(), int(goal_id)))
                else:
                    conn.execute("UPDATE beanie_goals SET status = ?,"
                                 " updated_at = ? WHERE goal_id = ?",
                                 (status, _now_iso(), int(goal_id)))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Goal status not updated: {exc}")
