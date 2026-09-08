"""Completion honesty guard (owner live test 2026-09-08).

The owner's log: the assistant ANNOUNCED work ("I'm proceeding with
deleting...", "I'll fetch the weather... please hold") and then either did
nothing or claimed an outcome that was never verified ("I have observed that
the neww folder has been deleted" — while the audit trail said
verified=False). This guard is the deterministic backstop on EVERY finished
cycle:

1. A reply that promises future work with NO real action executed in the
   cycle is replaced with a straight statement: nothing ran, say "do it" to
   actually run it.
2. A reply that claims success/deletion while the cycle's actions did NOT
   verify gets the real verification status appended — a claim of "done"
   can never stand alone against the machine's evidence.

It never invents success. It only removes fabricated confidence.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

ANNOUNCE_RE = re.compile(
    r"\b(i'?ll|i will|i'?m going to|i am going to|i'?m working on|i'?m looking up|"
    r"i'?m fetching|let me|please hold|give me a moment|one moment|just a moment|"
    r"i'?m checking|i'?m on it|working on it|i'?m proceeding|i see you'?re trying)\b",
    re.I,
)

CLAIMS_DONE_RE = re.compile(
    r"\b(deleted|removed|uninstalled|killed|shut(?:ting)? down|"
    r"has been (?:deleted|removed|completed)|completed successfully|done!)\b",
    re.I,
)

# An honest ASK (capability missing, question to the owner) is not a hollow
# promise — the defer path ends its reply with what it needs from the owner.
HONEST_ASK_RE = re.compile(
    r"\b(unrecognized|not recognized|no registered|not registered|"
    r"i can(?:'t|not)|i don(?:'t|) ?t have|i haven'?t|which |could you|"
    r"please (?:provide|tell|specify))|\?",
    re.I,
)

# Actions that are the reply itself — they are not "work done on the machine".
NON_ACTION_TYPES = {"formulate_answer"}


def real_executed_actions(executed_actions: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Executed actions that actually touched the world (not the reply)."""
    real: List[Dict[str, Any]] = []
    for action in executed_actions or []:
        if isinstance(action, dict) and str(action.get("action_type", "")) not in NON_ACTION_TYPES:
            real.append(action)
    return real


def enforce_completion_honesty(
    result: Dict[str, Any],
    *,
    enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """Final gate on a finished cycle's reply. Returns the (possibly
    rewritten) result dict. Deterministic; fail-open."""
    if enabled is None:
        try:
            from app.config import settings

            enabled = str(getattr(settings, "ARENA_ANNOUNCEMENT_GUARD", "1")) != "0"
        except Exception:
            enabled = True
    if not enabled:
        return result

    reply = str(result.get("assistant_reply") or "")
    if not reply.strip():
        return result

    user_text = str(result.get("user_text") or "")
    verified = bool(result.get("goal_verified"))
    executed = real_executed_actions(result.get("executed_actions"))
    lifecycle = str(result.get("goal_lifecycle_state") or "")
    guard_applied = ""

    if (
        ANNOUNCE_RE.search(reply)
        and not executed
        and not HONEST_ASK_RE.search(reply)
    ):
        # Case 1: promised future work with nothing executed at all, and the
        # reply is not itself an honest ask (defers/questions are kept).
        result["assistant_reply"] = (
            f'Straight answer: I have not actually done "{user_text[:80]}" — I only '
            "announced it, and nothing ran. I don't say \"working on it\" without "
            'doing the work. Say "do it" and I will run it now and report the '
            "verified result."
        )
        result["announcement_guard"] = "promise_without_action_replaced"
        guard_applied = "promise_without_action_replaced"
    elif executed and not verified and (
        CLAIMS_DONE_RE.search(reply) or ANNOUNCE_RE.search(reply)
    ):
        # Case 2: work ran but did NOT verify, while the reply claims
        # success or keeps announcing. The claim never stands alone.
        action_names = ", ".join(sorted({str(a.get("action_type", "action")) for a in executed}))
        verification = result.get("verification") or {}
        reason = str(verification.get("reason") or "").strip()
        if lifecycle == "failed":
            status = "FAILED — verification reports the goal was not achieved"
        else:
            status = (
                "UNVERIFIED — I could not independently confirm the result on the "
                "machine; treat any 'done' as NOT confirmed"
            )
        suffix = f"\n\nHonest status: I ran {action_names}, but the outcome is {status}."
        if reason:
            suffix += f" Verifier: {reason[:220]}"
        result["assistant_reply"] = reply.rstrip() + suffix
        guard_applied = "unverified_outcome_surfaced"

    if guard_applied:
        try:
            from app.utils import decision_trace

            decision_trace.record(
                "completion_honesty",
                "guard_applied",
                guard_applied,
                conversation_id=str(result.get("session_id") or "")[:80],
                user_text=user_text[:160],
                original_reply=reply[:200],
            )
        except Exception:
            pass
        app_logger.info(f"Completion-honesty guard applied: {guard_applied}")
    return result
