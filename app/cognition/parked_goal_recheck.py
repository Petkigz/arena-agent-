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
    """Parked (waiting_for_evidence) goals, newest first."""
    from app.database import db

    with db._get_connection() as conn:
        rows = conn.execute(
            """
            SELECT trace_id, session_id, user_input, created_at
            FROM cognitive_traces
            WHERE goal_lifecycle_state = 'waiting_for_evidence'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "trace_id": r[0],
            "conversation_id": r[1] or "desktop-chat",
            "goal": r[2] or "",
            "created_at": r[3],
        }
        for r in rows
    ]


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
                        f"{goal['goal']}"
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
    return _recheck(goal, _attempts_state(goal["trace_id"]))


def reset_for_tests() -> None:
    _attempts.clear()
