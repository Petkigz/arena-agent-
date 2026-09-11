"""Parked goals get re-checked automatically (owner live test 2026-09-08).

The owner watched goals end as "waiting_for_evidence — no background task is
running" and nothing ever happened again. That dangles. This module closes
the loop: a scheduled tick finds parked goals, and for each — up to a bounded
number of attempts — sends an automatic re-check through the NORMAL message
router, so the assistant gathers fresh evidence and the answer streams into
the conversation where the owner can see it. After the attempt budget is
spent it says so, honestly, once — it never fabricates success.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

_MAX_ATTEMPTS = 3
_MIN_AGE_S = 90.0
_RECHECK_GAP_S = 120.0

_attempts: Dict[str, Dict[str, Any]] = {}
_main_loop: Optional[Any] = None


def set_main_loop(loop: Any) -> None:
    """Capture the server's main asyncio loop (called from the lifespan)."""
    global _main_loop
    _main_loop = loop


def _attempts_state(trace_id: str) -> Dict[str, Any]:
    return _attempts.setdefault(trace_id, {"count": 0, "last": 0.0, "closed": False})


def _age_seconds(created_at: Any) -> float:
    """Best-effort age of a trace row (epoch seconds or ISO string)."""
    try:
        if isinstance(created_at, (int, float)):
            return max(0.0, time.time() - float(created_at))
        text = str(created_at)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0.0  # unknown format → treat as old enough to be eligible
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return max(0.0, time.time() - dt.timestamp())
    except Exception:
        return 0.0


def collect_parked_goals(limit: int = 5) -> List[Dict[str, Any]]:
    """Parked (waiting_for_evidence) goals, newest first.

    Typed park reasons (audit 2026-09-09): only OBSERVATION_PENDING
    goals — and legacy rows predating the taxonomy — are eligible for
    evidence rechecks. NEEDS_CLARIFICATION, TARGET_AMBIGUOUS,
    CAPABILITY_UNAVAILABLE, AUTHORIZATION_REQUIRED and
    PROVIDER_UNAVAILABLE can never be fixed by re-running the chat
    cycle; replaying it for those was the live defect (looping 'Have
    you tried Task Manager?' on an unresolvable app name). They stay
    parked and visible with their reason until the owner acts.
    """
    import sqlite3

    from app.database import db
    from app.cognition.goal_lifecycle import RECHECK_ELIGIBLE_PARK_REASONS

    base_where = (
        "WHERE goal_lifecycle_state = 'waiting_for_evidence' "
        "AND user_input NOT LIKE '%(automatic re-check #%' "
        "ORDER BY created_at DESC LIMIT ?")
    with db._get_connection() as conn:
        try:
            rows = conn.execute(
                "SELECT trace_id, session_id, user_input, created_at, "
                f"COALESCE(goal_park_reason, '') FROM cognitive_traces {base_where}",
                (limit * 4,),
            ).fetchall()
        except sqlite3.OperationalError:
            # Pre-migration database: the column is added by the trace
            # store's additive migration on first persist.
            rows = [
                (*r, "") for r in conn.execute(
                    "SELECT trace_id, session_id, user_input, created_at "
                    f"FROM cognitive_traces {base_where}",
                    (limit * 4,),
                ).fetchall()
            ]
    goals: List[Dict[str, Any]] = []
    for r in rows:
        if len(goals) >= limit:
            break
        reason = r[4] or ""
        if reason not in RECHECK_ELIGIBLE_PARK_REASONS:
            app_logger.debug(
                f"Parked goal {r[0]} skipped by auto-recheck "
                f"({reason}: re-running cannot fix it)")
            continue
        goals.append({
            "trace_id": r[0],
            "conversation_id": r[1] or "desktop-chat",
            "goal": r[2] or "",
            "created_at": r[3],
        })
    return goals


def _next_due_goal(goals: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The first goal eligible for a re-check (respects budget + gaps)."""
    now = time.time()
    for goal in goals:
        state = _attempts_state(goal["trace_id"])
        if state["closed"]:
            continue
        if state["count"] >= _MAX_ATTEMPTS:
            state["closed"] = True
            _notify_give_up(goal, state)
            continue
        if now - state["last"] < _RECHECK_GAP_S:
            continue
        if _age_seconds(goal.get("created_at")) < _MIN_AGE_S:
            continue
        return goal
    return None


def _notify_give_up(goal: Dict[str, Any], state: Dict[str, Any]) -> None:
    """Honest close-out: the owner hears that it could not be verified."""
    app_logger.info(
        f"Parked goal {goal['trace_id']} closed after {_MAX_ATTEMPTS} "
        f"unverified auto-rechecks: {goal['goal'][:80]}"
    )
    _post_to_conversation(
        goal["conversation_id"],
        (
            f"Automatic re-checks could not verify \u201c{goal['goal'][:120]}\u201d "
            f"after {_MAX_ATTEMPTS} attempts, so I am stopping rather than "
            f"pretending. Tell me what you actually see and I will record "
            f"that as the answer."
        ),
    )


def _post_to_conversation(conversation_id: str, text: str) -> None:
    """Best-effort owner-visible note via the websocket manager."""
    try:
        from backend.websocket_server import ws_manager

        if _main_loop is not None and _main_loop.is_running():
            import asyncio

            asyncio.run_coroutine_threadsafe(
                ws_manager.send_to_conversation(
                    conversation_id,
                    {
                        "type": "system_note",
                        "conversation_id": conversation_id,
                        "message": text,
                    },
                ),
                _main_loop,
            )
    except Exception as exc:
        app_logger.debug(f"parked recheck notify failed: {exc}")


# ── Follow-up supersession (owner transcript 2026-09-09) ────────────────────
# 'i wanted to search something' parked as waiting_for_evidence, and the
# rechecks kept web-searching the literal word 'something' while the
# owner's follow-up ('the weather in kampala now') carried the actual
# intent in its OWN trace. When the owner follows up in a conversation
# holding an AMBIGUOUS parked goal — one whose object is a placeholder
# ('something', 'stuff', 'things') — the stale vague trace leaves the
# recheck queue as 'superseded_by_followup'; the follow-up's own trace
# carries the goal forward. Conservative by design: greetings and very
# short turns never supersede, concrete parked goals are never touched,
# recheck messages never supersede. Kill switch:
# ARENA_PARKED_SUPERSESSION=0.
_AMBIGUOUS_OBJECT_WORDS = ("something", "stuff", "things", "that thing")
_SUPERSESSION_GREETINGS = {
    "hi", "hello", "hey", "yo", "sup", "ok", "okay", "yes", "no", "thanks",
    "thank you", "good morning", "good afternoon", "good evening",
    "good night", "bye", "cool", "nice", "sure",
}


def supersede_ambiguous_parked_goals(conversation_id: str, new_text: str) -> int:
    """Close ambiguous parked goals in this conversation; return the count."""
    import os

    if os.environ.get("ARENA_PARKED_SUPERSESSION", "1") == "0":
        return 0
    text = (new_text or "").strip()
    if len(text) < 10 or "(automatic re-check #" in text.lower():
        return 0
    if text.lower().rstrip("?!. ") in _SUPERSESSION_GREETINGS:
        return 0
    superseded = 0
    try:
        from app.database import db
        from app.utils.logger import audit_logger

        with db._get_connection() as conn:
            rows = conn.execute(
                "SELECT trace_id, user_input FROM cognitive_traces "
                "WHERE goal_lifecycle_state = 'waiting_for_evidence' "
                "  AND session_id = ? "
                "  AND user_input NOT LIKE '%(automatic re-check #%'",
                (conversation_id,),
            ).fetchall()
            for trace_id, goal_text in rows:
                low = (goal_text or "").lower()
                if not any(w in low for w in _AMBIGUOUS_OBJECT_WORDS):
                    continue
                conn.execute(
                    "UPDATE cognitive_traces "
                    "SET goal_lifecycle_state = 'superseded_by_followup' "
                    "WHERE trace_id = ?",
                    (trace_id,),
                )
                superseded += 1
                audit_logger.info(
                    f"Parked goal {trace_id} ('{(goal_text or '')[:60]}') "
                    f"superseded by the owner's follow-up: '{text[:60]}'")
            if superseded:
                conn.commit()
    except Exception as exc:
        app_logger.debug(f"Parked-goal supersession check skipped: {exc}")
        return 0
    # Phase 1 Event ledger mirror: the same supersession closes the
    # ambiguous request's EVENT with a typed receipt, so the ledger and
    # the goal lifecycle can never disagree. Fail-open.
    try:
        from app.cognition.event_ledger import (
            supersede_active_ambiguous_events,
        )
        supersede_active_ambiguous_events(conversation_id, text)
    except Exception as exc:
        app_logger.debug(f"Event-ledger supersession mirror skipped: {exc}")
    return superseded


# ── Phase: follow-up resolution (owner live run 2026-09-11, 1:20-1:22 PM) ──
# The clarification round-trip was broken twice in one conversation:
#   "can you open it now" → 'it' never resolved to the iTunes named in the
#       parked goal two turns earlier — Beanie asked "what does 'it' refer
#       to?" instead;
#   "itunes" (the owner ANSWERING that question) was processed as a brand
#       new vague request — "nothing ran... say 'do it'".
# The owner's answers to Beanie's own questions must complete the parked
# request; the owner must never have to repeat themselves. Deterministic,
# narrow, fail-open; kill switch ARENA_FOLLOWUP_RESOLVE=0.

_FOLLOWUP_LAUNCH_VERB_RE = None
_PRONOUN_REQUEST_RE = None
_BARE_ANSWER_MAX_WORDS = 4


def _followup_regexes():
    global _FOLLOWUP_LAUNCH_VERB_RE, _PRONOUN_REQUEST_RE
    if _FOLLOWUP_LAUNCH_VERB_RE is None:
        import re
        _FOLLOWUP_LAUNCH_VERB_RE = re.compile(r"\b(?:open|launch|start|run)\b", re.I)
        _PRONOUN_REQUEST_RE = re.compile(
            r"\b(open|launch|start|run)\s+(it|that|this|them)\b", re.I)
    return _FOLLOWUP_LAUNCH_VERB_RE, _PRONOUN_REQUEST_RE


def _recent_waiting_goals(conversation_id: str, limit: int = 5) -> List[str]:
    from app.database import db
    with db._get_connection() as conn:
        rows = conn.execute(
            "SELECT user_input FROM cognitive_traces "
            "WHERE session_id = ? "
            "  AND goal_lifecycle_state = 'waiting_for_evidence' "
            "  AND user_input NOT LIKE '%(automatic re-check #%' "
            "ORDER BY created_at DESC LIMIT ?",
            (conversation_id, int(limit)),
        ).fetchall()
    return [r[0] or "" for r in rows]


def resolve_followup_request(conversation_id: str, text: str) -> str:
    """Bind the owner's short follow-up to the parked request it answers.

    Two deterministic cases (both from the owner's live transcript):
      * BARE-NAME ANSWER: "itunes" after Beanie asked which app — when the
        most recent parked goal in this conversation is launch-shaped, the
        answer becomes "open itunes".
      * PRONOUN REQUEST: "can you open it now" — the pronoun takes the app
        target of the most recent parked goal that HAS one ("open it
        itunes on my pc" → 'itunes'), so interpretation sees the real name.

    Anything ambiguous stays verbatim: guessing wrong here would violate
    the very contract this fixes. Fail-open.
    """
    try:
        import os
        if os.environ.get("ARENA_FOLLOWUP_RESOLVE", "1") == "0":
            return text
        t = str(text or "").strip()
        if not t or t.endswith("?") or len(t.split()) > 12:
            return text
        verb_re, pronoun_re = _followup_regexes()
        goals = _recent_waiting_goals(conversation_id)
        if not goals:
            return text

        from app.agents.master_agent import extract_app_query
        from app.utils.logger import audit_logger

        # Case B first: an explicit pronoun request ("open it now").
        m = pronoun_re.search(t)
        if m:
            for goal in goals:
                target = extract_app_query(goal)
                if target:  # pronoun-only goals extract to '' — keep looking
                    new_text = t[:m.start()] + f"{m.group(1)} {target}" + t[m.end():]
                    audit_logger.info(
                        f"Follow-up resolve: pronoun in '{t[:40]}' bound to "
                        f"'{target}' from parked goal '{goal[:40]}'")
                    return new_text.strip()
            return text

        # Case A: a bare-name answer to our own clarification question.
        if (len(t.split()) <= _BARE_ANSWER_MAX_WORDS
                and not verb_re.search(t)
                and not t.lower().rstrip("?!. ") in _SUPERSESSION_GREETINGS):
            for goal in goals:
                if verb_re.search(goal):
                    new_text = f"open {t}"
                    audit_logger.info(
                        f"Follow-up resolve: bare answer '{t[:40]}' completes "
                        f"parked launch goal '{goal[:40]}' -> '{new_text}'")
                    return new_text
            return text
        return text
    except Exception as exc:
        app_logger.debug(f"Follow-up resolution skipped: {exc}")
        return str(text or "")


_MARKER_RE = None


def _strip_recheck_markers(text: str) -> str:
    """Remove accumulated '(automatic re-check #N)' prefixes.

    Owner live test 2026-09-08: each chained recheck prepended another
    marker to the goal text, producing '(automatic re-check #1) (automatic
    re-check #1) ...' eight levels deep in the chat.
    """
    import re

    return re.sub(r"\(automatic re-check #\d+\)\s*", "", str(text or "")).strip()


def _probe_launch_goal(clean_goal: str) -> Optional[Dict[str, Any]]:
    """Cheap evidence-only probe for launch-shaped parked goals.

    Returns {"verified": bool, "detail": str} when the goal IS a launch
    request with a resolvable app name, else None (caller falls back to the
    full-cycle recheck). Process scan only — no LLM call, no re-execution,
    no filesystem walk.
    """
    try:
        from app.agents.master_agent import extract_app_query

        app_query = extract_app_query(clean_goal)
    except Exception:
        return None
    if not app_query:
        return None
    try:
        from app.tools.app_inventory import SystemAppInventory

        proc = SystemAppInventory._find_app_process(app_query)
    except Exception:
        return None
    if proc is not None:
        try:
            pname = proc.info.get("name") or ""
            pid = proc.info.get("pid") or proc.pid
        except Exception:
            pname, pid = "", None
        return {
            "verified": True,
            "detail": f"'{app_query}' is running right now "
                      f"(process {pname}, pid {pid}).",
        }
    return {"verified": False, "detail": f"No process matching '{app_query}' is running."}


def _close_goal_verified(goal: Dict[str, Any], detail: str) -> None:
    """Mark the parked trace achieved on machine evidence + tell the owner."""
    try:
        from app.database import db

        with db._get_connection() as conn:
            conn.execute(
                "UPDATE cognitive_traces SET goal_lifecycle_state = 'achieved', "
                "goal_verified = 1 WHERE trace_id = ?",
                (goal["trace_id"],),
            )
            conn.commit()
    except Exception as exc:
        app_logger.warning(f"Parked-goal close failed for {goal['trace_id']}: {exc}")
    state = _attempts_state(goal["trace_id"])
    state["closed"] = True
    app_logger.info(
        f"Parked goal {goal['trace_id']} VERIFIED by probe (no re-execution): {detail[:120]}"
    )
    _post_to_conversation(
        goal["conversation_id"],
        f"Auto re-check (evidence only, nothing was re-run): {detail} "
        f"Goal verified — closing it.",
    )


def _recheck(goal: Dict[str, Any], state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    state["count"] += 1
    state["last"] = time.time()
    app_logger.info(
        f"Parked-goal auto-recheck #{state['count']} for "
        f"{goal['trace_id']}: {goal['goal'][:80]}"
    )
    try:
        from app.utils import decision_trace

        decision_trace.record(
            "parked_recheck",
            "auto_recheck_started",
            f"attempt {state['count']} of {_MAX_ATTEMPTS}",
            trace_id=goal["trace_id"],
            conversation_id=goal["conversation_id"],
            goal=goal["goal"][:200],
        )
    except Exception:
        pass
    try:
        from backend import message_router as router_module

        router = router_module.message_router
        if router is None or _main_loop is None or not _main_loop.is_running():
            state["count"] -= 1  # not the recheck's fault; retry next tick
            return None
        import asyncio

        future = asyncio.run_coroutine_threadsafe(
            router.handle_message(
                None,
                {
                    "type": "user_message",
                    "conversation_id": goal["conversation_id"],
                    "content": (
                        f"(automatic re-check #{state['count']}) "
                        f"{_strip_recheck_markers(goal['goal'])}"
                    ),
                    "source": "auto_recheck",
                },
            ),
            _main_loop,
        )
        future.result(timeout=240)
        return {"trace_id": goal["trace_id"], "attempt": state["count"]}
    except Exception as exc:
        app_logger.warning(f"Parked-goal recheck failed for {goal['trace_id']}: {exc}")
        return None


def parked_goal_recheck_tick() -> Optional[Dict[str, Any]]:
    """Scheduler entry: re-check at most one parked goal per tick."""
    try:
        goals = collect_parked_goals(limit=5)
    except Exception as exc:
        app_logger.debug(f"Parked recheck could not list goals: {exc}")
        return None
    if not goals:
        return None
    goal = _next_due_goal(goals)
    if goal is None:
        return None

    # Evidence FIRST, re-execution LAST (owner live test 2026-09-08: each
    # recheck ran the FULL cognitive cycle and re-launched the app — six
    # Electron instances fighting over one disk cache — instead of just
    # looking). For launch-shaped goals a process scan answers it for free.
    clean_goal = _strip_recheck_markers(goal["goal"])
    probe = None
    try:
        probe = _probe_launch_goal(clean_goal)
    except Exception as exc:
        app_logger.debug(f"Parked-goal launch probe failed: {exc}")
    if probe is not None:
        state = _attempts_state(goal["trace_id"])
        if probe.get("verified"):
            state["count"] += 1  # the probe itself was the attempt
            state["last"] = time.time()
            _close_goal_verified(goal, probe["detail"])
            return {"trace_id": goal["trace_id"], "probe_closed": True}
        # Evidence says it is NOT running: close honestly WITHOUT
        # re-executing. Owner round-4 verdict: rechecks must never re-run
        # actions on their own — the request is hours old by then, and the
        # surprise re-launch IS the bug (six RICHST TV instances). The
        # owner decides whether to retry.
        state["closed"] = True
        _post_to_conversation(
            goal["conversation_id"],
            f"Auto re-check (evidence only, nothing was re-run): {probe['detail']} "
            f"I am not re-launching on my own — say \"open it\" if you want it "
            f"started, and this closes as not-verified.",
        )
        return None

    return _recheck(goal, _attempts_state(goal["trace_id"]))


def reset_for_tests() -> None:
    _attempts.clear()
