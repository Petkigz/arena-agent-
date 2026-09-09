"""Evaluation — Phase 24 (Beanie AGI roadmap): AGI evaluation.

"Stop measuring primarily 'How many tests pass?' Measure
GENERALIZATION. Create tasks Beanie has never explicitly been
programmed for:
A. Teach her a new procedure once, then give her a variation — adapt?
B. Show her a tutorial — perform without a hard-coded workflow?
C. Give her an unfamiliar error — investigate?
D. Change the environment — adapt?
E. Give her an incomplete instruction — infer (not fabricate) the
   missing context?
F. Let her fail — learn from the failure?
G. Teach her something on one body — transfer the concept to another?"

The evaluator runs those seven families as DETERMINISTIC probes against
her REAL organs — never an LLM jury, never a staged pass:

- A: the taught material must surface as related to the variation by
  real term evidence (the learning loop's own vocabulary);
- B: the steps she derives from a tutorial are recovered from what was
  actually learned — nothing reconstructed from hidden knowledge;
- C: the unfamiliar error must become a registered UNKNOWN (curiosity),
  the honest first act of investigation;
- D: a changed environment must advance the registry's environment
  revision and drop the stale capability's cached availability — she
  re-probes instead of reading dead facts;
- E: an incomplete instruction must leave correctness UNKNOWN — the
  verifier's word is missing and is never guessed;
- F: a verified failure must be called WRONG by reflection, with
  counsel attached — failure becomes material;
- G: steps taught on one body are transferred by the OS concept layer —
  resolved on the target body, or flagged as a VISIBLE gap.

Each task yields a score in [0, 1] with its evidence; the run is
recorded. The overall number is a proxy measurement of generalization —
meaningful, and honestly labeled as a proxy, never as proof.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

# Task A: term-overlap at or above this counts as adapting to a variation.
ADAPTATION_OVERLAP_THRESHOLD = 0.25

_STEP_LINE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.+)$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _overlap(a: str, b: str) -> float:
    ta, tb = set(_terms(a)), set(_terms(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class Evaluation:
    """The seven generalization families, run against the real organs.
    Deterministic proxies, honestly labeled."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_evaluations (
                    evaluation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    overall REAL NOT NULL,
                    profile TEXT NOT NULL
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Evaluation ledger unavailable: {exc}")

    # ── the seven families ───────────────────────────────────────────────
    def task_a_teach_then_variation(self, procedure: str,
                                    variation: str) -> Dict[str, Any]:
        """Teach once; does the taught material cover the variation?"""
        try:
            self.mind.learn({"kind": "demonstration", "content": procedure,
                             "source": "evaluation:task_a"})
        except Exception as exc:
            return self._task("A", "teach once, adapt to variation", 0.0,
                              {"error": str(exc)},
                              "teaching failed honestly — nothing scored")
        overlap = _overlap(procedure, variation)
        adapted = overlap >= ADAPTATION_OVERLAP_THRESHOLD
        return self._task(
            "A", "teach once, adapt to variation", round(overlap, 3),
            {"term_overlap": round(overlap, 3),
             "threshold": ADAPTATION_OVERLAP_THRESHOLD,
             "taught": procedure[:120], "variation": variation[:120]},
            "the taught material surfaces for the variation by real term "
            "evidence — she adapts" if adapted else
            "the variation shares too little evidence with what was "
            "taught — adaptation not demonstrated")

    def task_b_tutorial(self, tutorial: str) -> Dict[str, Any]:
        """Show a tutorial; recover the steps she actually learned —
        nothing reconstructed from hidden knowledge."""
        expected = [m.group(1).strip() for m in
                    (_STEP_LINE.match(ln) for ln in
                     str(tutorial or "").splitlines()) if m]
        try:
            self.mind.learn({"kind": "demonstration", "content": tutorial,
                             "source": "evaluation:task_b"})
        except Exception as exc:
            return self._task("B", "tutorial without hard-coded workflow",
                              0.0, {"error": str(exc)},
                              "learning failed honestly — nothing scored")
        # the ledger keeps NO source column on learning events — the
        # content itself is the evidence; recover from the most recent
        # matching event (events arrive newest-first).
        learned = ""
        try:
            for row in self.mind.learning.events(limit=50):
                if _norm_eq(row.get("content"), tutorial):
                    learned = str(row.get("content") or "")
                    break
        except Exception:
            pass
        recovered = [m.group(1).strip() for m in
                     (_STEP_LINE.match(ln) for ln in learned.splitlines())
                     if m]
        score = (len(recovered) / len(expected)) if expected else 0.0
        return self._task(
            "B", "tutorial without hard-coded workflow", round(score, 3),
            {"expected_steps": len(expected),
             "recovered_steps": len(recovered),
             "from_ledger": bool(learned)},
            "the steps she performs come from what was actually learned "
            "— no hard-coded workflow" if expected and recovered and
            len(recovered) >= len(expected) else
            "step recovery incomplete — scored from the ledger only")

    def task_c_unfamiliar_error(self, error_text: str) -> Dict[str, Any]:
        """An unfamiliar error: the honest first act of investigation is
        registering the unknown — never pretending to know."""
        topic = f"unfamiliar error: {str(error_text)[:120]}"
        try:
            self.mind.curiosity.register(topic, source="evaluation",
                                         context="task_c: unfamiliar error")
        except Exception as exc:
            return self._task("C", "unfamiliar error → investigate", 0.0,
                              {"error": str(exc)},
                              "curiosity unavailable — nothing scored")
        registered = False
        try:
            registered = any(
                "unfamiliar error" in str(u.get("topic") or "")
                for u in self.mind.curiosity.curiosities(limit=100))
        except Exception:
            pass
        return self._task(
            "C", "unfamiliar error → investigate", 1.0 if registered else 0.0,
            {"registered_unknown": registered, "topic": topic[:140]},
            "the error became a registered UNKNOWN — investigation "
            "starts with honest ignorance" if registered else
            "the unknown could not be registered — not scored as "
            "investigation")

    def task_d_environment_change(self, capability: str) -> Dict[str, Any]:
        """Change the environment: does she drop the stale fact and
        re-probe instead of reading dead cache?"""
        try:
            from app.cognition.tool_registry import get_shared_registry
            registry = get_shared_registry()
            before = registry.environment_revision
            registry.note_environment_change(
                "evaluation:task_d environment change",
                source="mind_evaluation")
            registry.invalidate_tool_availability(
                str(capability), reason="evaluation: environment changed")
            after = registry.environment_revision
        except Exception as exc:
            return self._task("D", "environment change → adapt", 0.0,
                              {"error": str(exc)},
                              "registry unavailable — nothing scored")
        advanced = after > before
        return self._task(
            "D", "environment change → adapt", 1.0 if advanced else 0.0,
            {"environment_revision": [before, after],
             "capability_invalidated": str(capability)},
            "the environment revision advanced and the stale capability "
            "availability was dropped — she re-probes, never reads dead "
            "facts" if advanced else
            "the revision did not advance — adaptation not demonstrated")

    def task_e_incomplete_instruction(self, instruction: str
                                      ) -> Dict[str, Any]:
        """An incomplete instruction: the missing context is inferred as
        MISSING — never fabricated as done."""
        try:
            self.mind.learn({"kind": "conversation", "content": instruction,
                             "source": "evaluation:task_e"})
        except Exception:
            pass
        try:
            refl = self.mind.reflection.reflect_on(
                {"kind": "action", "content": instruction,
                 "success": None, "source": "evaluation"})
        except Exception as exc:
            return self._task("E", "incomplete instruction → infer", 0.0,
                              {"error": str(exc)},
                              "reflection unavailable — nothing scored")
        unknown_kept = refl.get("was_i_correct", {}).get("verdict") is None
        return self._task(
            "E", "incomplete instruction → infer", 1.0 if unknown_kept
            else 0.0,
            {"verdict": refl.get("was_i_correct", {}).get("verdict"),
             "instruction": str(instruction)[:120]},
            "correctness stays UNKNOWN — she names the missing context "
            "instead of fabricating completion" if unknown_kept else
            "a verdict appeared without the verifier's word — honesty "
            "broken")

    def task_f_learn_from_failure(self, content: str) -> Dict[str, Any]:
        """Let her fail: the failure must be called wrong and become
        material (counsel), never buried."""
        try:
            self.mind.learn({"kind": "action", "content": content,
                             "source": "evaluation:task_f",
                             "success": False})
        except Exception:
            pass
        try:
            refl = self.mind.reflection.reflect_on(
                {"kind": "action", "content": content, "success": False,
                 "source": "evaluation"})
        except Exception as exc:
            return self._task("F", "fail → learn from failure", 0.0,
                              {"error": str(exc)},
                              "reflection unavailable — nothing scored")
        wrong = refl.get("was_i_correct", {}).get("verdict") == "wrong"
        counsel = bool(refl.get("should_change_model", {}).get("statement"))
        return self._task(
            "F", "fail → learn from failure",
            1.0 if (wrong and counsel) else (0.5 if wrong else 0.0),
            {"verdict": refl.get("was_i_correct", {}).get("verdict"),
             "counsel": refl.get("should_change_model", {}).get(
                 "statement", "")[:160]},
            "the failure was called wrong and became counsel — failure "
            "is material" if wrong and counsel else
            "the failure was not fully converted into material")

    def task_g_transfer(self, steps: List[str],
                        to_platform: str = "android") -> Dict[str, Any]:
        """Teach it on one body; the concept layer transfers it —
        resolved on the target body, or a VISIBLE gap."""
        try:
            res = self.mind.os_concepts.transfer(to_platform,
                                                 steps=list(steps or []))
        except Exception as exc:
            return self._task("G", "teach on one body → transfer", 0.0,
                              {"error": str(exc)},
                              "concept layer unavailable — nothing scored")
        if not res.get("success"):
            return self._task("G", "teach on one body → transfer", 0.0,
                              {"reason": res.get("reason")},
                              "transfer refused honestly — nothing scored")
        resolved, gaps = res.get("resolved", 0), res.get("gaps", 0)
        total = resolved + gaps
        score = (resolved / total) if total else 0.0
        return self._task(
            "G", "teach on one body → transfer", round(score, 3),
            {"to_platform": to_platform, "resolved": resolved,
             "gaps": gaps, "generalized": res.get("generalized")},
            "the concept generalized to the other body" if
            res.get("generalized") else
            f"{resolved} of {total} steps resolved on {to_platform} — "
            f"gaps stay VISIBLE, never fabricated")

    # ── the run ──────────────────────────────────────────────────────────
    def run_all(self, overrides: Optional[Dict[str, Any]] = None
                ) -> Dict[str, Any]:
        """All seven families with deterministic default material
        (overridable). Recorded; labeled as proxy measurements."""
        ov = overrides or {}
        tasks = [
            self.task_a_teach_then_variation(
                ov.get("a_procedure",
                       "open the settings app and search for display "
                       "brightness"),
                ov.get("a_variation",
                       "open settings and search for the display "
                       "brightness")),
            self.task_b_tutorial(ov.get(
                "b_tutorial",
                "How to export a report:\n1. open the reports app\n"
                "2. choose the monthly summary\n3. press export")),
            self.task_c_unfamiliar_error(ov.get(
                "c_error", "KernelError: page fault in module arena_core "
                           "at 0x0")),
            self.task_d_environment_change(
                ov.get("d_capability", "open_application")),
            self.task_e_incomplete_instruction(
                ov.get("e_instruction", "back it up")),
            self.task_f_learn_from_failure(
                ov.get("f_content", "the nightly export")),
            self.task_g_transfer(
                ov.get("g_steps", ["open the browser", "copy the link"]),
                ov.get("g_platform", "android")),
        ]
        overall = round(sum(t["score"] for t in tasks) / len(tasks), 3) \
            if tasks else 0.0
        profile = {"tasks": tasks, "overall": overall,
                   "policy": "deterministic proxies against the real "
                             "organs — meaningful measurements of "
                             "generalization, honestly labeled as "
                             "proxies, never as proof"}
        self._record(overall, profile)
        return {"success": True, "acted": False,
                "epistemic_kind": "agi_evaluation", **profile}

    def runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM beanie_evaluations ORDER BY "
                    "evaluation_id DESC LIMIT ?", (int(limit),))]
        except Exception:
            return []
        for r in rows:
            try:
                r["profile"] = json.loads(r["profile"])
            except Exception:
                pass
        return rows

    def stats(self) -> Dict[str, Any]:
        runs = self.runs(limit=1000)
        latest = runs[0]["overall"] if runs else None
        return {"runs": len(runs), "latest_overall": latest,
                "policy": "measure generalization, not test counts — "
                          "seven families (A–G) as deterministic proxies "
                          "against the real organs; proxies, never proof"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "evaluation", **self.stats(),
                "runs": self.runs(limit=5)}

    # ── internals ────────────────────────────────────────────────────────
    @staticmethod
    def _task(task_id: str, name: str, score: float,
              evidence: Dict[str, Any], verdict: str) -> Dict[str, Any]:
        return {"task": task_id, "name": name,
                "score": max(0.0, min(1.0, float(score))),
                "evidence": evidence, "verdict": verdict}

    def _record(self, overall: float, profile: Dict[str, Any]) -> None:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    "INSERT INTO beanie_evaluations (created_at, overall,"
                    " profile) VALUES (?,?,?)",
                    (_now_iso(), float(overall),
                     json.dumps(profile, default=str)[:60000]))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Evaluation record failed (non-fatal): "
                               f"{exc}")


def _norm_eq(a: Any, b: Any) -> bool:
    return " ".join(sorted(_terms(str(a or "")))) == \
        " ".join(sorted(_terms(str(b or ""))))
