"""Round 10 — context distillation: what leaves the window must not leave
the mind.

The runtime sees only the last ~16 messages; older turns evaporated,
which is the structural half of the owner's "I had to repeat myself"
headache (round 8 fixed the clarification case; this fixes the general
one). The distiller compresses the turns that leave the window into a
standing per-conversation digest of FACTS — what was asked, what was
done and its verified outcome, decisions, open loops — and the router
injects that digest ahead of the recent window, labeled for what it is.

Cost discipline: re-distillation happens at most every
REDISTILL_EVERY departing turns, incrementally (existing digest +
only the new departures), so the fast lane is not paid per message.

Honesty rules (owner standing directives):
  * a simulated/unavailable model produces NO digest — the machine
    never fabricates its own memory; the previous real digest stands
    and the distillation is retried later;
  * the digest is labeled as continuity context, never presented as a
    fresh claim;
  * fail-open everywhere; kill switch ARENA_CONTEXT_DISTILL=0.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

KEEP_RECENT = 16        # the window the router hands the runtime
REDISTILL_EVERY = 8     # re-distill at most every N departing turns
DIGEST_MAX_CHARS = 1600
_MIN_DEPARTING_TURNS = 4

_DIGEST_SYSTEM = (
    "You compress conversation history into a continuity digest. Output "
    "at most 10 short bullet lines of FACTS only: what the owner asked "
    "for, what was actually done and its verified outcome, decisions "
    "made, and open loops. Keep names, numbers, and file paths verbatim. "
    "Never add claims that are not in the conversation. No preamble."
)


def _enabled() -> bool:
    return os.environ.get("ARENA_CONTEXT_DISTILL", "1") != "0"


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _ensure_table() -> None:
    from app.database import db
    with db._get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS context_digests (
                conversation_id TEXT PRIMARY KEY,
                digest TEXT NOT NULL DEFAULT '',
                covered_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _real_turns(history: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
    return [
        {"role": str(m.get("role", "")), "content": str(m.get("content", ""))}
        for m in (history or [])
        if m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()
    ]


def get_digest(conversation_id: str) -> str:
    if not _enabled() or not conversation_id:
        return ""
    try:
        _ensure_table()
        from app.database import db
        with db._get_connection() as conn:
            row = conn.execute(
                "SELECT digest FROM context_digests WHERE conversation_id = ?",
                (str(conversation_id),)).fetchone()
        return str(row[0] or "") if row else ""
    except Exception as exc:
        app_logger.debug(f"Digest read skipped: {exc}")
        return ""


def _load_state(conversation_id: str):
    from app.database import db
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT digest, covered_count FROM context_digests "
            "WHERE conversation_id = ?",
            (str(conversation_id),)).fetchone()
    return (str(row[0] or ""), int(row[1] or 0)) if row else ("", 0)


def _save_state(conversation_id: str, digest: str, covered: int) -> None:
    from app.database import db
    with db._get_connection() as conn:
        conn.execute(
            "INSERT INTO context_digests (conversation_id, digest, "
            "covered_count, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET digest = ?, "
            "covered_count = ?, updated_at = ?",
            (str(conversation_id), digest, covered, _now(),
             digest, covered, _now()))
        conn.commit()


def update_digest(
    conversation_id: str,
    history: Optional[List[Dict[str, str]]],
    llm_client: Any = None,
) -> str:
    """Refresh the conversation digest from the departing turns.

    Returns the digest to inject (possibly the previous one). Cost is
    bounded: the model is only called when at least REDISTILL_EVERY new
    turns have departed since the last successful distillation.
    """
    if not _enabled() or not conversation_id:
        return ""
    try:
        _ensure_table()
        turns = _real_turns(history)
        departing = turns[:-KEEP_RECENT] if len(turns) > KEEP_RECENT else []
        previous, covered = _load_state(conversation_id)
        if len(departing) < _MIN_DEPARTING_TURNS:
            return previous
        new_turns = len(departing) - covered
        if previous and new_turns < REDISTILL_EVERY:
            return previous  # cost bound — not enough new departures yet

        if llm_client is None:
            from app.llm import llm_client as default_client
            llm_client = default_client

        fresh = departing[covered:] if previous else departing
        transcript = "\n".join(
            f"{t['role']}: {t['content'][:400]}" for t in fresh[-24:])
        seed = f"EXISTING DIGEST (update it, do not repeat it):\n{previous}\n\n" \
            if previous else ""
        response = llm_client.generate_chat_completion(
            messages=[
                {"role": "system", "content": _DIGEST_SYSTEM},
                {"role": "user", "content": f"{seed}NEW DEPARTING TURNS:\n{transcript}"},
            ],
            complexity="fast", temperature=0.2, max_tokens=500)
        if not isinstance(response, dict):
            return previous
        # A simulated provider never fabricates memory.
        if response.get("simulated") or response.get("id") == "chat-simulated":
            return previous
        text = str((response.get("choices", [{}])[0]
                    .get("message", {}).get("content", "")) or "").strip()
        if not text:
            return previous
        _save_state(conversation_id, text[:DIGEST_MAX_CHARS], len(departing))
        return text[:DIGEST_MAX_CHARS]
    except Exception as exc:
        app_logger.debug(f"Digest update skipped: {exc}")
        try:
            return get_digest(conversation_id)
        except Exception:
            return ""


def digest_message(digest: str) -> Optional[Dict[str, str]]:
    """The labeled continuity message the router injects, or None."""
    text = str(digest or "").strip()
    if not text or not _enabled():
        return None
    return {
        "role": "assistant",
        "content": (
            "(Context digest — facts from EARLIER turns of this "
            "conversation, for continuity only; not a new statement)\n"
            + text
        ),
    }
