"""Presence — Phase 22 (Beanie AGI roadmap): voice-first Beanie.

"The desktop shouldn't look like a traditional dashboard… Voice:
primary. Text: backup. Visual UI: contextual window into the mind. The
complicated information exists when needed, not permanently."

The presence organ is the mind's OWN account of how she is present in
the conversation right now — never staged:

- the STATE vocabulary is the design system's own presence state machine
  (``design/tokens.json`` → ``beanie.states``: idle / listening /
  thinking / speaking / working / acting / observing / success / error /
  offline) — one shared vocabulary, rendered per platform;
- ``note(state)`` records real transitions; states outside the
  vocabulary are refused, never invented; with no activity on record she
  reports ``idle`` honestly (never pretends to be busy);
- ``context_window()`` is the contextual window into the mind — the
  complicated information exists WHEN NEEDED: the recent conversation
  (the door's entry ledger), open asks awaiting the owner's answer,
  active goals, the top open unknowns, and model-changing lessons — each
  bounded, each from a real ledger, each section honest when
  unavailable;
- ``voice_turn(text)`` is the voice-primary door: a transcript enters
  the ONE mind exactly like any other modality, and the reply comes back
  with the presence state the evidence supports (verified success →
  success; verified failure → error; no verdict → nothing claimed).

The voice pipeline itself (``backend/voice`` orchestrator: wake word,
VAD, STT, TTS) stays wired as a callable — it calls this organ, one
typed door, one continuous conversation.

Honesty rules:
- states are derived from real signals, never staged;
- no state outside the design vocabulary is ever recorded;
- the context window shows what the ledgers hold, bounded — nothing
  permanent, nothing invented.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.logger import app_logger

# Fallback only: the canonical source is design/tokens.json →
# beanie.states. These match it so a missing file degrades, never lies.
_FALLBACK_STATES: Dict[str, Dict[str, Any]] = {
    "idle": {"label": "Idle", "color": "#3B82F6", "duration_ms": 3400},
    "listening": {"label": "Listening", "color": "#10B981",
                  "duration_ms": 1200},
    "thinking": {"label": "Thinking", "color": "#F59E0B",
                 "duration_ms": 1600},
    "speaking": {"label": "Speaking", "color": "#8B5CF6",
                 "duration_ms": 1050},
    "working": {"label": "Working", "color": "#F59E0B",
                "duration_ms": 1600},
    "acting": {"label": "Acting", "color": "#38BDF8",
               "duration_ms": 2000},
    "observing": {"label": "Observing", "color": "#38BDF8",
                  "duration_ms": 2000},
    "success": {"label": "Success", "color": "#10B981",
                "duration_ms": 2000},
    "error": {"label": "Error", "color": "#EF4444", "duration_ms": 2000},
    "offline": {"label": "Offline", "color": "#334155", "duration_ms": 0},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state_vocabulary() -> Dict[str, Dict[str, Any]]:
    try:
        tokens = json.loads(
            (Path(settings.BASE_DIR) / "design" / "tokens.json").read_text(
                encoding="utf-8"))
        states = tokens["beanie"]["states"]
        if isinstance(states, dict) and states:
            return states
    except Exception as exc:
        app_logger.warning(f"Presence vocabulary fell back to defaults "
                           f"(design/tokens.json unreadable: {exc})")
    return dict(_FALLBACK_STATES)


class Presence:
    """How she is present in the conversation right now — derived from
    real signals, never staged — plus the contextual window into the
    mind."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        self.vocabulary = _load_state_vocabulary()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_presence (
                    presence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    noted_at TEXT NOT NULL,
                    state TEXT NOT NULL,
                    detail TEXT,
                    source TEXT NOT NULL
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Presence ledger unavailable: {exc}")

    # ── the state itself ─────────────────────────────────────────────────
    def note(self, state: str, detail: str = "",
             source: str = "organ") -> Dict[str, Any]:
        """Record a real transition. States outside the design vocabulary
        are refused — a presence state is never invented."""
        state = str(state or "").strip().lower()
        if state not in self.vocabulary:
            return {"success": False, "acted": False,
                    "reason": (f"'{state}' is not a presence state in the "
                               f"design vocabulary "
                               f"({len(self.vocabulary)} known states) — "
                               f"never invented")}
        row_id = None
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "INSERT INTO beanie_presence (noted_at, state, detail,"
                    " source) VALUES (?,?,?,?)",
                    (_now_iso(), state, str(detail or "")[:500],
                     str(source)[:100]))
                conn.commit()
                row_id = int(cur.lastrowid)
        except Exception as exc:
            return {"success": False, "acted": False,
                    "reason": f"presence ledger unavailable: {exc}"}
        spec = self.vocabulary[state]
        return {"success": True, "acted": False,
                "epistemic_kind": "presence",
                "presence_id": row_id, "state": state,
                "label": spec.get("label"), "color": spec.get("color"),
                "duration_ms": spec.get("duration_ms"),
                "detail": str(detail or "") or None,
                "statement": f"presence: {spec.get('label', state)}"}

    def current(self) -> Dict[str, Any]:
        """The latest real transition — or an honest idle (she never
        pretends to be busy)."""
        rows = self.history(limit=1)
        if not rows:
            spec = self.vocabulary.get("idle", {})
            return {"state": "idle", "label": spec.get("label", "Idle"),
                    "color": spec.get("color"),
                    "duration_ms": spec.get("duration_ms"),
                    "since": None, "detail": None,
                    "statement": "no activity on record — idle, honestly"}
        row = rows[0]
        spec = self.vocabulary.get(row["state"], {})
        return {"state": row["state"], "label": spec.get("label",
                                                         row["state"]),
                "color": spec.get("color"),
                "duration_ms": spec.get("duration_ms"),
                "since": row["noted_at"], "detail": row.get("detail"),
                "source": row.get("source"),
                "statement": f"presence: {spec.get('label', row['state'])}"}

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT * FROM beanie_presence ORDER BY presence_id "
                    "DESC LIMIT ?", (int(limit),))
                return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    # ── the contextual window into the mind ──────────────────────────────
    def context_window(self, limit: int = 5) -> Dict[str, Any]:
        """The complicated information exists WHEN NEEDED — every section
        bounded, every section from a real ledger, each honest when
        unavailable."""
        window: Dict[str, Any] = {}
        try:
            window["conversation"] = [
                {"modality": e.get("modality"), "summary": e.get("summary"),
                 "at": e.get("recorded_at") or e.get("at")}
                for e in self.mind.entries(limit=int(limit))]
        except Exception as exc:
            window["conversation"] = f"unavailable ({exc})"
        try:
            asks = self.mind.authority.pending_asks()
            window["open_asks"] = asks[:int(limit)]
        except Exception as exc:
            window["open_asks"] = f"unavailable ({exc})"
        try:
            window["goals"] = self.mind.motivation.goals(limit=int(limit))
        except Exception as exc:
            window["goals"] = f"unavailable ({exc})"
        try:
            window["unknowns"] = self.mind.curiosity.curiosities(
                limit=int(limit))
        except Exception as exc:
            window["unknowns"] = f"unavailable ({exc})"
        try:
            window["lessons"] = self.mind.reflection.lessons(
                limit=int(limit))
        except Exception as exc:
            window["lessons"] = f"unavailable ({exc})"
        window["policy"] = ("the complicated information exists when "
                            "needed, not permanently — voice primary, "
                            "text backup, visual UI a contextual window "
                            "into the mind")
        return window

    # ── the voice-primary door ───────────────────────────────────────────
    def voice_turn(self, text: str,
                   conversation_id: Optional[str] = None
                   ) -> Dict[str, Any]:
        """A transcript enters the ONE mind exactly like any other
        modality; the reply comes back with the presence state the
        evidence supports."""
        text = str(text or "").strip()
        if not text:
            return {"success": False, "acted": False,
                    "reason": "nothing was said"}
        self.note("listening", detail=text[:120], source="voice_turn")
        self.note("thinking", detail="processing through the door",
                  source="voice_turn")
        try:
            result = self.mind.process(text, modality="voice",
                                       conversation_id=conversation_id)
        except Exception as exc:
            self.note("error", detail=str(exc)[:200], source="voice_turn")
            return {"success": False, "acted": False,
                    "reply": "the door failed honestly — nothing was "
                             "faked",
                    "reason": str(exc), "state": "error",
                    "modality": "voice"}
        reply = ""
        if isinstance(result, dict):
            reply = str(result.get("assistant_reply") or result.get("reply")
                        or "")
        verified = result.get("goal_verified") if isinstance(result, dict) \
            else None
        if verified is True:
            state = "success"
            detail = "the verifier confirmed it"
        elif verified is False:
            state = "error"
            detail = "the verifier said it did not succeed"
        else:
            state = "idle"
            detail = "no verifier verdict — nothing claimed"
        self.note(state, detail=detail, source="voice_turn")
        return {"success": True, "acted": False,
                "epistemic_kind": "presence_voice_turn",
                "reply": reply, "state": state, "detail": detail,
                "modality": "voice",
                "goal_verified": verified if isinstance(verified, bool)
                else None}

    # ── surfaces ────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        rows = self.history(limit=10000)
        by_state: Dict[str, int] = {}
        for r in rows:
            by_state[r["state"]] = by_state.get(r["state"], 0) + 1
        return {"transitions": len(rows), "by_state": by_state,
                "current": self.current()["state"],
                "vocabulary": sorted(self.vocabulary.keys()),
                "policy": "states derived from real signals, never "
                          "staged; outside the design vocabulary nothing "
                          "is recorded; idle is honest, not a mask"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "presence", **self.stats(),
                "current": self.current(),
                "context_window": self.context_window()}
