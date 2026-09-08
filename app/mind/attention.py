"""Attention — Phase 14 (Beanie AGI roadmap): M8 attention significance.

perception → ATTENTION → significance. Perception judges each sense event in
isolation; attention is the arbitrator that decides, across everything she
is currently sensing and doing, WHAT DESERVES THOUGHT. The roadmap ladder:

    ATTENTION
    ├── current task
    ├── owner speaking
    ├── important change
    ├── anomaly
    ├── unfinished goal
    ├── learned curiosity
    └── background observation

The roadmap's scenario: you're editing something, a popup appears — instead
of doing nothing because nobody explicitly called the screen tool, she
notices "something changed that may interfere with what you're doing."
That is exactly what this organ produces: an advisory with reasons.

Mechanics (deterministic, no LLM):
- ``notice(perception)`` classifies ONE perception record onto the ladder,
  with evidence-based reasons (urgency declared by the probe → important
  change; the learning loop judged it novel → anomaly; it touches an open
  unknown → unfinished goal; anything from the owner channel → owner
  speaking; else background). Repeats of already-attended content are
  demoted to background — "don't react to everything" applies to thought
  too, not just to storage.
- ``review(task)`` arbitrates every not-yet-attended perception (watermark
  over the perception ledger), then, only when nothing more pressing is
  pending, surfaces ONE open unknown as learned curiosity (with a cooldown
  so the same unknown is not re-surfaced review after review).
- If an anomaly/important change overlaps the current task's vocabulary,
  attention writes an advisory ("…may interfere with what you're doing")
  and offers it to working memory — the channel the cognitive cycle already
  reads. Best-effort; without working memory the advisory is still recorded.

Honesty rules:
- attention DECIDES WHAT DESERVES THOUGHT — it never acts (``acted: False``
  on every verdict);
- every verdict carries its ladder level AND its reasons — inspectable;
- background classification is an explicit verdict, not a silent drop;
- repeats are demoted with a reason, never hidden.
"""

from __future__ import annotations

import sqlite3
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

# the roadmap ladder: ladder level → rank (higher = more deserving of
# thought). current_task is the anchor she is doing; attention's job is to
# notice what else deserves thought alongside or above it.
LADDER = {
    "current_task": 7,
    "owner_speaking": 6,
    "important_change": 5,
    "anomaly": 4,
    "unfinished_goal": 3,
    "learned_curiosity": 2,
    "background_observation": 1,
}

_CURIOSITY_COOLDOWN_REVIEWS = 3  # don't re-surface the same unknown every review
_DEDUPE_CAP = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join(sorted(_terms(str(text))))


class Attention:
    """The arbitrator between perception and thought: what deserves thought,
    in what order, and with what advisory. Plans and judges only — never
    acts."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        self._task: str = ""
        self._recent: Dict[str, int] = {}       # content_norm → rank last attended
        self._curiosity_surfaced: deque = deque(maxlen=_CURIOSITY_COOLDOWN_REVIEWS)
        self._advisories: List[Dict[str, Any]] = []
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_attentions (
                    attention_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decided_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    modality TEXT,
                    content TEXT NOT NULL,
                    reasons TEXT,
                    advisory TEXT,
                    perception_id INTEGER
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Attention ledger unavailable: {exc}")

    # ── the anchor ───────────────────────────────────────────────────────
    def set_task(self, text: str) -> Dict[str, Any]:
        """The current task is what she is doing right now — the rung every
        change is measured against ('may interfere with what you're
        doing')."""
        self._task = str(text or "").strip()[:500]
        return {"success": True, "current_task": self._task}

    # ── classifying one perception onto the ladder ───────────────────────
    def notice(self, perception: Dict[str, Any],
               task: Optional[str] = None) -> Dict[str, Any]:
        """One perception record (as produced by Perception.perceive or read
        from the perception ledger) → one attention verdict."""
        content = str(perception.get("content") or "").strip()
        if not content:
            return {"success": False, "reason": "no content to attend to"}
        task = str(task if task is not None else self._task).strip()
        modality = str(perception.get("modality") or "").strip().lower()
        reasons = [str(r) for r in (perception.get("reasons") or [])]
        joined = " | ".join(reasons).lower()

        level, why = self._classify(modality, reasons, joined,
                                    perception.get("novelty"))
        # repeats of already-attended content are demoted — attending again
        # would be noise, not thought
        key = _norm(content)
        attended_rank = self._recent.get(key)
        if attended_rank is not None and attended_rank >= LADDER[level]:
            level = "background_observation"
            why = [f"repeat — already attended at rung {attended_rank}"]

        advisory = None
        if level in ("important_change", "anomaly") and task:
            overlap = set(_terms(content)) & set(_terms(task))
            if overlap:
                advisory = (f"{content} — this may interfere with what "
                            f"you're doing ({task})")
                why.append("overlaps the current task — advisory raised")

        rank = LADDER[level]
        verdict = {
            "success": True, "epistemic_kind": "attention_verdict",
            "level": level, "rank": rank, "modality": modality,
            "content": content[:300], "reasons": why, "advisory": advisory,
            "perception_id": perception.get("perception_id"),
            "acted": False,  # attention decides what deserves thought; it never acts
        }
        self._recent[key] = rank
        if len(self._recent) > _DEDUPE_CAP:
            for k in list(self._recent)[:len(self._recent) - _DEDUPE_CAP]:
                self._recent.pop(k, None)
        self._persist(verdict)
        if advisory:
            self._advisories.append({"at": _now_iso(), "advisory": advisory,
                                     "level": level})
            self._deliver_advisory(advisory, task)
        return verdict

    @staticmethod
    def _classify(modality: str, reasons: List[str], joined: str,
                  novelty: Optional[str]) -> Any:
        """Deterministic ladder placement from evidence on the record."""
        if modality == "owner":
            return "owner_speaking", ["the owner channel — owner speech outranks the environment"]
        if "urgent" in joined:
            return "important_change", ["the probe declared it urgent"]
        if novelty == "novel":
            return "anomaly", ["the learning loop judged it novel"]
        if "unknown" in joined:
            return "unfinished_goal", ["touches open unknown(s): " + joined]
        if novelty == "reinforces":
            return "background_observation", ["known and repeated — background"]
        return "background_observation", ["no evidence it deserves thought right now"]

    # ── arbitrating everything not yet attended ──────────────────────────
    def review(self, task: Optional[str] = None) -> Dict[str, Any]:
        """The door-level arbitration: attend to every perception newer than
        the watermark, then decide what currently deserves thought most."""
        if task is not None:
            self.set_task(task)
        verdicts: List[Dict[str, Any]] = []
        for perception in self._unattended():
            try:
                verdicts.append(self.notice(perception, task=self._task))
            except Exception as exc:
                app_logger.warning(f"Perception not attended (non-fatal): {exc}")

        curiosity_note: Optional[Dict[str, Any]] = None
        if not verdicts:
            curiosity_note = self._surface_curiosity()
            if curiosity_note is not None:
                verdicts.append(curiosity_note)

        current_focus: Optional[Dict[str, Any]] = None
        if verdicts:
            top = max(verdicts, key=lambda v: v["rank"])
            if top["rank"] >= LADDER["learned_curiosity"]:
                current_focus = top
        advisories = [v for v in verdicts if v.get("advisory")]
        return {
            "success": True,
            "current_task": self._task,
            "attended": len(verdicts),
            "by_level": self._count_levels(verdicts),
            "current_focus": current_focus,
            "advisories": [v["advisory"] for v in advisories],
            "verdicts": verdicts,
            "policy": "attend by evidence; demote repeats; surface one open "
                      "unknown only when nothing more pressing is pending",
        }

    def _unattended(self) -> List[Dict[str, Any]]:
        """Perceptions newer than the watermark (highest perception_id this
        organ has already attended), oldest first."""
        try:
            stream = self.mind.perception.stream(limit=200)
        except Exception:
            return []
        watermark = self._watermark()
        fresh = [p for p in stream
                 if p.get("perception_id") is not None
                 and int(p["perception_id"]) > watermark]
        return list(reversed(fresh))  # oldest first: attend in order received

    def _watermark(self) -> int:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                row = conn.execute(
                    "SELECT MAX(perception_id) FROM beanie_attentions").fetchone()
            return int(row[0] or 0)
        except Exception:
            return 0

    def _surface_curiosity(self) -> Optional[Dict[str, Any]]:
        """Nothing more pressing is pending → ONE open unknown deserves
        thought. Cooldown keeps her from repeating herself every review."""
        try:
            unknowns = self.mind.curiosity.curiosities(limit=10)
        except Exception:
            return None
        for row in unknowns:
            topic = str(row.get("topic") or "").strip()
            if not topic or topic in self._curiosity_surfaced:
                continue
            self._curiosity_surfaced.append(topic)
            verdict = {
                "success": True, "epistemic_kind": "attention_verdict",
                "level": "learned_curiosity",
                "rank": LADDER["learned_curiosity"],
                "modality": "curiosity", "content": topic[:300],
                "reasons": ["open unknown surfaced — nothing more pressing "
                            "is pending"],
                "advisory": None, "perception_id": None, "acted": False,
            }
            self._persist(verdict)
            return verdict
        return None

    # ── advisory delivery (fail-open) ────────────────────────────────────
    def _deliver_advisory(self, advisory: str, task: str) -> None:
        """Offer the advisory to working memory — the same channel the
        Phase-2 brief uses, which the cognitive cycle already reads. Without
        working memory the advisory stays recorded in the ledger."""
        working = getattr(self.mind.runtime, "working_memory", None)
        if working is None:
            return
        try:
            working.encode(advisory, kind="retrieved_memory",
                           source="beanie_attention_advisory",
                           salience=0.9, goal_text=task or "")
        except Exception as exc:
            app_logger.warning(f"Advisory not delivered to working memory "
                               f"(non-fatal): {exc}")

    # ── surfaces ─────────────────────────────────────────────────────────
    def focus_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_attentions ORDER BY attention_id "
                    "DESC LIMIT ?", (int(limit),)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["reasons"] = [x for x in str(d.get("reasons") or "").split("|") if x]
                out.append(d)
            return out
        except Exception:
            return []

    def advisories(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(self._advisories)[-int(limit):]

    def stats(self) -> Dict[str, Any]:
        by_level: Dict[str, int] = {}
        for row in self.focus_history(limit=10000):
            by_level[row["level"]] = by_level.get(row["level"], 0) + 1
        return {"verdicts": sum(by_level.values()), "by_level": by_level,
                "advisories_issued": len(self._advisories),
                "current_task": self._task,
                "ladder": dict(sorted(LADDER.items(), key=lambda kv: -kv[1])),
                "policy": "attention decides what deserves thought; it never "
                          "acts (acted: False on every verdict)"}

    def snapshot(self) -> Dict[str, Any]:
        """The state-room surface (app/mind/state.py probes this)."""
        history = self.focus_history(limit=1)
        last = history[0] if history else None
        return {"current_task": self._task,
                "last_focus": {"level": last.get("level"),
                               "content": last.get("content")} if last else None,
                "advisories_issued": len(self._advisories)}

    # ── internals ────────────────────────────────────────────────────────
    @staticmethod
    def _count_levels(verdicts: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for v in verdicts:
            counts[v["level"]] = counts.get(v["level"], 0) + 1
        return counts

    def _persist(self, verdict: Dict[str, Any]) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_attentions
                       (decided_at, level, rank, modality, content, reasons,
                        advisory, perception_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (_now_iso(), verdict["level"], verdict["rank"],
                     verdict.get("modality"), str(verdict["content"])[:500],
                     "|".join(verdict.get("reasons") or []),
                     verdict.get("advisory"), verdict.get("perception_id")))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Attention verdict not persisted: {exc}")
