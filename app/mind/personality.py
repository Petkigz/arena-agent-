"""Personality — Phase 17 (Beanie AGI roadmap): a personality that develops,
derived from evidence — never a hard-coded mask.

"Don't hard-code the personality forever. Start with a basic identity. Then:
interactions → experiences → preferences → communication patterns → values
learned from owner → personality development. You should eventually be able
to notice 'Beanie has changed' because her behavior actually changed
through experience."

Mechanics (deterministic, no LLM):
- the profile is DERIVED on demand from her real ledgers — nothing is
  invented:
  * identity: the Phase-1 BeanieIdentity record (the basic identity she
    starts from);
  * experience profile: the learning ledger (how much she has lived
    through, by kind);
  * epistemic calibration: the imagination ledger (predictions confirmed
    vs refuted by reality);
  * curiosity stance: open vs resolved unknowns and how they were
    resolved;
  * communication patterns: HER OWN replies, sampled at the door
    (assistant_reply), with an early-vs-late trend — measurable change;
  * values learned from the owner: explicit value statements ("it's
    important to me that …", "always be honest", "never lie") — the
    owner's values only, per the charter;
  * adaptation: how she mirrors the owner's measured communication style
    (Phase 16).
- every trait carries evidence and an observation count; a trait with no
  evidence does not exist in the profile;
- ``derive()`` snapshots the profile and diffs it against the previous
  snapshot — ``changes()`` is the verifiable record of "Beanie has
  changed".

Honesty rules:
- personality describes observed behavior; it performs nothing;
- no values but the owner's (never system morals, never fabricated);
- an empty life yields a basic identity and the honest statement that no
  traits have formed yet.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

# owner value statements (the charter: owner's values only)
_VALUE_MARKERS = (
    "important to me", "i value", "matters to me", "always be honest",
    "never lie", "honesty", "privacy matters", "i care about",
    "what matters", "be truthful", "don't hide", "dont hide",
)

_REPLY_FLOOR = 5   # samples before she describes her own reply style
_TREND_SPLIT = 10  # samples before an early-vs-late trend is claimed


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Personality:
    """The developing personality: basic identity + traits derived from
    evidence. Describes; performs nothing."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_values (
                    value_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    times_heard INTEGER NOT NULL DEFAULT 1,
                    first_heard TEXT NOT NULL,
                    last_heard TEXT NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_reply_samples (
                    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    chars INTEGER NOT NULL,
                    has_question INTEGER NOT NULL DEFAULT 0
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS
                    beanie_personality_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    derived_at TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    changes TEXT
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Personality ledgers unavailable: {exc}")

    # ── values learned from the owner (owner's values only) ──────────────
    def note(self, text: str) -> List[Dict[str, Any]]:
        """Extract value statements from one owner utterance. Markers
        only; system morals are never injected."""
        text = str(text or "").strip()
        if not text:
            return []
        low = text.lower()
        found: List[Dict[str, Any]] = []
        for marker in _VALUE_MARKERS:
            if marker in low:
                found.append(self._store_value(marker, text))
                break  # one value facet per utterance is honest enough
        return found

    def _store_value(self, marker: str, content: str) -> Dict[str, Any]:
        key = marker.strip()[:120]
        now = _now_iso()
        times = 1
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                row = conn.execute(
                    "SELECT value_id, times_heard FROM beanie_values "
                    "WHERE key = ?", (key,)).fetchone()
                if row is not None:
                    conn.execute(
                        """UPDATE beanie_values SET content = ?, evidence = ?,
                           times_heard = times_heard + 1, last_heard = ?
                           WHERE value_id = ?""",
                        (content[:400], content[:400], now, row[0]))
                    times = row[1] + 1
                else:
                    conn.execute(
                        """INSERT INTO beanie_values
                           (key, content, evidence, times_heard, first_heard,
                            last_heard) VALUES (?, ?, ?, 1, ?, ?)""",
                        (key, content[:400], content[:400], now, now))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Value not persisted: {exc}")
        return {"facet": "value", "key": key, "content": content[:400],
                "times_heard": times}

    def values(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM beanie_values ORDER BY times_heard DESC,"
                    " last_heard DESC").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ── her own communication, sampled at the door ───────────────────────
    def record_reply(self, reply: Any) -> Optional[Dict[str, Any]]:
        """One of HER replies becomes evidence about her own communication
        pattern."""
        text = str(reply or "").strip()
        if not text:
            return None
        sample = {"chars": len(text), "has_question": int("?" in text)}
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_reply_samples
                       (recorded_at, chars, has_question) VALUES (?, ?, ?)""",
                    (_now_iso(), sample["chars"], sample["has_question"]))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Reply sample not persisted: {exc}")
        return sample

    def _reply_samples(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT chars, has_question FROM beanie_reply_samples "
                    "ORDER BY sample_id").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def communication_patterns(self) -> Dict[str, Any]:
        """Her own reply style: measured, with an early-vs-late trend when
        there is enough history to compare."""
        samples = self._reply_samples()
        if len(samples) < _REPLY_FLOOR:
            return {"known": False,
                    "reason": f"needs ≥{_REPLY_FLOOR} of her own replies to "
                              f"describe a pattern (have {len(samples)})"}
        chars = [s["chars"] for s in samples]
        avg = sum(chars) / len(chars)
        q_rate = sum(s["has_question"] for s in samples) / len(samples)
        out: Dict[str, Any] = {"known": True, "measured": len(samples),
                               "avg_reply_chars": round(avg, 1),
                               "question_rate": round(q_rate, 2),
                               "summary": ("terse" if avg < 80 else
                                           "expansive" if avg > 400 else
                                           "conversational")}
        if len(samples) >= _TREND_SPLIT:
            half = len(samples) // 2
            early = sum(chars[:half]) / half
            late = sum(chars[-half:]) / half
            drift = (late - early) / early if early else 0.0
            out["trend"] = ("lengthening" if drift > 0.15 else
                            "shortening" if drift < -0.15 else "stable")
            out["trend_drift"] = round(drift, 2)
        return out

    # ── the derived profile ──────────────────────────────────────────────
    def derive(self) -> Dict[str, Any]:
        """Compute the profile from the real ledgers, snapshot it, and diff
        against the previous snapshot — the record of having changed."""
        profile = self._profile()
        payload = json.dumps(profile, sort_keys=True)
        previous = self._latest_snapshot()
        changes = self._diff(previous, profile) if previous else None
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    """INSERT INTO beanie_personality_snapshots
                       (derived_at, profile, changes) VALUES (?, ?, ?)""",
                    (_now_iso(), payload,
                     json.dumps(changes) if changes is not None else None))
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Personality snapshot not persisted: {exc}")
        return {"success": True, "profile": profile,
                "changed": bool(changes), "changes": changes,
                "acted": False}  # describing herself is not an action

    def _profile(self) -> Dict[str, Any]:
        traits: Dict[str, Dict[str, Any]] = {}

        learning = self._safe(lambda: self.mind.learning.stats(), {})
        if learning.get("total_experiences"):
            traits["experience"] = {
                "description": (f"has lived through "
                                f"{learning['total_experiences']} recorded "
                                f"experiences"),
                "evidence": learning.get("by_kind", {}),
                "observations": int(learning["total_experiences"]),
            }

        imag = self._safe(lambda: self.mind.imagination.stats(), {})
        if imag.get("comparisons"):
            traits["epistemic_calibration"] = {
                "description": (f"predictions checked against reality: "
                                f"{imag.get('confirmed', 0)} confirmed, "
                                f"{imag.get('refuted', 0)} refuted"),
                "evidence": {"confirmed": imag.get("confirmed", 0),
                             "refuted": imag.get("refuted", 0)},
                "observations": int(imag["comparisons"]),
            }

        cur = self._safe(lambda: self.mind.curiosity.stats(), {})
        if cur.get("total_unknowns"):
            traits["curiosity_stance"] = {
                "description": (f"{cur.get('open', 0)} open unknowns, "
                                f"{cur.get('resolved', 0)} resolved"),
                "evidence": cur.get("resolved_by", {}),
                "observations": int(cur["total_unknowns"]),
            }

        patterns = self.communication_patterns()
        if patterns.get("known"):
            traits["communication_pattern"] = {
                "description": (f"her replies are "
                                f"{patterns.get('summary')} "
                                f"(avg {patterns.get('avg_reply_chars')} "
                                f"chars)"
                                + (f", {patterns['trend']} over time"
                                   if patterns.get("trend") else "")),
                "evidence": {k: v for k, v in patterns.items()
                             if k not in ("known", "reason")},
                "observations": int(patterns.get("measured", 0)),
            }

        vals = self.values()
        if vals:
            traits["values_from_owner"] = {
                "description": (f"{len(vals)} value(s) learned from the "
                                f"owner — the owner's values only"),
                "evidence": [f"{v['key']} (×{v['times_heard']})"
                             for v in vals[:6]],
                "observations": sum(v["times_heard"] for v in vals),
            }

        style = self._safe(lambda: self.mind.social.style(), {})
        if style.get("known"):
            traits["adaptation"] = {
                "description": (f"owner speaks {style.get('summary')}; she "
                                f"adapts her register to it"),
                "evidence": {"owner_avg_message_chars":
                             style.get("avg_message_chars")},
                "observations": int(style.get("measured", 0)),
            }

        identity = {}
        try:
            identity = self.mind.identity.to_dict()
        except Exception:
            pass
        return {"identity": identity, "traits": traits,
                "trait_names": sorted(traits.keys()),
                "policy": "personality = basic identity + traits derived "
                          "from evidence; nothing invented, nothing "
                          "performed; the owner's values only"}

    # ── change tracking: 'Beanie has changed' ────────────────────────────
    def changes(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT derived_at, changes FROM
                       beanie_personality_snapshots WHERE changes IS NOT NULL
                       ORDER BY snapshot_id DESC LIMIT ?""",
                    (int(limit),)).fetchall()
            out = []
            for r in rows:
                try:
                    out.append({"derived_at": r["derived_at"],
                                "changes": json.loads(r["changes"])})
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def profile(self) -> Dict[str, Any]:
        """Latest derived profile (or a fresh derivation if none)."""
        latest = self._latest_snapshot()
        if latest is not None:
            return latest
        return self._profile()

    def snapshot(self) -> Dict[str, Any]:
        """Compact surface for the state skeleton."""
        p = self.profile()
        return {"traits": p.get("trait_names", []),
                "values": [v["key"] for v in self.values()][:10],
                "communication": self.communication_patterns(),
                "policy": p.get("policy", "")}

    # ── internals ────────────────────────────────────────────────────────
    def _latest_snapshot(self) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                row = conn.execute(
                    "SELECT profile FROM beanie_personality_snapshots "
                    "ORDER BY snapshot_id DESC LIMIT 1").fetchone()
            return json.loads(row[0]) if row is not None else None
        except Exception:
            return None

    @staticmethod
    def _diff(previous: Dict[str, Any], current: Dict[str, Any]) -> List[str]:
        changed: List[str] = []
        old_traits = previous.get("traits", {})
        new_traits = current.get("traits", {})
        for name in sorted(set(old_traits) | set(new_traits)):
            old = old_traits.get(name)
            new = new_traits.get(name)
            if old is None and new is not None:
                changed.append(f"trait formed: {name}")
            elif new is None and old is not None:
                changed.append(f"trait lost: {name}")
            elif json.dumps(old, sort_keys=True) != json.dumps(new,
                                                               sort_keys=True):
                changed.append(f"trait changed: {name}")
        return changed

    @staticmethod
    def _safe(fn: Any, default: Any) -> Any:
        try:
            return fn()
        except Exception:
            return default
