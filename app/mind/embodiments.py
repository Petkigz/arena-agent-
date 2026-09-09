"""Embodiments — Phase 23 (Beanie AGI roadmap): desktop + Android as
embodiments of ONE mind.

"Arena Server ├──→ Desktop Beanie ── background presence
             └──→ Android Beanie ── background presence
Both are clients of the same Mind. Not two separate assistants."

The organ is the mind's own registry of its BODIES:

- a body ANNOUNCES itself (kind from the fixed vocabulary desktop /
  android / web — unknown kinds are refused, never invented) and is a
  presence point of the ONE mind, never a separate assistant;
- aliveness is DERIVED from heartbeats against a TTL — a body is active
  while it beats, silent when it stops; never assumed;
- ``broadcast_presence`` plans the same presence event for every ALIVE
  body — one mind, one message; silent bodies are skipped honestly;
- bodies PULL their queue (``events``) and ``acknowledge`` delivery —
  the transport stays whatever each client speaks (HTTP today), the
  decision stays with the mind;
- ``note_execution`` records WHICH body's hands performed an action —
  provenance, because the bodies are hands, never brains.

The device-pairing registry (``backend/api/device_routes.py``) stays
wired as the transport-level pairing layer; this organ is what each body
is TO THE MIND. The door broadcasts the settled presence state to every
alive body after a verified cycle — background presence, one continuous
conversation.

Honesty rules:
- no body outside the vocabulary is ever registered;
- aliveness comes from heartbeats, never assumption;
- silent bodies are skipped and said so, never faked deliveries;
- the same mind speaks the same words to every body.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

BODY_KINDS = ("desktop", "android", "web")
BODY_TTL_S = 60.0  # a body is alive while it beats within this window


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Embodiments:
    """The bodies of the one mind: announced, heartbeaten, broadcast to,
    and credited for what their hands do."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_bodies (
                    body_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    capabilities TEXT,
                    announced_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS
                    beanie_embodiment_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    body_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Embodiments ledger unavailable: {exc}")

    # ── announce + heartbeat ─────────────────────────────────────────────
    def announce(self, kind: str, name: str,
                 capabilities: Optional[List[str]] = None
                 ) -> Dict[str, Any]:
        """A client announces itself as a body of the ONE mind. Kinds
        outside the vocabulary are refused — never invented."""
        kind = str(kind or "").strip().lower()
        name = str(name or "").strip()
        if kind not in BODY_KINDS:
            return {"success": False, "acted": False,
                    "reason": (f"'{kind}' is not a body kind "
                               f"({', '.join(BODY_KINDS)}) — bodies are "
                               f"never invented")}
        if not name:
            return {"success": False, "acted": False,
                    "reason": "a body needs a name"}
        caps = json.dumps(sorted({str(c) for c in (capabilities or [])}))
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT body_id FROM beanie_bodies WHERE kind=? AND "
                    "name=?", (kind, name))
                row = cur.fetchone()
                if row:
                    conn.execute(
                        "UPDATE beanie_bodies SET capabilities=?,"
                        " last_seen=? WHERE body_id=?",
                        (caps, _now_iso(), row["body_id"]))
                    conn.commit()
                    body_id = int(row["body_id"])
                    reannounced = True
                else:
                    cur = conn.execute(
                        "INSERT INTO beanie_bodies (kind, name,"
                        " capabilities, announced_at, last_seen) VALUES "
                        "(?,?,?,?,?)",
                        (kind, name, caps, _now_iso(), _now_iso()))
                    conn.commit()
                    body_id = int(cur.lastrowid)
                    reannounced = False
        except Exception as exc:
            return {"success": False, "acted": False,
                    "reason": f"bodies ledger unavailable: {exc}"}
        return {"success": True, "acted": False,
                "epistemic_kind": "embodiment",
                "body_id": body_id, "kind": kind, "name": name,
                "reannounced": reannounced,
                "statement": (f"'{name}' is a {kind} body of the ONE "
                              f"mind — a presence point, not a separate "
                              f"assistant")}

    def heartbeat(self, body_id: int) -> Dict[str, Any]:
        body = self._body(int(body_id))
        if body is None:
            return {"success": False, "acted": False,
                    "reason": f"no body #{body_id} — nothing beats"}
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("UPDATE beanie_bodies SET last_seen=? WHERE "
                             "body_id=?", (_now_iso(), int(body_id)))
                conn.commit()
        except Exception as exc:
            return {"success": False, "acted": False,
                    "reason": f"heartbeat could not be recorded: {exc}"}
        return {"success": True, "acted": False, "body_id": int(body_id),
                "state": "active", "statement": "the body beats — active"}

    # ── aliveness is derived, never assumed ──────────────────────────────
    def bodies(self) -> List[Dict[str, Any]]:
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM beanie_bodies ORDER BY body_id")]
        except Exception:
            return []
        now = time.time()
        for r in rows:
            try:
                seen = datetime.fromisoformat(r["last_seen"]).timestamp()
            except Exception:
                seen = 0.0
            age = max(0.0, now - seen)
            r["age_s"] = round(age, 1)
            r["state"] = "active" if age <= BODY_TTL_S else "silent"
            try:
                r["capabilities"] = json.loads(r.get("capabilities") or "[]")
            except Exception:
                r["capabilities"] = []
        return rows

    def alive(self) -> List[Dict[str, Any]]:
        return [b for b in self.bodies() if b["state"] == "active"]

    # ── broadcast: one mind, one message ─────────────────────────────────
    def broadcast_presence(self, state: str, detail: str = ""
                           ) -> Dict[str, Any]:
        """Queue the SAME presence event for every alive body. Silent
        bodies are skipped and said so — deliveries are never faked."""
        living = self.alive()
        quiet = [b for b in self.bodies() if b["state"] != "active"]
        payload = json.dumps({"state": state, "detail": str(detail or ""),
                              "at": _now_iso()})
        planned = []
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                for b in living:
                    conn.execute(
                        "INSERT INTO beanie_embodiment_events (body_id,"
                        " kind, payload, created_at) VALUES (?,?,?,?)",
                        (b["body_id"], "presence", payload, _now_iso()))
                    planned.append({"body_id": b["body_id"],
                                    "kind": b["kind"], "name": b["name"]})
                conn.commit()
        except Exception as exc:
            return {"success": False, "acted": False,
                    "reason": f"broadcast failed honestly: {exc}"}
        if not living:
            return {"success": True, "acted": False,
                    "epistemic_kind": "embodiment_broadcast",
                    "planned": [], "skipped": [],
                    "statement": "no bodies are alive to reach — nothing "
                                 "was faked"}
        return {"success": True, "acted": True,
                "epistemic_kind": "embodiment_broadcast",
                "planned": planned,
                "skipped": [{"body_id": b["body_id"], "name": b["name"],
                              "reason": "silent — no heartbeat within the "
                                        "window"} for b in quiet],
                "statement": (f"one mind, one message: presence "
                              f"'{state}' planned for "
                              f"{len(planned)} alive bod"
                              f"{'y' if len(planned) == 1 else 'ies'}")}

    def events(self, body_id: int, include_acknowledged: bool = False
               ) -> List[Dict[str, Any]]:
        """The body's pull queue: what the mind has said to it."""
        query = ("SELECT * FROM beanie_embodiment_events WHERE body_id=?"
                 + ("" if include_acknowledged else
                    " AND acknowledged=0")
                 + " ORDER BY event_id")
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute(query,
                                                       (int(body_id),))]
        except Exception:
            return []
        for r in rows:
            try:
                r["payload"] = json.loads(r["payload"])
            except Exception:
                pass
            r["acknowledged"] = bool(r["acknowledged"])
        return rows

    def acknowledge(self, body_id: int, event_id: int) -> Dict[str, Any]:
        """A body confirms delivery — the mind's bookkeeping, not a
        claim."""
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT * FROM beanie_embodiment_events WHERE "
                    "event_id=? AND body_id=?",
                    (int(event_id), int(body_id)))
                row = cur.fetchone()
                if row is None:
                    return {"success": False, "acted": False,
                            "reason": (f"event #{event_id} was never "
                                       f"queued for body #{body_id} — "
                                       f"nothing to acknowledge")}
                conn.execute(
                    "UPDATE beanie_embodiment_events SET acknowledged=1 "
                    "WHERE event_id=?", (int(event_id),))
                conn.commit()
        except Exception as exc:
            return {"success": False, "acted": False,
                    "reason": f"acknowledge failed honestly: {exc}"}
        return {"success": True, "acted": False,
                "body_id": int(body_id), "event_id": int(event_id),
                "statement": "delivery confirmed by the body itself"}

    # ── provenance: hands, never brains ──────────────────────────────────
    def note_execution(self, body_id: int, action: str) -> Dict[str, Any]:
        """Record WHICH body's hands performed an action — the bodies are
        hands; the mind decides."""
        body = self._body(int(body_id))
        if body is None:
            return {"success": False, "acted": False,
                    "reason": f"no body #{body_id} — hands must belong to "
                              f"a known body"}
        action = str(action or "").strip()
        if not action:
            return {"success": False, "acted": False,
                    "reason": "nothing was done — nothing recorded"}
        payload = json.dumps({"action": action[:500],
                              "body": body["name"], "at": _now_iso()})
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute(
                    "INSERT INTO beanie_embodiment_events (body_id,"
                    " kind, payload, created_at) VALUES (?,?,?,?)",
                    (int(body_id), "execution", payload, _now_iso()))
                conn.commit()
        except Exception as exc:
            return {"success": False, "acted": False,
                    "reason": f"execution note failed honestly: {exc}"}
        return {"success": True, "acted": False,
                "epistemic_kind": "embodiment_provenance",
                "body_id": int(body_id), "body": body["name"],
                "action": action,
                "statement": (f"provenance recorded: {body['name']} "
                              f"({body['kind']}) performed it — hands, "
                              f"never brains")}

    # ── surfaces ────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        all_bodies = self.bodies()
        living = [b for b in all_bodies if b["state"] == "active"]
        return {"bodies": len(all_bodies), "alive": len(living),
                "by_kind": {k: sum(1 for b in all_bodies if b["kind"] == k)
                            for k in BODY_KINDS},
                "policy": "both clients of the SAME mind, never two "
                          "assistants; aliveness from heartbeats, never "
                          "assumed; silent bodies skipped honestly; the "
                          "same words to every body"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "embodiments", **self.stats(),
                "bodies": self.bodies()}

    # ── internals ────────────────────────────────────────────────────────
    def _body(self, body_id: int) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM beanie_bodies WHERE body_id=?",
                    (int(body_id),)).fetchone()
                return dict(row) if row else None
        except Exception:
            return None
