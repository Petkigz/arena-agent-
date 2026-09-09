"""Improvement — Phase 20 (Beanie AGI roadmap): self-improvement.

"Detect capability gaps → investigate → design improvement → implement →
test → measure → retain/revert. The existing self-evolving/code-generation
infrastructure can become part of this — one mechanism of self-improvement,
not the definition of intelligence."

Mechanics (deterministic detection; the ONLY code-generation is the wired,
already-verified ``SelfEvolvingAgent`` engine, called as one mechanism):

- detect_gaps(): gaps come ONLY from real evidence — the SAME thing
  failing verified 2+ times in the learning ledger. A single failure is
  data, not a gap (Phase-19 counsel). Reflection-registered unknowns
  corroborate a gap when present.
- investigate(content): the evidence bundle for a gap — the failing
  events, the reflections about it, the registered unknown. Nothing
  concluded beyond what the rows say.
- design(gap): a proposal — mechanism ``capability_synthesis`` (the
  self-evolving engine), the hypothesis, the baseline failure count, and
  the measurement criterion (future verified attempts of the same kind,
  tracked in the learning ledger).
- implement(id): runs the mechanism. The engine's own contract decides —
  sandbox test BEFORE install, hotload only if green. Success is claimed
  ONLY from its typed result; an offline model or a rejected attempt is
  recorded as the honest failure it is.
- measure(id): after NEW verified experience arrives, compare it to the
  baseline — success with no new failures = improved (retain); 2+ new
  failures = regressed (revert: unregister the capability, remove the
  files, record it); anything less = awaiting evidence, never guessed.
- retain/revert: the ledger's final word. Reverting undoes the install
  for real (registry entry popped, environment revision bumped, files
  removed best-effort) and says so.

The door detects and PROPOSES after a verified failure completes a
pattern; it NEVER implements on its own — implementation is an explicit
surface act (the owner's authority governs execution).

Honesty rules:
- no gap without 2+ verified failures of the same thing;
- no success claim without the engine's typed verified+installed word;
- no measurement without new verified evidence — awaiting, never
  guessed;
- the proposal describes; only implement() acts.
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

_GAP_FAIL_THRESHOLD = 2      # verified failures of one thing = a gap
_REVERT_FAIL_THRESHOLD = 2   # new verified failures after an attempt = revert


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join(sorted(_terms(str(text))))


def _safe_capability_name(content: str) -> str:
    """A registry-safe name derived from the gap's content (deterministic;
    never empty)."""
    words = [w for w in _terms(content)][:3] or ["capability"]
    return "imp_" + "_".join(words)[:48]


class Improvement:
    """Detect gaps from evidence, propose fixes, run the wired synthesis
    mechanism, measure from later evidence, retain or revert for real."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_improvements (
                    improvement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    content TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    mechanism TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    baseline_fails INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    attempted_at TEXT,
                    attempt TEXT,
                    measured_at TEXT,
                    measurement TEXT,
                    acted INTEGER NOT NULL DEFAULT 0,
                    note TEXT
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Improvement ledger unavailable: {exc}")

    # ── DETECT: gaps are evidence, never narration ──────────────────────
    def detect_gaps(self) -> List[Dict[str, Any]]:
        """The SAME thing failing verified 2+ times. Nothing else is a
        gap."""
        counts: Dict[str, Dict[str, Any]] = {}
        try:
            for row in self.mind.learning.events(limit=1000):
                if not self._is_failure(row):
                    continue
                norm = _norm(str(row.get("content") or ""))
                if not norm:
                    continue
                slot = counts.setdefault(
                    norm, {"fails": 0, "content": str(row.get("content")),
                           "last": None})
                slot["fails"] += 1
                slot["last"] = row.get("recorded_at") or slot["last"]
        except Exception as exc:
            app_logger.warning(f"Gap detection could not read the learning "
                               f"ledger (non-fatal): {exc}")
            return []
        unknowns = []
        try:
            unknowns = self.mind.curiosity.curiosities(limit=100)
        except Exception:
            unknowns = []
        gaps: List[Dict[str, Any]] = []
        for norm, slot in sorted(counts.items(),
                                 key=lambda kv: -kv[1]["fails"]):
            if slot["fails"] < _GAP_FAIL_THRESHOLD:
                continue  # a single failure is data, not a pattern
            corroborating = None
            for u in unknowns:
                topic = str(u.get("topic") or "")
                if "keep failing" in topic and (
                        slot["content"][:40] in topic
                        or _norm(topic.split(":", 1)[-1]) == norm):
                    corroborating = {"topic": topic,
                                     "context": u.get("context"),
                                     "times_encountered":
                                         u.get("times_encountered")}
                    break
            gaps.append({"content": slot["content"], "norm": norm,
                         "verified_failures": slot["fails"],
                         "last_failure": slot["last"],
                         "unknown": corroborating,
                         "source": "verified_failures"})
        return gaps

    # ── INVESTIGATE: the evidence bundle for one gap ────────────────────
    def investigate(self, content: str) -> Dict[str, Any]:
        content = str(content or "").strip()
        if not content:
            return {"success": False, "reason": "no content to investigate"}
        key = _norm(content)
        failures, successes = [], []
        try:
            for row in self.mind.learning.events(limit=1000):
                if _norm(str(row.get("content") or "")) != key:
                    continue
                entry = {"content": row.get("content"),
                         "recorded_at": row.get("recorded_at"),
                         "verdict": row.get("verdict")}
                if self._is_failure(row):
                    failures.append(entry)
                elif row.get("success") is True:
                    successes.append(entry)
        except Exception:
            pass
        reflections = []
        try:
            reflections = [r for r in self.mind.reflection.reflections(limit=200)
                           if _norm(str(r.get("content") or "")) == key][:5]
        except Exception:
            pass
        unknown = None
        try:
            for u in self.mind.curiosity.curiosities(limit=100):
                topic = str(u.get("topic") or "")
                if "keep failing" in topic and content[:40] in topic:
                    unknown = u
                    break
        except Exception:
            pass
        if not failures and not reflections and unknown is None:
            return {"success": False,
                    "reason": "no evidence on record about this — nothing "
                              "to investigate (UNKNOWN preserved)"}
        return {"success": True, "content": content,
                "verified_failures": failures[:10],
                "failure_count": len(failures),
                "success_count": len(successes),
                "reflections": [{"was_i_correct": r.get("was_i_correct"),
                                 "should_change_model":
                                     r.get("should_change_model")}
                                for r in reflections],
                "unknown": unknown,
                "finding": (f"{len(failures)} verified failure(s), "
                            f"{len(successes)} verified success(es) on "
                            f"record" if failures or successes else
                            "reflections/unknown only — no verified "
                            "attempts on record")}

    # ── DESIGN: a proposal from the evidence ────────────────────────────
    def design(self, gap: Dict[str, Any]) -> Dict[str, Any]:
        """Turn an evidenced gap into a recorded proposal. Designs never
        execute."""
        content = str(gap.get("content") or "").strip()
        if not content:
            return {"success": False, "reason": "no gap content"}
        fails = int(gap.get("verified_failures") or 0)
        if fails < _GAP_FAIL_THRESHOLD:
            return {"success": False,
                    "reason": "not a pattern yet — a gap needs 2+ verified "
                              "failures of the same thing (this is data, "
                              "not a gap)"}
        norm = _norm(content)
        existing = self._row_for_norm(norm)
        if existing is not None and existing["status"] in (
                "proposed", "attempted", "awaiting_evidence", "retained"):
            return {"success": False,
                    "reason": (f"this gap already has an improvement "
                               f"(#{existing['improvement_id']}, status "
                               f"{existing['status']})"),
                    "improvement_id": existing["improvement_id"]}
        capability = _safe_capability_name(content)
        hypothesis = (
            f"a dedicated capability for '{content[:120]}' — synthesized "
            f"and sandbox-verified before install — should end the "
            f"verified-failure pattern ({fails}× so far)")
        measurement = (
            "future verified attempts of this same kind, tracked in the "
            "learning ledger: success with no new failures = improved; "
            "2+ new failures = reverted; nothing else is ever guessed")
        row_id = self._insert(content, norm, "capability_synthesis",
                              hypothesis, fails, "proposed",
                              note=f"capability_name={capability}; "
                                   f"{measurement}")
        return {"success": True, "acted": False,
                "epistemic_kind": "improvement_proposal",
                "improvement_id": row_id, "content": content,
                "mechanism": "capability_synthesis",
                "capability_name": capability,
                "hypothesis": hypothesis, "baseline_fails": fails,
                "measurement_criterion": measurement, "status": "proposed",
                "statement": (f"gap detected from {fails} verified "
                              f"failures — proposal recorded; nothing "
                              f"executes until the owner surface says so")}

    # ── IMPLEMENT → TEST: the wired mechanism decides ───────────────────
    def implement(self, improvement_id: int) -> Dict[str, Any]:
        """Run the mechanism. The self-evolving engine's OWN contract
        decides (sandbox test before install, hotload only if green);
        this organ only reports its typed word — never a claim of its
        own."""
        row = self._row(int(improvement_id))
        if row is None:
            return {"success": False,
                    "reason": f"no improvement #{improvement_id}"}
        if row["status"] not in ("proposed", "failed"):
            return {"success": False,
                    "reason": (f"improvement #{improvement_id} is "
                               f"'{row['status']}' — only proposed/failed "
                               f"proposals can be attempted")}
        capability = self._capability_name(row)
        task = f"learn to reliably: {row['content'][:200]}"
        attempt: Dict[str, Any]
        try:
            from app.agents.self_evolving_agent import SelfEvolvingAgent
            attempt = SelfEvolvingAgent.synthesize_and_hotload_tool(
                task_objective=task, tool_name_query=capability)
        except Exception as exc:
            attempt = {"success": False, "verified": False,
                       "installed": False,
                       "error": f"synthesis mechanism failed: {exc}"}
        if not isinstance(attempt, dict):
            attempt = {"success": False, "verified": False,
                       "installed": False,
                       "error": "synthesis mechanism returned no typed "
                                "result"}
        verified = bool(attempt.get("verified"))
        installed = bool(attempt.get("installed"))
        status = "attempted" if installed else "failed"
        self._update(int(improvement_id), status=status,
                     attempted_at=_now_iso(),
                     attempt=json.dumps(attempt, default=str)[:8000],
                     acted=1 if installed else 0)
        if installed:
            statement = (f"the mechanism verified AND installed "
                         f"'{capability}' — sandbox-tested before install "
                         f"(attempts: {attempt.get('attempts')}); "
                         f"measurement awaits new verified experience")
        elif verified:
            statement = ("the mechanism verified the code but could not "
                         "install it — nothing is claimed")
        else:
            reason = str(attempt.get("last_failure")
                         or attempt.get("error")
                         or "verification did not pass")
            statement = (f"the mechanism did NOT verify — nothing "
                         f"installed anywhere (reason: {reason[:240]})")
        return {"success": True, "acted": installed,
                "epistemic_kind": "improvement_attempt",
                "improvement_id": int(improvement_id),
                "status": status, "verified": verified,
                "installed": installed, "capability_name": capability,
                "attempts": attempt.get("attempts"),
                "statement": statement}

    # ── MEASURE: later evidence against the baseline ────────────────────
    def measure(self, improvement_id: int) -> Dict[str, Any]:
        """Compare NEW verified experience (after the attempt) to the
        baseline. No new evidence = awaiting, never guessed."""
        row = self._row(int(improvement_id))
        if row is None:
            return {"success": False,
                    "reason": f"no improvement #{improvement_id}"}
        if row["status"] in ("proposed",):
            return {"success": False,
                    "reason": "nothing was attempted yet — nothing to "
                              "measure"}
        if row["status"] in ("retained", "reverted"):
            return {"success": True, "status": row["status"],
                    "statement": (f"already concluded: "
                                   f"{row['status']} (see measurement on "
                                   f"record)"),
                    "measurement": self._load_json(row["measurement"])}
        since = row["attempted_at"] or row["created_at"]
        key = row["norm"]
        new_successes, new_failures = 0, 0
        try:
            for ev in self.mind.learning.events(limit=1000):
                if _norm(str(ev.get("content") or "")) != key:
                    continue
                if str(ev.get("recorded_at") or "") <= str(since):
                    continue
                if self._is_failure(ev):
                    new_failures += 1
                elif ev.get("success") is True:
                    new_successes += 1
        except Exception as exc:
            return {"success": False,
                    "reason": f"measurement could not read the learning "
                              f"ledger: {exc}"}
        measurement = {"since": since, "new_successes": new_successes,
                       "new_failures": new_failures,
                       "baseline_fails": row["baseline_fails"]}
        if new_failures >= _REVERT_FAIL_THRESHOLD:
            revert_report = self._revert_installed(row)
            measurement["verdict"] = "regressed"
            measurement["revert"] = revert_report
            self._update(int(improvement_id), status="reverted",
                         measured_at=_now_iso(),
                         measurement=json.dumps(measurement)[:4000],
                         note="the pattern continued after the attempt — "
                              "reverted for real")
            return {"success": True, "acted": bool(revert_report.get("acted")),
                    "epistemic_kind": "improvement_measurement",
                    "improvement_id": int(improvement_id),
                    "status": "reverted", "measurement": measurement,
                    "statement": (f"{new_failures} new verified failures "
                                  f"after the attempt — reverted "
                                  f"(registry/files: "
                                  f"{revert_report['statement']})")}
        if new_successes >= 1 and new_failures == 0:
            measurement["verdict"] = "improved"
            self._update(int(improvement_id), status="retained",
                         measured_at=_now_iso(),
                         measurement=json.dumps(measurement)[:4000],
                         note="verified success with no new failures — "
                              "the improvement is kept")
            return {"success": True, "acted": False,
                    "epistemic_kind": "improvement_measurement",
                    "improvement_id": int(improvement_id),
                    "status": "retained", "measurement": measurement,
                    "statement": (f"{new_successes} verified success(es), "
                                  f"no new failures — retained")}
        measurement["verdict"] = "awaiting_evidence"
        self._update(int(improvement_id), status="awaiting_evidence",
                     measured_at=_now_iso(),
                     measurement=json.dumps(measurement)[:4000])
        return {"success": True, "acted": False,
                "epistemic_kind": "improvement_measurement",
                "improvement_id": int(improvement_id),
                "status": "awaiting_evidence", "measurement": measurement,
                "statement": "no decisive new verified evidence yet — "
                             "measurement awaits, never guessed"}

    # ── the door: detect + propose after a verified failure ─────────────
    def note_failure(self, content: str) -> Optional[Dict[str, Any]]:
        """Called by the door after a DEFINITELY-failed cycle. When the
        failure completes a pattern (2+ verified), design the proposal —
        the door NEVER implements."""
        content = str(content or "").strip()
        if not content:
            return None
        try:
            counts: Dict[str, int] = {}
            for row in self.mind.learning.events(limit=1000):
                if self._is_failure(row):
                    norm = _norm(str(row.get("content") or ""))
                    counts[norm] = counts.get(norm, 0) + 1
            norm = _norm(content)
            if counts.get(norm, 0) < _GAP_FAIL_THRESHOLD:
                return None
            if self._row_for_norm(norm) is not None:
                return None
            return self.design({"content": content,
                                "verified_failures": counts[norm]})
        except Exception as exc:
            app_logger.warning(f"Improvement note_failure skipped "
                               f"(non-fatal): {exc}")
            return None

    # ── surfaces ────────────────────────────────────────────────────────
    def improvements(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT * FROM beanie_improvements ORDER BY "
                    "improvement_id DESC LIMIT ?", (int(limit),))
                rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            return []
        for r in rows:
            r["attempt"] = self._load_json(r.get("attempt"))
            r["measurement"] = self._load_json(r.get("measurement"))
            r["acted"] = bool(r.get("acted"))
        return rows

    def stats(self) -> Dict[str, Any]:
        rows = self.improvements(limit=10000)
        by_status: Dict[str, int] = {}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        return {"improvements": len(rows), "by_status": by_status,
                "gaps_detected": len(self.detect_gaps()),
                "policy": "gaps from 2+ verified failures only; the "
                          "mechanism's typed word decides; measurement "
                          "awaits new evidence, never guesses; revert "
                          "undoes for real"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "improvement", **self.stats(),
                "gaps": self.detect_gaps(),
                "improvements": self.improvements(limit=20)}

    # ── internals ────────────────────────────────────────────────────────
    @staticmethod
    def _is_failure(row: Dict[str, Any]) -> bool:
        return row.get("success") is False or row.get("success") == 0

    @staticmethod
    def _capability_name(row: Dict[str, Any]) -> str:
        note = str(row.get("note") or "")
        match = re.search(r"capability_name=([a-z0-9_]+)", note)
        if match:
            return match.group(1)
        return _safe_capability_name(row.get("content") or "")

    def _row_for_norm(self, norm: str) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT * FROM beanie_improvements WHERE norm=? "
                    "ORDER BY improvement_id DESC LIMIT 1", (norm,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception:
            return None

    def _row(self, improvement_id: int) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT * FROM beanie_improvements WHERE "
                    "improvement_id=?", (int(improvement_id),))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception:
            return None

    def _insert(self, content: str, norm: str, mechanism: str,
                hypothesis: str, baseline_fails: int, status: str,
                note: str = "") -> Optional[int]:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "INSERT INTO beanie_improvements (created_at, content,"
                    " norm, mechanism, hypothesis, baseline_fails, status,"
                    " acted, note) VALUES (?,?,?,?,?,?,?,0,?)",
                    (_now_iso(), content, norm, mechanism, hypothesis,
                     int(baseline_fails), status, note))
                conn.commit()
                return int(cur.lastrowid)
        except Exception as exc:
            app_logger.warning(f"Improvement insert failed (non-fatal): "
                               f"{exc}")
            return None

    def _update(self, improvement_id: int, **fields: Any) -> None:
        if not fields:
            return
        keys = ", ".join(f"{k}=?" for k in fields)
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    f"UPDATE beanie_improvements SET {keys} WHERE "
                    f"improvement_id=?",
                    (*fields.values(), int(improvement_id)))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Improvement update failed (non-fatal): "
                               f"{exc}")

    @staticmethod
    def _load_json(blob: Any) -> Any:
        if not blob:
            return None
        try:
            return json.loads(blob)
        except Exception:
            return blob

    def _revert_installed(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Undo a synthesized install for real: pop the live registry
        entry, bump the environment revision, remove the files. Best
        effort, each step recorded honestly."""
        capability = self._capability_name(row)
        unregistered = files_removed = False
        details = []
        try:
            from app.cognition.tool_registry import get_shared_registry
            registry = get_shared_registry()
            key = capability.lower()
            if key in getattr(registry, "_registry", {}):
                registry._registry.pop(key, None)
                try:
                    registry.note_environment_change(
                        f"reverted improvement #{row['improvement_id']}",
                        source="mind_improvement")
                except Exception:
                    pass
                unregistered = True
                details.append("live registry entry removed")
            else:
                details.append("no live registry entry to remove")
        except Exception as exc:
            details.append(f"registry revert skipped: {exc}")
        try:
            from app.agents.self_evolving_agent import SelfEvolvingAgent
            for path in (SelfEvolvingAgent.DYNAMIC_TOOLS_DIR /
                         f"dynamic_{capability}.py",
                         SelfEvolvingAgent.PLUGINS_DIR / f"{capability}.py"):
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
            files_removed = True
            details.append("installed files removed")
        except Exception as exc:
            details.append(f"file cleanup skipped: {exc}")
        return {"acted": unregistered or files_removed,
                "unregistered": unregistered,
                "files_removed": files_removed,
                "statement": "; ".join(details) or "nothing to undo"}
