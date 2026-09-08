"""Guard-refusal visibility (owner vision charter §6, raw-input item).

RawInputGuard refusals already produce typed, reasoned, retryable results
("re-observe and retry"), but the owner live test showed they die inside the
execution payload: the chat reply the owner reads never mentions the refusal,
so a refused click looks like the assistant ignoring them or silently doing
nothing.

This module is the deterministic backstop on every finished cycle: if any
executed result carries the guard's refusal markers (``refused`` + a typed
``guard_reason``), the owner's reply gets ONE plain-language note naming what
was refused, why, and the retry path. It never invents success and never
masks the guard — it surfaces it.

Refusal markers are scanned for recursively (bounded) because the refusal
dict can sit at different depths depending on the execution path (top-level
result, ``outputs.manifest_res``, per-action results, …).
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.utils.logger import app_logger

# Typed guard reasons -> plain words for the owner. Anything unmapped still
# surfaces using its raw reason string — visibility never depends on the map.
_GUARD_REASON_PLAIN: Dict[str, str] = {
    "missing_grounding": (
        "the click/typing had no verified window+process target, so nothing was "
        "sent to the screen"
    ),
    "missing_topology_digest": (
        "the action plan carried no display fingerprint, so the coordinates "
        "could not be proven current — nothing was clicked"
    ),
    "unknown_grounding": (
        "the recorded window target is gone or no longer active — nothing was "
        "clicked"
    ),
    "grounding_missing_window": (
        "the target has no window binding — the exact window must be re-bound "
        "before input is allowed"
    ),
    "process_gone": (
        "the application it was aimed at has closed — nothing was clicked"
    ),
    "executable_changed": (
        "the process behind the target window changed identity — nothing was "
        "clicked"
    ),
    "missing_fresh_observation": (
        "the target window had not been observed just before the action "
        "(observations older than a few seconds are refused) — nothing was "
        "clicked"
    ),
    "stale_observation": (
        "the target observation was too old to trust — nothing was clicked"
    ),
    "topology_changed": (
        "the display setup changed since the plan was made (monitor, "
        "resolution, or window layout) — the coordinates would land somewhere "
        "else, so nothing was clicked"
    ),
    "point_outside_display": (
        "the coordinates fall outside the verified display — nothing was "
        "clicked"
    ),
    "point_outside_window": (
        "the coordinates fall outside the verified target window — nothing "
        "was clicked"
    ),
}

_MAX_SCAN_DEPTH = 6
_MAX_DISTINCT_REASONS = 3


def _collect_guard_refusals(node: Any, depth: int, found: List[Dict[str, Any]]) -> None:
    """Recursively collect dicts carrying the guard refusal markers."""
    if depth > _MAX_SCAN_DEPTH or len(found) >= _MAX_DISTINCT_REASONS:
        return
    if isinstance(node, dict):
        refused = node.get("refused") is True
        reason = node.get("guard_reason")
        if refused and isinstance(reason, str) and reason.strip():
            found.append({"guard_reason": reason.strip(), "error": str(node.get("error") or "")})
            if len(found) >= _MAX_DISTINCT_REASONS:
                return
        for value in node.values():
            _collect_guard_refusals(value, depth + 1, found)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect_guard_refusals(item, depth + 1, found)
            if len(found) >= _MAX_DISTINCT_REASONS:
                return


def guard_retry_note(reason: str) -> str:
    """One owner-visible sentence for a typed guard refusal."""
    plain = _GUARD_REASON_PLAIN.get(reason)
    if not plain:
        plain = f"the grounding guard refused it ({reason}) — nothing touched the screen"
    return (
        f"Guard note: I did NOT complete the screen input — {plain}. "
        'The safe fix is to re-observe the desktop and retry: say "retry" and '
        "I will re-ground the target window and run it again, reporting what "
        "actually happens."
    )


def surface_guard_retry(result: Dict[str, Any]) -> Dict[str, Any]:
    """Append the guard-refusal/retry note to the owner's reply when any
    executed result was refused by a grounding guard. Deterministic; adds
    information, never removes it."""
    if not isinstance(result, dict):
        return result

    found: List[Dict[str, Any]] = []
    _collect_guard_refusals(result, 0, found)
    if not found:
        return result

    reply = str(result.get("assistant_reply") or "")
    # One note per distinct reason; skip reasons the reply already names
    # (raw reason or its spoken form: "topology_changed" ~ "topology changed").
    notes: List[str] = []
    seen: set = set()
    reply_l = reply.lower().replace("_", " ")
    for refusal in found:
        reason = refusal["guard_reason"]
        spoken = reason.lower().replace("_", " ")
        if reason in seen or spoken in reply_l:
            continue
        seen.add(reason)
        notes.append(guard_retry_note(reason))

    if not notes:
        return result

    result["assistant_reply"] = reply.rstrip() + "\n\n" + "\n\n".join(notes)
    result["guard_retry_surfaced"] = sorted(seen)
    try:
        from app.utils import decision_trace

        decision_trace.record(
            "guard_visibility",
            "refusal_surfaced",
            ",".join(sorted(seen)),
            conversation_id=str(result.get("session_id") or "")[:80],
            user_text=str(result.get("user_text") or "")[:160],
        )
    except Exception:
        pass
    app_logger.info(f"Guard-refusal visibility applied: {sorted(seen)}")
    return result
