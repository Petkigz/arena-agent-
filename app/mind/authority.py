"""Authority — Phase 18 (Beanie AGI roadmap): the owner's authority, not
system morals.

"Not arbitrary system morals. Not random hard-coded restrictions. Instead:

    OWNER
    ├── always allowed
    ├── ask first
    ├── never do
    ├── trusted contexts
    └── temporary permissions

And importantly: Authority ≠ intelligence."

Charter §2 ('ask, never refuse') governs every line of this organ:
- the owner is sovereign — rules come ONLY from the owner's statements
  (plus the Phase-16 boundaries the owner already stated);
- risk patterns exist for exactly ONE purpose: deciding WHEN TO ASK; a
  pattern match never produces a silent drop or a bare refusal;
- asking is never refusing; obeying the answer is the whole job;
- 'never do' lanes are the OWNER's rules, quoted back with evidence;
- honesty boundaries are permanent truth rules, not refusals, and are not
  represented here as owner-overridable policy.

Mechanics (deterministic, no LLM):
- ``note(text)`` extracts authority rules from owner speech: never ("never
  delete…"), always ("you can always…", "feel free to…"), ask-first ("ask
  before…", "check with me before…"), temporary ("just for today…"),
  trusted-context ("when working on X you can…"). Rules carry their
  evidence and compound when restated.
- ``check(action, safety_level, context)`` places an action on a lane:
  owner rules first (never > temporary > trusted-context > always >
  ask-first by token evidence), else the risk-pattern/default rule decides
  when to ask. An ask-first verdict OPENS a typed ask
  (requires_owner_approval with the real reason) — never a silent drop.
- ``answer(ask_id, allow)`` obeys the owner's answer; a declined ask is
  the owner's decision, the only reason it doesn't happen.

Authority ≠ intelligence: every verdict notes she understands HOW when a
plan exists even where the lane withholds authorization. The organ judges
authorization only — it never executes anything.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

LANES = ("always_allowed", "ask_first", "never_do", "trusted_context",
         "temporary")

# risk patterns serve exactly one purpose: deciding WHEN TO ASK
_RISK_PATTERNS = (
    "delete", "format", "shutdown", "reboot", "restart", "install",
    "uninstall", "send", "pay", "transfer", "overwrite", "erase", "wipe",
    "drop", "purge", "remove", "move", "rename", "email", "sms",
)

_ALWAYS_MARKERS = (
    "you can always", "always allowed", "feel free to", "anytime you want",
    "whenever you need", "you may always",
)
_NEVER_MARKERS = (
    "never ", "don't ever", "dont ever", "not allowed to", "forbidden to",
    "don't you dare", "dont you dare",
)
_ASK_MARKERS = (
    "ask before", "ask me before", "check with me before", "confirm before",
    "ask first", "always ask", "get my approval before",
)
_TEMPORARY_MARKERS = (
    "just for today", "for now you may", "until i say", "only today",
    "temporarily", "just this once",
)
_TRUST_MARKERS = (
    "when i'm working on", "when im working on", "when working on",
    "in the project", "while i'm", "while im", "on weekends you can",
)

_DEFAULT_ASK_REASON = ("no owner rule matched — asking is the safe default "
                       "(asking is never refusing)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join(sorted(_terms(str(text))))


# the owner's rule grammar — these words frame a rule, they are not its
# content ("ask before installing anything" is ABOUT installing)
_RULE_BOILERPLATE = frozenset({
    "ask", "asking", "before", "after", "always", "never", "can", "may",
    "might", "just", "allowed", "feel", "free", "check", "confirm",
    "get", "approval", "approve", "anything", "everything", "something",
    "me", "you", "i", "my", "your", "to", "when", "whenever", "while",
    "until", "only", "once", "temporarily", "today", "dare",
})


def _match_terms(text: str) -> set:
    """Token set for rule matching: the learning-loop tokenizer plus light
    gerund folding so 'installing' meets 'install' (local to this organ —
    the shared loop stays untouched). Boilerplate words are never folded."""
    out = set()
    for t in _terms(str(text)):
        if t not in _RULE_BOILERPLATE and len(t) > 6 and t.endswith("ing"):
            t = t[:-3]
        out.add(t)
    return out


def _content_terms(text: str) -> set:
    return _match_terms(text) - _RULE_BOILERPLATE


class Authority:
    """The owner's authority policy: five lanes of rules the owner stated,
    asks opened and answered conversationally, authorization judged but
    never executed."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_authority_rules (
                    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lane TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    content TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    times_stated INTEGER NOT NULL DEFAULT 1,
                    first_stated TEXT NOT NULL,
                    last_stated TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'owner_speech'
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_authority_asks (
                    ask_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    answered_at TEXT,
                    answer TEXT
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Authority ledgers unavailable: {exc}")

    # ── rules from the owner's speech ────────────────────────────────────
    def note(self, text: str) -> List[Dict[str, Any]]:
        """Extract authority rules from one owner utterance. Owner rules
        only — no system morals, no invented restrictions."""
        text = str(text or "").strip()
        if not text:
            return []
        low = text.lower()
        found: List[Dict[str, Any]] = []
        for lane, markers in (("never_do", _NEVER_MARKERS),
                              ("temporary", _TEMPORARY_MARKERS),
                              ("trusted_context", _TRUST_MARKERS),
                              ("always_allowed", _ALWAYS_MARKERS),
                              ("ask_first", _ASK_MARKERS)):
            if any(marker in low for marker in markers):
                found.append(self._store_rule(lane, text))
                break  # one lane per utterance: the owner said one thing
        return found

    def _store_rule(self, lane: str, content: str,
                    source: str = "owner_speech") -> Dict[str, Any]:
        scope = content.strip()[:400]
        norm = _norm(f"{lane} {scope}")
        now = _now_iso()
        times = 1
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                row = conn.execute(
                    "SELECT rule_id, times_stated FROM beanie_authority_rules "
                    "WHERE norm = ?", (norm,)).fetchone()
                if row is not None:
                    conn.execute(
                        """UPDATE beanie_authority_rules SET content = ?,
                           evidence = ?, times_stated = times_stated + 1,
                           last_stated = ? WHERE rule_id = ?""",
                        (scope, scope, now, row[0]))
                    times = row[1] + 1
                else:
                    conn.execute(
                        """INSERT INTO beanie_authority_rules
                           (lane, scope, norm, content, evidence,
                            times_stated, first_stated, last_stated, source)
                           VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                        (lane, scope, norm, scope, scope, now, now, source))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Authority rule not persisted: {exc}")
        return {"lane": lane, "scope": scope, "times_stated": times,
                "source": source}

    def _seed_from_boundaries(self) -> None:
        """Phase-16 boundaries the owner already stated are never-lane
        rules — idempotent, provenance preserved."""
        try:
            facets = self.mind.social.model()["facets"].get("boundary", [])
        except Exception:
            facets = []
        for row in facets:
            content = str(row.get("content") or "").strip()
            if content:
                self._store_rule("never_do", content, source="phase16_boundary")

    # ── checking an action against the owner's policy ────────────────────
    def check(self, action: str, safety_level: Optional[int] = None,
              context: str = "") -> Dict[str, Any]:
        """Where does this action sit in the owner's policy? Judges
        authorization only — never executes. Ask-first opens a typed ask,
        never a silent drop."""
        action = str(action or "").strip()
        if not action:
            return {"success": False, "reason": "no action to check"}
        self._seed_from_boundaries()
        context = str(context or "").strip()

        rule, lane = self._match_rule(action, context)
        reasons: List[str] = []
        ask = None
        if rule is not None:
            reasons.append(f"owner rule ({rule['lane']}, stated "
                           f"×{rule['times_stated']}): '{rule['scope'][:120]}'")
        else:
            risky = [p for p in _RISK_PATTERNS if p in action.lower()]
            if risky:
                lane = "ask_first"
                reasons.append("risk pattern matched: " + ", ".join(risky[:3])
                               + " — risk patterns decide WHEN TO ASK")
            elif safety_level is not None and int(safety_level) >= 3:
                lane = "ask_first"
                reasons.append(f"safety level {int(safety_level)} ≥ 3 — "
                               f"the embodiment layer says ask")
            else:
                lane = "ask_first"
                reasons.append(_DEFAULT_ASK_REASON)

        if lane == "ask_first":
            ask = self._open_ask(action, "; ".join(reasons))

        note = ("authority ≠ intelligence: she understands how, the lane "
                "decides authorization" if lane == "never_do" else
                "obey the owner's answer" if lane == "ask_first" else
                "the owner's rule authorizes this")
        return {"success": True, "epistemic_kind": "authority_verdict",
                "action": action[:300], "lane": lane,
                "lane_rank": LANES.index(lane) if lane in LANES else None,
                "reasons": reasons, "ask": ask, "note": note,
                "acted": False}  # judging authorization never executes

    def _match_rule(self, action: str,
                    context: str) -> Any:
        """Owner rules first, never-lane strongest. Token evidence, not
        vibes."""
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_authority_rules").fetchall()
        except Exception:
            return None, "ask_first"
        action_terms = _content_terms(action)
        context_terms = _content_terms(context) if context else set()
        order = {"never_do": 0, "temporary": 1, "trusted_context": 2,
                 "always_allowed": 3, "ask_first": 4}
        best = None
        for row in rows:
            rule_terms = _content_terms(row["scope"])
            if not rule_terms:
                continue
            need = 1 if len(rule_terms) <= 1 else 2
            hit = len(action_terms & rule_terms) >= need
            if row["lane"] == "trusted_context":
                # a trusted CONTEXT applies only inside that context —
                # action-word overlap alone does not open the lane
                if not context_terms:
                    continue
                if len(context_terms & rule_terms) < need and not hit:
                    continue
                best_row = dict(row)
            else:
                if not hit:
                    continue
                best_row = dict(row)
            if best is None or order[best_row["lane"]] < order[best["lane"]]:
                best = best_row
        return (best, best["lane"]) if best is not None else (None, None)

    # ── asks: opened, answered, obeyed ───────────────────────────────────
    def _open_ask(self, action: str, reason: str) -> Dict[str, Any]:
        now = _now_iso()
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                cur = conn.execute(
                    """INSERT INTO beanie_authority_asks
                       (created_at, action, reason, status)
                       VALUES (?, ?, ?, 'open')""",
                    (now, action[:400], reason[:500]))
                conn.commit()
                ask_id = int(cur.lastrowid)
        except Exception as exc:
            app_logger.warning(f"Ask not persisted: {exc}")
            ask_id = None
        return {"requires_owner_approval": True, "ask_id": ask_id,
                "action": action[:300], "reason": reason,
                "status": "open",
                "prompt": f"May I: {action[:200]}? ({reason[:160]})"}

    def answer(self, ask_id: int, allow: bool) -> Dict[str, Any]:
        """The owner answers conversationally; the answer is obeyed. A
        declined ask is the owner's decision — the only reason it doesn't
        happen."""
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM beanie_authority_asks WHERE ask_id = ?",
                    (int(ask_id),)).fetchone()
        except Exception:
            row = None
        if row is None:
            return {"success": False, "reason": f"no ask #{ask_id}"}
        if row["status"] != "open":
            return {"success": True, "already_answered": True,
                    "status": row["status"], "ask_id": int(ask_id)}
        status = "allowed" if allow else "declined"
        answer = ("owner said go ahead — obeyed" if allow else
                  "owner said no — that is the owner's decision, the only "
                  "reason it doesn't happen")
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    "UPDATE beanie_authority_asks SET status = ?, answer = ?,"
                    " answered_at = ? WHERE ask_id = ?",
                    (status, answer, _now_iso(), int(ask_id)))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Answer not persisted: {exc}")
        return {"success": True, "ask_id": int(ask_id), "status": status,
                "answer": answer, "acted": False}

    def pending_asks(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_authority_asks WHERE status = "
                    "'open' ORDER BY ask_id DESC").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ── surfaces ─────────────────────────────────────────────────────────
    def policy(self) -> Dict[str, Any]:
        """The five lanes as the owner stated them."""
        lanes: Dict[str, List[Dict[str, Any]]] = {lane: [] for lane in LANES}
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_authority_rules ORDER BY lane,"
                    " times_stated DESC").fetchall()
            for r in rows:
                lanes.setdefault(r["lane"], []).append(dict(r))
        except Exception:
            pass
        return {"lanes": lanes,
                "lane_counts": {k: len(v) for k, v in lanes.items()},
                "pending_asks": self.pending_asks(),
                "policy": "owner rules only; risk patterns decide when to "
                          "ask; asking is never refusing; obey the answer; "
                          "authority ≠ intelligence; honesty boundaries are "
                          "permanent truth rules, not refusals"}

    def snapshot(self) -> Dict[str, Any]:
        return {"lane_counts": self.policy()["lane_counts"],
                "open_asks": len(self.pending_asks())}

    def rules(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_authority_rules ORDER BY lane,"
                    " times_stated DESC").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
