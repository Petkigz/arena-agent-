"""Phase 1 — the typed Event ledger: the request spine.

Every owner request gets exactly ONE event id, and the machine can always
answer "what happened to that request" from typed states and receipts
instead of re-reading chat vibes. This is the structural fix for the
whole bug class the owner's live rounds exposed: the derail, the
fabricated completion claim, the lost clarification — all were "the
machine lost track of what it had done or been told".

States (typed, one-way):

    new -> dispatched -> observation_pending
                              |
    new/dispatched -----------+--> verified_success
                               +-> verified_failure
                               +-> superseded
                               +-> abandoned
                               +-> expired

Receipts are first-class and append-only: dispatch, cycle_result
(trace link + verdict), supersession, expiry. A receipt records only
what the machine observed — never a claim.

Design rules (owner standing directives):
  * one event id per request — a retried/duplicated message inside the
    dedupe window binds to the SAME event, never opens a second;
  * fail-open everywhere — the ledger observes cognition, it never
    blocks or fails a request;
  * kill switch ARENA_EVENT_LEDGER=0 silences every entry point;
  * legacy traces are backfilled with source='legacy_backfill' and an
    empty park reason recorded as 'legacy_unspecified' — history is
    labeled, never rewritten.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

# ── typed state machine ────────────────────────────────────────────────────
STATE_NEW = "new"
STATE_DISPATCHED = "dispatched"
STATE_OBSERVATION_PENDING = "observation_pending"
STATE_VERIFIED_SUCCESS = "verified_success"
STATE_VERIFIED_FAILURE = "verified_failure"
STATE_SUPERSEDED = "superseded"
STATE_ABANDONED = "abandoned"
STATE_EXPIRED = "expired"

ACTIVE_STATES = (STATE_NEW, STATE_DISPATCHED, STATE_OBSERVATION_PENDING)
TERMINAL_STATES = (
    STATE_VERIFIED_SUCCESS,
    STATE_VERIFIED_FAILURE,
    STATE_SUPERSEDED,
    STATE_ABANDONED,
    STATE_EXPIRED,
)

VALID_TRANSITIONS: Dict[str, frozenset] = {
    # A request observed only at its terminal seam (engine handled it
    # without a visible dispatch step) still gets an honest typed state —
    # the receipt records that dispatch was unobserved.
    STATE_NEW: frozenset({
        STATE_DISPATCHED, STATE_OBSERVATION_PENDING, STATE_VERIFIED_SUCCESS,
        STATE_VERIFIED_FAILURE, STATE_SUPERSEDED, STATE_ABANDONED,
        STATE_EXPIRED,
    }),
    STATE_DISPATCHED: frozenset({
        STATE_OBSERVATION_PENDING, STATE_VERIFIED_SUCCESS,
        STATE_VERIFIED_FAILURE, STATE_SUPERSEDED, STATE_ABANDONED,
        STATE_EXPIRED,
    }),
    STATE_OBSERVATION_PENDING: frozenset({
        STATE_VERIFIED_SUCCESS, STATE_VERIFIED_FAILURE, STATE_SUPERSEDED,
        STATE_ABANDONED, STATE_EXPIRED,
    }),
    STATE_VERIFIED_SUCCESS: frozenset(),
    STATE_VERIFIED_FAILURE: frozenset(),
    STATE_SUPERSEDED: frozenset(),
    STATE_ABANDONED: frozenset(),
    STATE_EXPIRED: frozenset(),
}

_DEDUPE_WINDOW_SECONDS = 600      # one event id per request
_EVENT_TTL_HOURS = 48             # matches the parked-goal TTL
_BACKFILL_LIMIT = 200

_WS_RE = re.compile(r"\s+")
_backfill_done = False


def _enabled() -> bool:
    return os.environ.get("ARENA_EVENT_LEDGER", "1") != "0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", str(text or "").strip().lower())


def _ensure_table() -> None:
    from app.database import db
    with db._get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cognitive_events (
                event_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                request_text TEXT NOT NULL,
                request_norm TEXT NOT NULL,
                state TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                trace_id TEXT,
                receipt_json TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'owner',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cognitive_events_conv "
            "ON cognitive_events (conversation_id, state, created_at)"
        )
        conn.commit()


def _row_to_event(row: Any) -> Dict[str, Any]:
    try:
        receipts = json.loads(row[7] or "[]")
    except Exception:
        receipts = []
    return {
        "event_id": row[0],
        "conversation_id": row[1],
        "request_text": row[2],
        "request_norm": row[3],
        "state": row[4],
        "reason": row[5],
        "trace_id": row[6],
        "receipts": receipts,
        "source": row[8],
        "created_at": row[9],
        "updated_at": row[10],
    }


_SELECT_COLS = (
    "event_id, conversation_id, request_text, request_norm, state, "
    "reason, trace_id, receipt_json, source, created_at, updated_at"
)


def get_event(event_id: str) -> Optional[Dict[str, Any]]:
    if not _enabled() or not event_id:
        return None
    try:
        _ensure_table()
        from app.database import db
        with db._get_connection() as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM cognitive_events WHERE event_id = ?",
                (str(event_id),),
            ).fetchone()
        return _row_to_event(row) if row else None
    except Exception as exc:
        app_logger.debug(f"Event ledger read skipped: {exc}")
        return None


def expire_stale_events(ttl_hours: int = _EVENT_TTL_HOURS) -> int:
    """Active events older than the TTL are expired, with a receipt."""
    if not _enabled():
        return 0
    expired = 0
    try:
        _ensure_table()
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=int(ttl_hours))
        ).isoformat()
        from app.database import db
        with db._get_connection() as conn:
            rows = conn.execute(
                "SELECT event_id FROM cognitive_events "
                "WHERE state IN (?, ?, ?) AND created_at < ?",
                (*ACTIVE_STATES, cutoff),
            ).fetchall()
            ids = [r[0] for r in rows]
        for event_id in ids:
            if transition_event(
                event_id, STATE_EXPIRED,
                reason=f"no resolution within {int(ttl_hours)}h",
                receipt={"kind": "expired",
                         "detail": f"older than {int(ttl_hours)}h"},
            ):
                expired += 1
    except Exception as exc:
        app_logger.debug(f"Event expiry sweep skipped: {exc}")
    return expired


def open_event(
    conversation_id: str,
    request_text: str,
    source: str = "owner",
) -> Optional[str]:
    """Open (or re-bind) the ONE event for this request.

    The same normalized request inside the dedupe window in the same
    conversation returns the existing active event id — retries and
    duplicate deliveries never mint a second identity for one request.
    """
    if not _enabled():
        return None
    text = str(request_text or "").strip()
    if not text or not conversation_id:
        return None
    try:
        _ensure_table()
        expire_stale_events()
        norm = _norm(text)
        window_start = (
            datetime.now(timezone.utc)
            - timedelta(seconds=_DEDUPE_WINDOW_SECONDS)
        ).isoformat()
        from app.database import db
        with db._get_connection() as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM cognitive_events "
                "WHERE conversation_id = ? AND request_norm = ? "
                "  AND state IN (?, ?, ?) AND created_at >= ? "
                "ORDER BY created_at DESC LIMIT 1",
                (str(conversation_id), norm, *ACTIVE_STATES, window_start),
            ).fetchone()
            if row:
                return row[0]
            event_id = f"evt_{uuid.uuid4().hex[:12]}"
            now = _now()
            conn.execute(
                "INSERT INTO cognitive_events (event_id, conversation_id, "
                "request_text, request_norm, state, reason, receipt_json, "
                "source, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, '', '[]', ?, ?, ?)",
                (event_id, str(conversation_id), text, norm, STATE_NEW,
                 str(source), now, now),
            )
            conn.commit()
        _maybe_backfill_legacy()
        return event_id
    except Exception as exc:
        app_logger.debug(f"Event open skipped: {exc}")
        return None


def attach_receipt(
    event_id: str,
    kind: str,
    detail: str = "",
    verified: Optional[bool] = None,
) -> bool:
    """Append-only receipt: records what was observed, never a claim."""
    if not _enabled() or not event_id:
        return False
    try:
        _ensure_table()
        from app.database import db
        with db._get_connection() as conn:
            row = conn.execute(
                "SELECT receipt_json FROM cognitive_events WHERE event_id = ?",
                (str(event_id),),
            ).fetchone()
            if not row:
                return False
            try:
                receipts = json.loads(row[0] or "[]")
            except Exception:
                receipts = []
            receipts.append({
                "kind": str(kind),
                "detail": str(detail)[:200],
                "verified": verified,
                "at": _now(),
            })
            conn.execute(
                "UPDATE cognitive_events SET receipt_json = ?, updated_at = ? "
                "WHERE event_id = ?",
                (json.dumps(receipts[-50:]), _now(), str(event_id)),
            )
            conn.commit()
        return True
    except Exception as exc:
        app_logger.debug(f"Event receipt skipped: {exc}")
        return False


def transition_event(
    event_id: str,
    to_state: str,
    reason: str = "",
    receipt: Optional[Dict[str, Any]] = None,
) -> bool:
    """Typed one-way transition; anything else is refused (returns False)."""
    if not _enabled() or not event_id or to_state not in VALID_TRANSITIONS:
        return False
    try:
        _ensure_table()
        from app.database import db
        with db._get_connection() as conn:
            row = conn.execute(
                "SELECT state FROM cognitive_events WHERE event_id = ?",
                (str(event_id),),
            ).fetchone()
            if not row:
                return False
            current = str(row[0])
            if to_state not in VALID_TRANSITIONS.get(current, frozenset()):
                app_logger.debug(
                    f"Event {event_id}: refused transition "
                    f"{current} -> {to_state}")
                return False
            conn.execute(
                "UPDATE cognitive_events SET state = ?, reason = ?, "
                "updated_at = ? WHERE event_id = ?",
                (to_state, str(reason)[:200], _now(), str(event_id)),
            )
            conn.commit()
        if receipt:
            attach_receipt(
                event_id,
                str(receipt.get("kind", "transition")),
                str(receipt.get("detail", f"-> {to_state}")),
                receipt.get("verified"),
            )
        return True
    except Exception as exc:
        app_logger.debug(f"Event transition skipped: {exc}")
        return False


def find_active_event(
    conversation_id: str,
    request_text: str,
) -> Optional[Dict[str, Any]]:
    """Newest active event whose normalized request matches (re-check
    markers stripped, so a re-check finds the ORIGINAL request's event)."""
    if not _enabled():
        return None
    try:
        _ensure_table()
        from app.cognition.parked_goal_recheck import _strip_recheck_markers
        norm = _norm(_strip_recheck_markers(request_text))
        if not norm:
            return None
        from app.database import db
        with db._get_connection() as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM cognitive_events "
                "WHERE conversation_id = ? AND request_norm = ? "
                "  AND state IN (?, ?, ?) "
                "ORDER BY created_at DESC LIMIT 1",
                (str(conversation_id), norm, *ACTIVE_STATES),
            ).fetchone()
        return _row_to_event(row) if row else None
    except Exception as exc:
        app_logger.debug(f"Event lookup skipped: {exc}")
        return None


def mark_from_cycle_result(
    conversation_id: str,
    request_text: str,
    result: Dict[str, Any],
) -> Optional[str]:
    """The runtime seam: map a finished cycle's honest verdict onto the
    event. Called once per cycle from process_cognitive_cycle, which is
    also where re-checks and pipeline-crash dicts flow through."""
    if not _enabled():
        return None
    try:
        event = find_active_event(conversation_id, request_text)
        if not event:
            return None  # nothing to bind (legacy/recheck of unknown) — no-op
        event_id = str(event["event_id"])
        if not isinstance(result, dict):
            transition_event(
                event_id, STATE_ABANDONED,
                reason="cycle returned no structured result",
                receipt={"kind": "cycle_result",
                         "detail": "non-dict result"}, verified=False)
            return event_id

        state = str(result.get("goal_lifecycle_state") or "")
        guard = str(result.get("announcement_guard") or "")
        goal_verified = bool(result.get("goal_verified", False))
        trace_id = str(result.get("trace_id") or "") or None

        if trace_id:
            from app.database import db
            with db._get_connection() as conn:
                conn.execute(
                    "UPDATE cognitive_events SET trace_id = ?, updated_at = ? "
                    "WHERE event_id = ? AND trace_id IS NULL",
                    (trace_id, _now(), event_id))
                conn.commit()

        receipt = {
            "kind": "cycle_result",
            "detail": (f"lifecycle={state or 'legacy'} "
                       f"guard={guard or '-'} trace={trace_id or '-'}"),
            "verified": goal_verified,
        }
        if state == "failed":
            # The pipeline bridge's honest crash dict.
            to_state = STATE_ABANDONED
            reason = str(result.get("reason") or "runtime failed")
        elif guard:
            # The honesty guard fired: the cycle did NOT honestly fulfill
            # the request, whatever else the reply says.
            to_state = STATE_VERIFIED_FAILURE
            reason = f"completion-honesty guard: {guard}"
        elif state == "waiting_for_evidence":
            to_state = STATE_OBSERVATION_PENDING
            reason = "parked awaiting evidence"
        elif state == "achieved":
            to_state = STATE_VERIFIED_SUCCESS if goal_verified \
                else STATE_VERIFIED_FAILURE
            reason = "goal achieved" if goal_verified \
                else "achieved state without verification"
        elif state == "superseded":
            to_state = STATE_SUPERSEDED
            reason = "superseded during cycle"
        elif state == "deferred":
            to_state = STATE_OBSERVATION_PENDING
            reason = "deferred — still open"
        else:
            # Legacy '' / plain answer cycles: the answer was delivered;
            # the verdict follows the recorded verification flag.
            to_state = STATE_VERIFIED_SUCCESS if goal_verified \
                else STATE_VERIFIED_FAILURE
            reason = "delivered without a typed lifecycle state"
        transition_event(event_id, to_state, reason=reason, receipt=receipt)
        return event_id
    except Exception as exc:
        app_logger.debug(f"Event cycle-result mark skipped: {exc}")
        return None


def supersede_active_ambiguous_events(
    conversation_id: str,
    new_request: str,
) -> int:
    """Mirror of supersede_ambiguous_parked_goals for the ledger: active
    events for AMBIGUOUS requests are superseded by the substantive
    follow-up, with a receipt naming it."""
    if not _enabled():
        return 0
    superseded = 0
    try:
        _ensure_table()
        from app.cognition.parked_goal_recheck import _AMBIGUOUS_OBJECT_WORDS
        from app.database import db
        with db._get_connection() as conn:
            rows = conn.execute(
                f"SELECT event_id, request_text FROM cognitive_events "
                "WHERE conversation_id = ? AND state IN (?, ?, ?)",
                (str(conversation_id), *ACTIVE_STATES),
            ).fetchall()
            targets = [
                (r[0], r[1]) for r in rows
                if any(w in str(r[1]).lower() for w in _AMBIGUOUS_OBJECT_WORDS)
            ]
        for event_id, _request in targets:
            if transition_event(
                event_id, STATE_SUPERSEDED,
                reason="superseded by the owner's substantive follow-up",
                receipt={"kind": "superseded",
                         "detail": str(new_request)[:80]},
            ):
                superseded += 1
        return superseded
    except Exception as exc:
        app_logger.debug(f"Event supersession skipped: {exc}")
        return 0


def _map_legacy_state(lifecycle_state: str, verified: bool) -> str:
    if lifecycle_state == "achieved":
        return STATE_VERIFIED_SUCCESS if verified else STATE_VERIFIED_FAILURE
    if lifecycle_state == "waiting_for_evidence":
        return STATE_OBSERVATION_PENDING
    if lifecycle_state == "failed":
        return STATE_ABANDONED
    if lifecycle_state == "superseded":
        return STATE_SUPERSEDED
    return STATE_VERIFIED_SUCCESS if verified else STATE_VERIFIED_FAILURE


def _maybe_backfill_legacy() -> int:
    """One-time-per-process migration: recent legacy traces become ledger
    events (source='legacy_backfill'). An EMPTY park reason is recorded
    as 'legacy_unspecified' — history is labeled, never rewritten.
    Idempotent: a trace already linked to an event is skipped."""
    global _backfill_done
    if _backfill_done or not _enabled():
        return 0
    _backfill_done = True
    created = 0
    try:
        _ensure_table()
        from app.database import db
        with db._get_connection() as conn:
            has_traces = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='cognitive_traces'").fetchone()
            if not has_traces:
                return 0
            rows = conn.execute(
                "SELECT trace_id, session_id, user_input, created_at, "
                "       goal_verified, goal_lifecycle_state, goal_park_reason "
                "FROM cognitive_traces ORDER BY created_at DESC LIMIT ?",
                (_BACKFILL_LIMIT,),
            ).fetchall()
            for trace_id, session_id, user_input, created_at, verified, \
                    lifecycle_state, park_reason in rows:
                exists = conn.execute(
                    "SELECT 1 FROM cognitive_events WHERE trace_id = ? "
                    "LIMIT 1", (str(trace_id),)).fetchone()
                if exists:
                    continue
                now = _now()
                created += 1
                conn.execute(
                    "INSERT INTO cognitive_events (event_id, conversation_id, "
                    "request_text, request_norm, state, reason, trace_id, "
                    "receipt_json, source, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'legacy_backfill', ?, ?)",
                    (f"evt_{uuid.uuid4().hex[:12]}", str(session_id or ""),
                     str(user_input or ""), _norm(user_input),
                     _map_legacy_state(str(lifecycle_state or ""),
                                       bool(verified)),
                     str(park_reason or "legacy_unspecified"),
                     str(trace_id),
                     json.dumps([{
                         "kind": "legacy_backfill",
                         "detail": "migrated from cognitive_traces",
                         "verified": bool(verified),
                         "at": now,
                     }]),
                     str(created_at or now), now))
            conn.commit()
        if created:
            app_logger.info(
                f"Event ledger backfilled {created} legacy trace(s)")
    except Exception as exc:
        app_logger.debug(f"Event ledger backfill skipped: {exc}")
    return created


def active_events(conversation_id: str) -> List[Dict[str, Any]]:
    """Introspection for tests and future owner-facing surfaces."""
    if not _enabled():
        return []
    try:
        _ensure_table()
        from app.database import db
        with db._get_connection() as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLS} FROM cognitive_events "
                "WHERE conversation_id = ? AND state IN (?, ?, ?) "
                "ORDER BY created_at DESC",
                (str(conversation_id), *ACTIVE_STATES),
            ).fetchall()
        return [_row_to_event(r) for r in rows]
    except Exception as exc:
        app_logger.debug(f"Event ledger introspection skipped: {exc}")
        return []
