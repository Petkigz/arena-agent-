"""Imagination — Phase 10 (Beanie AGI roadmap): reasoning and imagination.

The roadmap's epistemic distinctions, made real as labeled states::

    PERCEPTION  — "the screen contains this"
    BELIEF      — "I think this is happening"
    HYPOTHESIS  — "perhaps X caused it"          (Phase-6 contradictions)
    PREDICTION  — "if I do X, Y should happen"
    SIMULATION  — "if I take this path, the likely result is..."
    REALITY     — "I actually tried it and Y happened"

and the loop::

    PERCEIVE → MODEL → HYPOTHESIZE → SIMULATE → ACT → OBSERVE
    → COMPARE PREDICTION vs REALITY → LEARN

What this organ adds (deterministic, no LLM):
- ``simulate(action_type)`` — BEFORE acting: the existing PredictionEngine
  produces the prediction (expected changes + confidence, learned or
  default), then she consults her OWN verified history (episodic evidence)
  and her open unknowns (curiosity) and gives deterministic counsel.
- ``compare(action_type, success)`` — AFTER acting: reality (bool evidence
  ONLY) is compared with the prediction; the outcome is recorded in a
  persistent ledger and submitted to the Phase-6 loop as an ``experiment``
  experience — verdict confirmed/refuted — so **failures become training
  data**, exactly as the roadmap demands (M11: the prediction↔reality loop
  gets connected).

Division of labor, stated honestly:
- the runtime already predicts before acting, evaluates surprisal, and
  feeds the confidence calibrator; this organ does NOT re-feed the
  calibrator from cycle comparisons (no double counting) — it owns the
  ledger, the verdicts, and the training-data feed into the learning loop;
- the organ's own ``simulate``/owner-driven ``compare`` are the surfaces
  the owner (and, later, the planner) can use before any action happens.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

# the roadmap's epistemic ladder — each surface labels its output with one
EPISTEMIC_KINDS = (
    "perception",   # "the screen contains this"
    "belief",       # "I think this is happening"
    "hypothesis",   # "perhaps X caused it" (Phase-6 contradiction output)
    "prediction",   # "if I do X, Y should happen"
    "simulation",   # "if I take this path, the likely result is..."
    "reality",      # "I actually tried it and Y happened"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Imagination:
    """SIMULATE before acting; COMPARE prediction vs reality after; turn the
    difference into training data."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_simulations (
                    simulation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    epistemic_kind TEXT NOT NULL,
                    expected TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    confidence_source TEXT NOT NULL,
                    success INTEGER,
                    surprisal REAL,
                    verdict TEXT,
                    source TEXT NOT NULL
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Simulation ledger unavailable: {exc}")

    # ── SIMULATE: run the path in her head BEFORE acting ─────────────────
    def simulate(self, action_type: str,
                 payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        action_type = str(action_type or "").strip()
        if not action_type:
            return {"success": False, "reason": "simulate needs an action_type"}
        try:
            from app.cognition.prediction_engine import PredictionEngine
            pred = PredictionEngine().predict_action(action_type, payload or {})
        except Exception as exc:
            return {"success": False,
                    "reason": f"prediction engine unavailable: {exc}"}
        evidence = self._prior_evidence(action_type)
        unknowns = self._overlapping_unknowns(action_type)
        counsel, confidence = self._counsel(evidence, pred.confidence)
        return {
            "success": True,
            "epistemic_kind": "simulation",
            "action_type": action_type,
            "prediction": {
                "epistemic_kind": "prediction",
                "expected_changes": pred.expected_changes,
                "confidence": confidence,
                "confidence_source": pred.confidence_source,
            },
            "prior_evidence": evidence,
            "open_unknowns": unknowns[:3],
            "counsel": counsel,
        }

    def _prior_evidence(self, action_type: str) -> Dict[str, Any]:
        """Her own verified history with this kind of action: successes and
        failures from episodic memory (the learning loop stores them with
        success flags)."""
        memory = getattr(self.mind.memory, "memory", None)
        if memory is None:
            return {"successes": 0, "failures": 0, "note": "memory not wired"}
        try:
            records = memory.search(action_type, kinds={"episodic"}, limit=10)
        except Exception:
            return {"successes": 0, "failures": 0}
        terms = set(str(action_type).lower().replace("_", " ").split())
        successes = failures = 0
        for r in records:
            rec_terms = set(str(getattr(r, "content", "")).lower().split()) | \
                set(str(getattr(r, "source", "")).lower().split())
            if not (terms & rec_terms):
                continue  # evidence gate: real overlap only
            if getattr(r, "success", None) is True:
                successes += 1
            elif getattr(r, "success", None) is False:
                failures += 1
        return {"successes": successes, "failures": failures}

    def _overlapping_unknowns(self, action_type: str) -> List[str]:
        try:
            tops = self.mind.curiosity.curiosities(limit=20)
        except Exception:
            return []
        terms = {t for t in str(action_type).lower().replace("_", " ").split()
                 if len(t) >= 3}
        hits: List[str] = []
        for row in tops:
            topic_terms = set(str(row.get("topic", "")).lower().split())
            if terms & topic_terms:
                hits.append(str(row.get("topic")))
        return hits

    @staticmethod
    def _counsel(evidence: Dict[str, Any], predicted: float):
        s, f = evidence.get("successes", 0), evidence.get("failures", 0)
        if s == 0 and f == 0:
            return ("no verified experience with this yet — the prediction "
                    "rests on the default prior alone", predicted)
        if f > 0 and s == 0:
            return (f"this has failed {f} time(s) before and never "
                    "verifiably succeeded — proceed carefully",
                    min(predicted, 0.5))
        if f > 0:
            return (f"mixed history: {s} verified success(es), {f} "
                    "verified failure(s)", predicted)
        return (f"worked {s} time(s) before, no verified failures",
                predicted)

    # ── COMPARE: reality arrives, prediction is judged ───────────────────
    def compare(self, action_type: str, success: Any,
                surprisal: Optional[float] = None,
                source: str = "cycle") -> Dict[str, Any]:
        """Reality must be EVIDENCE: verified True or verified False.
        Anything else is rejected — an unobserved outcome is not a
        prediction error."""
        action_type = str(action_type or "").strip()
        if not action_type:
            return {"success": False, "reason": "compare needs an action_type"}
        if not isinstance(success, bool):
            return {"success": False,
                    "reason": "reality must be bool evidence "
                              "(verified True/False), never a guess"}
        try:
            from app.cognition.prediction_engine import PredictionEngine
            pred = PredictionEngine().predict_action(action_type, {})
        except Exception as exc:
            return {"success": False,
                    "reason": f"prediction engine unavailable: {exc}"}
        verdict = "confirmed" if success else "refuted"
        self._record(action_type, "reality", str(pred.expected_changes),
                     pred.confidence, pred.confidence_source, success,
                     surprisal, verdict, source)
        # the verified outcome becomes a durable episode FIRST (same pattern
        # as Phase-7 teaching): the learning loop then rehearses it instead
        # of misreading an unrelated action's different outcome as a
        # contradiction of this one
        outcome_text = f"{action_type} {'succeeded' if success else 'failed'}"
        stored_memory_id = None
        try:
            out = self.mind.memory.remember(
                "episodic", outcome_text,
                importance=0.6 if success else 0.55,
                source=f"reality:{source}",
                tags=["prediction_vs_reality"] + action_type.split("_")[:4],
                outcome=verdict, success=success)
            if out.get("success"):
                stored_memory_id = out.get("memory_id")
        except Exception as exc:
            app_logger.warning(f"Reality episode not stored: {exc}")
        # ...and the comparison enters the one learning loop as an
        # experiment with a declared prediction (ledger + verdict).
        # predicted_confidence is deliberately withheld: the runtime already
        # feeds the calibrator for cycle outcomes (no double counting).
        learned = False
        try:
            # content stays action-specific on purpose: boilerplate shared
            # by every experiment would make unrelated actions look related
            # to the learning loop's overlap gate (the prediction rides its
            # own field)
            rec = self.mind.learn({
                "kind": "experiment",
                "content": outcome_text,
                "prediction": str(pred.expected_changes)[:160],
                "success": success,
                "source": f"reality:{source}"[:120],
                "outcome": verdict,
                "goal_type": "prediction_vs_reality",
            })
            learned = bool(rec.get("success"))
        except Exception as exc:
            app_logger.warning(f"Reality not fed to learning loop: {exc}")
        return {"success": True, "epistemic_kind": "reality",
                "action_type": action_type, "verdict": verdict,
                "predicted": pred.expected_changes,
                "confidence": pred.confidence,
                "surprisal": surprisal, "learned": learned,
                "stored_memory_id": stored_memory_id}

    # ── surfaces ─────────────────────────────────────────────────────────
    def records(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_simulations ORDER BY "
                    "simulation_id DESC LIMIT ?", (int(limit),)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["success"] = None if d["success"] is None else bool(d["success"])
                out.append(d)
            return out
        except Exception:
            return []

    def stats(self) -> Dict[str, Any]:
        confirmed = refuted = total = 0
        surprisal_sum = 0.0
        surprisal_n = 0
        for row in self.records(limit=10000):
            total += 1
            if row.get("verdict") == "confirmed":
                confirmed += 1
            elif row.get("verdict") == "refuted":
                refuted += 1
            if isinstance(row.get("surprisal"), (int, float)):
                surprisal_sum += float(row["surprisal"])
                surprisal_n += 1
        return {
            "comparisons": total, "confirmed": confirmed, "refuted": refuted,
            "mean_surprisal": round(surprisal_sum / surprisal_n, 3)
            if surprisal_n else None,
            "epistemic_kinds": list(EPISTEMIC_KINDS),
            "loop": "perceive → model → hypothesize → simulate → act → "
                    "observe → compare prediction vs reality → learn",
        }

    # ── internals ────────────────────────────────────────────────────────
    def _record(self, action_type: str, kind: str, expected: str,
                confidence: float, confidence_source: str, success: bool,
                surprisal: Optional[float], verdict: str,
                source: str) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_simulations
                       (recorded_at, action_type, epistemic_kind, expected,
                        confidence, confidence_source, success, surprisal,
                        verdict, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (_now_iso(), action_type[:120], kind, expected[:300],
                     float(confidence), confidence_source[:60],
                     int(success), surprisal, verdict, source[:120]))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Simulation not persisted: {exc}")
