"""Phase 7 (owner plan 2026-09-10): information-gain-based continuous cognition.

Objective: Beanie notices, reasons, and learns continuously WITHOUT
becoming a noisy replay engine. The owner's contract:

  * Intelligence is not limited; execution authority is explicit.
    Read-only probes (observe, re-check state, resolve contradictions)
    are allowed autonomous behavior; anything that CHANGES the machine
    stays approval-gated (ActionGate / Phase 4 contracts).
  * Every autonomous investigation must answer the SEVEN QUESTIONS:
    what uncertainty exists, why it matters, what evidence would
    resolve it, cost/risk, is the probe read-only, what decision could
    it change, when does the question expire. A question missing any
    answer is NOT admitted — "unknown" alone is never a reason.
  * No re-running vague, stale, or superseded questions: duplicates of
    open/answered questions are rejected; questions expire.
  * The owner can pause, inspect, approve, reject, or delete every
    question (API + persisted state).

Contract (owner rules, standing):
  * kill switch: ``ARENA_CURIOSITY=0`` silences the organ entirely;
  * autonomous EXECUTION remains gated behind AUTONOMY_MODE (Phase 0
    default: off) — this organ curates questions and answers
    owner-visible ones; it never launches, moves, or sends anything;
  * fail-open everywhere; bounded by design (open-question cap, TTLs,
    read-only probe whitelist).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Admission policy (deliberately explicit):
MIN_GAIN = 0.3          # below this, resolving it changes no decision
MAX_OPEN_QUESTIONS = 25  # bounded — never a noisy replay engine
DEFAULT_TTL_HOURS = 48.0 # every question expires

# Read-only probe whitelist: the ONLY evidence-gathering this organ may
# run autonomously. Anything else stays owner-gated execution.
READ_ONLY_PROBES = frozenset({"process_state", "file_exists", "entity_state"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enabled() -> bool:
    try:
        from app.config import settings
        raw = str(getattr(settings, "ARENA_CURIOSITY", "1")).strip().lower()
        return raw not in ("0", "false", "off", "no", "")
    except Exception:
        return True  # fail-open


@dataclass
class CuriosityQuestion:
    """One bounded investigation, carrying the owner's seven answers."""

    id: str = field(default_factory=lambda: uuid4().hex)
    subject: str = ""
    predicate: str = ""
    uncertainty: str = ""        # 1. what uncertainty exists?
    rationale: str = ""          # 2. why does resolving it matter?
    resolving_evidence: str = "" # 3. what evidence would resolve it?
    cost_risk: str = ""          # 4. what is the cost/risk?
    read_only: bool = False      # 5. is the probe read-only?
    decision_impact: str = ""    # 6. what decision could it change?
    expires_at: str = ""         # 7. when does the question expire?
    probe_kind: str = ""         # whitelist key for run_probe
    information_gain: float = 0.0
    gain_explanation: str = ""
    source: str = "world_model"
    status: str = "candidate"    # candidate|open|approved|rejected|deleted|expired|answered
    answer: Optional[Dict[str, Any]] = None
    owner_note: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def missing_contract_fields(self) -> List[str]:
        missing = []
        if not self.uncertainty:
            missing.append("uncertainty")
        if not self.rationale:
            missing.append("rationale")
        if not self.resolving_evidence:
            missing.append("resolving_evidence")
        if not self.cost_risk:
            missing.append("cost_risk")
        if not self.decision_impact:
            missing.append("decision_impact")
        if not self.expires_at:
            missing.append("expires_at")
        return missing

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__)
        d["read_only"] = bool(self.read_only)
        return d


class CuriosityScheduler:
    """Curates bounded, expiring, read-only questions about the world.

    Persisted in the owner's SQLite DB (additive tables); every state
    change is inspectable through the owner-control API.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        from app.config import settings
        self.db_path = db_path or str(settings.DB_PATH)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS curiosity_questions (
                    id TEXT PRIMARY KEY, subject TEXT, predicate TEXT,
                    uncertainty TEXT, rationale TEXT, resolving_evidence TEXT,
                    cost_risk TEXT, read_only INTEGER, decision_impact TEXT,
                    expires_at TEXT, probe_kind TEXT, information_gain REAL,
                    gain_explanation TEXT, source TEXT, status TEXT,
                    answer TEXT, owner_note TEXT, created_at TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS curiosity_meta (
                    key TEXT PRIMARY KEY, value TEXT
                );
            """)

    # ── owner controls: pause / inspect / decide ─────────────────────────

    def pause(self, paused: bool = True) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO curiosity_meta VALUES ('paused', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("1" if paused else "0",))

    def resume(self) -> None:
        self.pause(False)

    def is_paused(self) -> bool:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT value FROM curiosity_meta WHERE key = 'paused'").fetchone()
            return bool(row) and row["value"] == "1"
        except Exception:
            return False  # fail-open: a meta glitch never fabricates a pause

    def inspect(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """The owner's window: every question, its seven answers, its state."""
        query = "SELECT * FROM curiosity_questions"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY information_gain DESC, created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._dict(row) for row in rows]

    def decide(self, question_id: str, decision: str,
               owner_note: str = "") -> Dict[str, Any]:
        """Owner verdict: approve / reject / delete. Nothing autonomous
        happens to a question the owner has not approved."""
        decision = str(decision or "").strip().lower()
        if decision not in ("approve", "reject", "delete"):
            return {"success": False, "reason": f"unknown decision '{decision}'"}
        new_status = {"approve": "approved", "reject": "rejected",
                      "delete": "deleted"}[decision]
        with self._connect() as conn:
            row = conn.execute("SELECT id, status FROM curiosity_questions WHERE id = ?",
                               (question_id,)).fetchone()
            if row is None:
                return {"success": False, "reason": "no such question"}
            conn.execute(
                "UPDATE curiosity_questions SET status = ?, owner_note = ?, updated_at = ? "
                "WHERE id = ?", (new_status, str(owner_note), _now(), question_id))
        return {"success": True, "question_id": question_id, "status": new_status}

    # ── question generation (bounded, evidence-driven) ───────────────────

    def generate_candidates(self, world: Any,
                            active_goals: Optional[List[str]] = None,
                            limit: int = 10) -> List[CuriosityQuestion]:
        """Derive questions from REAL world-model signals — contradictions
        and staleness that some decision depends on. Never from mere
        unknownness: 'I don't know X' alone generates nothing.
        """
        if not _enabled() or world is None:
            return []
        goals = [str(g) for g in (active_goals or []) if str(g).strip()]
        out: List[CuriosityQuestion] = []
        # 1) Contradictions: two sources disagree — resolving it changes
        #    every decision that trusts either claim.
        try:
            for c in world.detect_contradictions()[:limit]:
                a, b = c.get("observation_a", {}), c.get("observation_b", {})
                q = CuriosityQuestion(
                    subject=str(c.get("subject", "")), predicate=str(c.get("predicate", "")),
                    uncertainty=(f"sources disagree about {c.get('subject')}.{c.get('predicate')}: "
                                 f"{a.get('source')} says '{a.get('value')}', "
                                 f"{b.get('source')} says '{b.get('value')}'"),
                    rationale="contradictory facts would mislead every decision that trusts either claim",
                    resolving_evidence=f"one fresh read-only observation of {c.get('subject')}.{c.get('predicate')}",
                    cost_risk="none — read-only probe, milliseconds",
                    read_only=True,
                    decision_impact=(f"decisions relying on {c.get('subject')}.{c.get('predicate')} "
                                     "currently rest on conflicting evidence"),
                    probe_kind=self._probe_kind_for(str(c.get("predicate", ""))),
                    information_gain=0.9,
                    expires_at=default_ttl_expiry(),
                    source="world_model_contradiction",
                )
                q.gain_explanation = self._explain_gain(q)
                out.append(q)
        except Exception:
            pass  # fail-open
        # 2) Staleness WITH decision impact: an old fact some active goal
        #    depends on. Staleness alone generates nothing (exit criterion:
        #    never investigate merely because something is unknown).
        try:
            for obs in world.stale_observations()[:limit]:
                goal = self._goal_depending_on(obs.subject, goals)
                if goal is None:
                    continue  # mere unknownness — NOT a reason
                q = CuriosityQuestion(
                    subject=str(obs.subject), predicate=str(obs.predicate),
                    uncertainty=(f"last known {obs.subject}.{obs.predicate} = '{obs.value}' "
                                 f"(observed {obs.observed_at}) is past its freshness window"),
                    rationale=f"an active goal depends on this fact: '{goal[:80]}'",
                    resolving_evidence=f"fresh read-only observation of {obs.subject}.{obs.predicate}",
                    cost_risk="none — read-only probe, milliseconds",
                    read_only=True,
                    decision_impact=f"goal '{goal[:80]}' acts on this state",
                    probe_kind=self._probe_kind_for(str(obs.predicate)),
                    information_gain=0.7,
                    expires_at=default_ttl_expiry(),
                    source="world_model_staleness",
                )
                q.gain_explanation = self._explain_gain(q)
                out.append(q)
        except Exception:
            pass  # fail-open
        return out[: max(1, min(int(limit), 25))]

    @staticmethod
    def _goal_depending_on(subject: str, goals: List[str]) -> Optional[str]:
        needle = str(subject or "").strip().lower()
        if not needle:
            return None
        for g in goals:
            if needle in g.lower():
                return g
        return None

    @staticmethod
    def _probe_kind_for(predicate: str) -> str:
        p = str(predicate or "").lower()
        if "process" in p or "running" in p:
            return "process_state"
        if "file" in p or "path" in p or "exists" in p:
            return "file_exists"
        return "entity_state"

    @staticmethod
    def _explain_gain(q: CuriosityQuestion) -> str:
        """The expected information gain, in words the owner can audit."""
        if q.source == "world_model_contradiction":
            return (f"gain {q.information_gain:.1f}/1.0 — resolves a direct conflict between "
                    f"two sourced claims about {q.subject}.{q.predicate}; until then every "
                    f"decision using this fact is a coin flip between them")
        return (f"gain {q.information_gain:.1f}/1.0 — refreshes a stale fact an active goal "
                f"acts on ({q.subject}.{q.predicate}); the alternative is deciding on data "
                f"already past its freshness window")

    # ── admission: the seven-question gate ───────────────────────────────

    def admit(self, q: CuriosityQuestion) -> Dict[str, Any]:
        """Admit a question as OPEN only when it honors the full contract.
        Rejections are honest and specific — silence is never the answer.
        """
        if not _enabled():
            return {"admitted": False, "reason": "curiosity disabled (ARENA_CURIOSITY=0)"}
        missing = q.missing_contract_fields()
        if missing:
            return {"admitted": False,
                    "reason": f"incomplete contract — missing: {', '.join(missing)}"}
        if not q.read_only:
            return {"admitted": False,
                    "reason": "probe is not read-only — that is owner-gated execution, not curiosity"}
        if q.probe_kind and q.probe_kind not in READ_ONLY_PROBES:
            return {"admitted": False,
                    "reason": f"no read-only probe exists for '{q.probe_kind}'"}
        try:
            if datetime.fromisoformat(q.expires_at) <= datetime.now(timezone.utc):
                return {"admitted": False, "reason": "question already expired"}
        except (TypeError, ValueError):
            return {"admitted": False, "reason": "invalid expiry"}
        if q.information_gain < MIN_GAIN:
            return {"admitted": False,
                    "reason": f"expected gain {q.information_gain:.2f} < {MIN_GAIN} — resolves no decision"}
        if self.is_paused():
            return {"admitted": False, "reason": "curiosity paused by owner"}
        # No re-running: an open or answered question on the same fact
        # supersedes this one (vague/stale/superseded never re-runs).
        with self._connect() as conn:
            dup = conn.execute(
                "SELECT id, status FROM curiosity_questions "
                "WHERE subject = ? AND predicate = ? AND status IN ('open', 'approved', 'answered') "
                "AND expires_at > ? LIMIT 1",
                (q.subject, q.predicate, _now())).fetchone()
            open_count = conn.execute(
                "SELECT COUNT(*) AS n FROM curiosity_questions "
                "WHERE status IN ('open', 'approved')").fetchone()["n"]
        if dup is not None:
            return {"admitted": False,
                    "reason": f"superseded by existing {dup['status']} question {dup['id']} "
                              f"on {q.subject}.{q.predicate}"}
        if open_count >= MAX_OPEN_QUESTIONS:
            return {"admitted": False,
                    "reason": f"open-question cap ({MAX_OPEN_QUESTIONS}) reached — bounded by design"}
        q.status = "open"
        q.updated_at = _now()
        self._save(q)
        return {"admitted": True, "question_id": q.id}

    def _save(self, q: CuriosityQuestion) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO curiosity_questions VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (q.id, q.subject, q.predicate, q.uncertainty, q.rationale,
                 q.resolving_evidence, q.cost_risk, int(q.read_only),
                 q.decision_impact, q.expires_at, q.probe_kind,
                 q.information_gain, q.gain_explanation, q.source, q.status,
                 json.dumps(q.answer) if q.answer is not None else None,
                 q.owner_note, q.created_at, q.updated_at))

    @staticmethod
    def _dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["read_only"] = bool(d.get("read_only"))
        if d.get("answer"):
            try:
                d["answer"] = json.loads(d["answer"])
            except (TypeError, ValueError):
                pass
        return d

    def sweep(self, world: Any, active_goals: Optional[List[str]] = None) -> Dict[str, Any]:
        """One bounded pass: expire due questions, generate + admit new
        ones. Returns a summary for the cycle event log / owner view.
        """
        summary = {"generated": 0, "admitted": 0, "expired": 0,
                   "rejections": [], "paused": self.is_paused()}
        if not _enabled():
            summary["disabled"] = True
            return summary
        summary["expired"] = self.expire_due()
        for q in self.generate_candidates(world, active_goals):
            summary["generated"] += 1
            verdict = self.admit(q)
            if verdict.get("admitted"):
                summary["admitted"] += 1
            else:
                summary["rejections"].append(
                    {"subject": q.subject, "predicate": q.predicate,
                     "reason": verdict.get("reason", "")})
        return summary

    # ── expiry + read-only probes ─────────────────────────────────────────

    def expire_due(self, now: Optional[str] = None) -> int:
        now = now or _now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE curiosity_questions SET status = 'expired', updated_at = ? "
                "WHERE status IN ('candidate', 'open', 'approved') AND expires_at <= ?",
                (now, now))
            return cur.rowcount or 0

    def run_probe(self, question_id: str, world: Optional[Any] = None) -> Dict[str, Any]:
        """Run the READ-ONLY probe for a question. Whitelist-enforced:
        anything that could change the machine is refused here, full stop.
        Answered only on real evidence; failures are recorded honestly.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM curiosity_questions WHERE id = ?",
                               (question_id,)).fetchone()
        if row is None:
            return {"success": False, "reason": "no such question"}
        q_dict = self._dict(row)
        if q_dict["status"] not in ("open", "approved"):
            return {"success": False,
                    "reason": f"question is {q_dict['status']} — only open/approved questions probe"}
        if not q_dict["read_only"]:
            return {"success": False, "reason": "probe is not read-only — refused"}
        kind = q_dict.get("probe_kind") or ""
        if kind not in READ_ONLY_PROBES:
            return {"success": False, "reason": f"no read-only probe for '{kind}'"}
        evidence: Dict[str, Any] = {"kind": kind, "subject": q_dict["subject"],
                                    "predicate": q_dict["predicate"], "observed_at": _now()}
        try:
            if kind == "process_state":
                from app.tools.app_inventory import SystemAppInventory
                probe = SystemAppInventory.verify_app_running(q_dict["subject"], wait_seconds=2.0)
                evidence.update({"running": bool(probe.get("process_verified")),
                                 "pid": probe.get("pid"),
                                 "process_name": probe.get("process_name", ""),
                                 "source": "psutil_scan"})
                value = "running" if evidence["running"] else "not_running"
            elif kind == "file_exists":
                import os
                exists = bool(q_dict["subject"]) and os.path.exists(q_dict["subject"])
                evidence.update({"exists": exists, "source": "os.path.exists"})
                value = "exists" if exists else "missing"
            else:  # entity_state
                if world is None:
                    return {"success": False, "reason": "entity_state probe needs the world model"}
                state = world.get_entity_state(q_dict["subject"], q_dict["predicate"])
                if state is None:
                    evidence.update({"observed": False, "source": "world_model"})
                    value = "still unobserved"
                else:
                    evidence.update({"observed": True, "value": state.get("value"),
                                     "source": state.get("source", "world_model")})
                    value = str(state.get("value"))
        except Exception as exc:  # fail-open: a failed probe answers nothing
            return {"success": False,
                    "reason": f"probe failed honestly: {type(exc).__name__}: {exc}"}
        answer = {"value": value, "evidence": evidence}
        with self._connect() as conn:
            conn.execute(
                "UPDATE curiosity_questions SET status = 'answered', answer = ?, updated_at = ? "
                "WHERE id = ?", (json.dumps(answer), _now(), question_id))
        # The answer becomes a world-model observation with provenance.
        if world is not None and value not in ("still unobserved",):
            try:
                from app.cognition.world_model import Observation
                world.observe(Observation(
                    id=uuid4().hex, subject=q_dict["subject"], predicate=q_dict["predicate"],
                    value=value, source="curiosity_probe", observation_type="direct"))
            except Exception:
                pass  # fail-open: recording never fails the probe
        return {"success": True, "question_id": question_id, "answer": answer}


def default_ttl_expiry(hours: float = DEFAULT_TTL_HOURS) -> str:
    """Expiry for questions created without an explicit deadline."""
    return (datetime.now(timezone.utc) + timedelta(hours=max(0.1, float(hours)))).isoformat()
