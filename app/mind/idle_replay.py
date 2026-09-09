"""Idle replay — post-roadmap growth (audit item #18): dream-like
consolidation.

"When nothing is asked of her, does she replay recent experience
offline and consolidate it — the way sleep consolidates memory?"

``replay(source)`` is her quiet pass over what happened since the last
replay. It is DETERMINISTIC and reads ONLY her own ledgers — the
learning event ledger first — so nothing is invented while she
"dreams":

- NEW experiences since the last replay (a watermark kept in the replay
  ledger itself, so it survives restarts) are replayed;
- related experiences are gathered into THREADS (vocabulary overlap,
  same spirit as the learning loop's evidence gate);
- each thread is judged only by the verifier's own tally — mostly
  verified successes → STRENGTHEN, mostly verified failures → REVISIT,
  mixed or no verdict → OPEN;
- improvement gaps still open are named, not re-argued.

The door runs ``maybe_replay`` at the end of each cycle: if the gap
since the owner's previous message crossed the idle window, the replay
happens then — she dreams in the quiet BETWEEN messages, and the
consolidation is ready the moment the owner returns. Replay describes;
it never acts, never edits the record it consolidates.

Honesty rules:
- only experiences already in the ledger are replayed — never invented;
- a thread verdict reflects verified evidence only (success True /
  failure True / unknown ignored);
- nothing new is claimed: no new knowledge, no new skills — only the
  record gathered and named.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.mind.learning_loop import _terms
from app.utils.logger import app_logger

# Thread gate: two experiences belong together only when they share
# this fraction of vocabulary (same spirit as the learning loop's
# evidence gate) — loose co-occurrence does not manufacture a thread.
_THREAD_OVERLAP = 0.3
_REPLAY_LIMIT = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _idle_seconds() -> int:
    try:
        return max(0, int(float(str(getattr(
            settings, "ARENA_IDLE_REPLAY_SECONDS", "1800")))))
    except (TypeError, ValueError):
        return 1800


class IdleReplay:
    """Dream-like consolidation: replays new experiences offline,
    gathers them into threads, and names what the verifier's tally
    says. Describes; never acts, never edits the record."""

    def __init__(self, mind: Any, db_path: Optional[str] = None) -> None:
        self.mind = mind
        self.db_path = str(db_path or mind.db_path)
        self._lock = threading.RLock()
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS beanie_replays (
                    replay_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    events_reviewed INTEGER NOT NULL,
                    threads TEXT NOT NULL,
                    open_gaps TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    acted INTEGER NOT NULL DEFAULT 0
                )""")
                conn.commit()
        except Exception as exc:
            app_logger.warning(f"Idle replay ledger unavailable: {exc}")

    # ── the quiet pass ──────────────────────────────────────────────────
    def replay(self, source: str = "idle") -> Dict[str, Any]:
        """Replay everything NEW since the last replay. Deterministic;
        reads her own ledgers only."""
        watermark = self._watermark()
        fresh = self._new_events(watermark)
        threads = self._gather_threads(fresh)
        gaps = self._open_gaps()
        if fresh:
            parts = [f"replayed {len(fresh)} new experience(s)"]
            if threads:
                parts.append(
                    f"{len(threads)} thread(s) surfaced: "
                    + "; ".join(
                        f"'{t['label']}' → {t['verdict']}" for t in threads))
            else:
                parts.append("no related thread yet (each stands alone)")
            if gaps:
                top = str(gaps[0].get("content") or "")[:80]
                parts.append(f"{len(gaps)} open gap(s) still waiting "
                             f"(top: {top})")
            statement = " — ".join(parts)
        else:
            statement = ("no new experiences since the last replay — "
                         "the mind rested")
        row_id = self._record(str(source)[:100], fresh, threads, gaps,
                              statement)
        return {"success": True, "acted": False,
                "epistemic_kind": "idle_replay",
                "replay_id": row_id, "source": str(source)[:100],
                "events_reviewed": len(fresh),
                "threads": threads, "open_gaps": gaps,
                "statement": statement}

    def maybe_replay(self, last_iso: Optional[str]) -> Dict[str, Any]:
        """The door's idle gate: replay only when the quiet since the
        previous entry crossed the idle window."""
        window = _idle_seconds()
        last = _parse_iso(last_iso)
        if last is None:
            return {"replayed": False, "elapsed_seconds": None,
                    "idle_window_seconds": window,
                    "reason": "no previous entry — the idle window is "
                              "not measured yet"}
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed < window:
            return {"replayed": False, "elapsed_seconds": elapsed,
                    "idle_window_seconds": window,
                    "reason": f"{int(elapsed)}s since the last entry — "
                              f"the idle window is {window}s"}
        res = self.replay(source="idle")
        return {"replayed": True, "elapsed_seconds": elapsed,
                "idle_window_seconds": window, **res}

    def replays(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._rows(limit=int(limit))

    # ── consolidation internals (her own record only) ───────────────────
    def _watermark(self) -> Optional[datetime]:
        """The last replay's time — everything at or before it was
        already dreamed over."""
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                row = conn.execute(
                    "SELECT MAX(created_at) FROM beanie_replays"
                ).fetchone()
            if row and row[0]:
                return _parse_iso(row[0])
        except Exception:
            pass
        return None

    def _new_events(self, watermark: Optional[datetime]
                    ) -> List[Dict[str, Any]]:
        try:
            events = self.mind.learning.events(limit=_REPLAY_LIMIT)
        except Exception:
            return []
        fresh = []
        for ev in events:
            when = _parse_iso(ev.get("recorded_at"))
            if watermark is not None:
                if when is None or when <= watermark:
                    continue
            fresh.append(ev)
        fresh.sort(key=lambda e: str(e.get("recorded_at") or ""))
        return fresh

    def _gather_threads(self, events: List[Dict[str, Any]]
                        ) -> List[Dict[str, Any]]:
        """Greedy, deterministic clustering: an experience joins the
        FIRST thread it overlaps enough; otherwise it starts one. A
        thread is real only with 2+ experiences."""
        clusters: List[Dict[str, Any]] = []
        for ev in events:
            terms = set(_terms(str(ev.get("content") or "")))
            if not terms:
                continue
            placed = False
            for cl in clusters:
                shared = cl["terms"] & terms
                union = cl["terms"] | terms
                if union and len(shared) / len(union) >= _THREAD_OVERLAP:
                    cl["events"].append(ev)
                    cl["terms"] = cl["terms"] | terms
                    placed = True
                    break
            if not placed:
                clusters.append({"terms": terms, "events": [ev]})
        threads = []
        for cl in clusters:
            if len(cl["events"]) < 2:
                continue  # one experience is data, not a thread
            succ = sum(1 for e in cl["events"] if e.get("success") is True)
            fail = sum(1 for e in cl["events"] if e.get("success") is False)
            if succ > fail:
                verdict = "strengthen"
            elif fail > succ:
                verdict = "revisit"
            else:
                verdict = "open"
            counts: Dict[str, int] = {}
            for e in cl["events"]:
                for t in _terms(str(e.get("content") or "")):
                    counts[t] = counts.get(t, 0) + 1
            label = " ".join(t for t, _ in sorted(
                counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3])
            threads.append({
                "label": label,
                "events": len(cl["events"]),
                "successes": succ, "failures": fail,
                "verdict": verdict,
                "sample": str(cl["events"][-1].get("content") or "")[:120],
            })
        threads.sort(key=lambda t: (-t["events"], t["label"]))
        return threads

    def _open_gaps(self) -> List[Dict[str, Any]]:
        try:
            gaps = self.mind.improvement.detect_gaps()
        except Exception:
            return []
        out = []
        for g in gaps[:5]:
            out.append({"content": str(g.get("content") or "")[:160],
                        "verified_failures": g.get("verified_failures",
                                                   g.get("fails"))})
        return out

    # ── surfaces ────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, Any]:
        rows = self._rows(limit=10000)
        return {"replays": len(rows),
                "events_reviewed_total":
                    sum(int(r.get("events_reviewed") or 0) for r in rows),
                "threads_found_total":
                    sum(len(r.get("threads") or []) for r in rows),
                "last_replay_at": rows[0]["created_at"] if rows else None,
                "idle_window_seconds": _idle_seconds(),
                "policy": "replay reads her own ledgers only — never "
                          "invents; thread verdicts follow the "
                          "verifier's tally (strengthen / revisit / "
                          "open); she dreams between messages and "
                          "describes — never acts, never edits the "
                          "record she consolidates"}

    def snapshot(self) -> Dict[str, Any]:
        return {"organ": "idle_replay", **self.stats(),
                "stream": self.replays(limit=20)}

    # ── internals ────────────────────────────────────────────────────────
    def _record(self, source: str, fresh: List[Dict[str, Any]],
                threads: List[Dict[str, Any]], gaps: List[Dict[str, Any]],
                statement: str) -> Optional[int]:
        try:
            with self._lock, sqlite3.connect(self.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "INSERT INTO beanie_replays (created_at, source,"
                    " events_reviewed, threads, open_gaps, statement,"
                    " acted) VALUES (?,?,?,?,?,?,0)",
                    (_now_iso(), source, len(fresh),
                     json.dumps(threads, default=str)[:8000],
                     json.dumps(gaps, default=str)[:4000], statement))
                conn.commit()
                return int(cur.lastrowid)
        except Exception as exc:
            app_logger.warning(f"Idle replay record failed (non-fatal): "
                               f"{exc}")
            return None

    def _rows(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = []
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM beanie_replays ORDER BY "
                    "replay_id DESC LIMIT ?", (int(limit),))]
        except Exception:
            return []
        for r in rows:
            for key in ("threads", "open_gaps"):
                try:
                    r[key] = json.loads(r[key])
                except Exception:
                    pass
            r["acted"] = bool(r["acted"])
        return rows
