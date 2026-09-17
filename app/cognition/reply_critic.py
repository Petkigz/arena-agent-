"""Round 9 — the critic pass: a second pair of eyes before she speaks.

The completion-honesty guard catches LIE PATTERNS — regex-recognizable
claim phrasings ("I've confirmed...", "has been deleted..."). It cannot
catch a semantic overshoot phrased in words no regex knows. The critic
is the second defense: the FAST lane reads the draft reply against the
actual evidence of the cycle — the actions that executed and the
verifier's verdict — and flags any outcome claim the evidence does not
support. A flagged reply keeps its text (the owner sees what she was
about to be told) and gains an explicit correction suffix; the marker
lands on the result for the ledger and the UI.

Design rules (owner standing directives):
  * the critic never touches VERIFIED outcomes or replies the honesty
    guard already corrected — no double-correction, no theater;
  * it only runs when something actually executed — claim+nothing-
    executed is the honesty guard's case, not the critic's;
  * a simulated/unavailable model is NOT a critic — no-op, fail-open;
  * kill switch ARENA_REPLY_CRITIC=0.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from app.utils.logger import app_logger

_JSON_RE = re.compile(r"\{.*\}", re.S)
_MAX_EVIDENCE_ITEMS = 6

_CRITIC_SYSTEM = (
    "You are a strict evidence critic. You compare an assistant's draft "
    "reply against the ONLY evidence available: the actions that actually "
    "executed and the verifier's verdict. If the reply states an outcome "
    "as accomplished that the evidence does not support, flag it. Answer "
    'with ONLY JSON: {"exceeds": true|false, "unsupported_claim": "<the '
    'exact claim or empty>"}.'
)


def _enabled() -> bool:
    return os.environ.get("ARENA_REPLY_CRITIC", "1") != "0"


def _evidence_digest(result: Dict[str, Any]) -> str:
    lines = []
    for action in (result.get("executed_actions") or [])[:_MAX_EVIDENCE_ITEMS]:
        if isinstance(action, dict):
            detail = str(action.get("detail")
                         or action.get("action_type") or "action")
        else:
            detail = str(action)
        lines.append(f"- executed: {detail[:120]}")
    lines.append(
        f"- verifier verdict: goal_verified="
        f"{bool(result.get('goal_verified', False))}, "
        f"lifecycle_state={str(result.get('goal_lifecycle_state') or 'legacy')}")
    return "\n".join(lines)


def critique_reply(
    result: Dict[str, Any],
    llm_client: Any = None,
) -> Dict[str, Any]:
    """Critic the draft reply; returns the (possibly corrected) result.

    Fail-open and strictly scoped: anything unexpected returns the
    result unchanged. The correction is a visible suffix, never a
    silent rewrite — the owner always sees what was about to be said.
    """
    if not _enabled() or not isinstance(result, dict):
        return result
    try:
        reply = str(result.get("assistant_reply") or "").strip()
        if not reply:
            return result
        # The honesty guard already spoke: never double-correct.
        if result.get("announcement_guard"):
            return result
        # A verified outcome needs no critic; a cycle that executed
        # nothing is the honesty guard's case, not this organ's.
        if result.get("goal_verified") or not result.get("executed_actions"):
            return result

        if llm_client is None:
            from app.llm import llm_client as default_client
            llm_client = default_client

        messages = [
            {"role": "system", "content": _CRITIC_SYSTEM},
            {"role": "user", "content": (
                f"EVIDENCE:\n{_evidence_digest(result)}\n\n"
                f"DRAFT REPLY:\n{reply[:2000]}")},
        ]
        response = llm_client.generate_chat_completion(
            messages=messages, complexity="fast",
            temperature=0.1, max_tokens=160)
        if not isinstance(response, dict):
            return result
        # A simulated provider is not a critic.
        if response.get("simulated") or response.get("id") == "chat-simulated":
            return result
        raw = (response.get("choices", [{}])[0]
               .get("message", {}).get("content", ""))
        match = _JSON_RE.search(str(raw or ""))
        if not match:
            return result
        verdict = json.loads(match.group(0))
        if not isinstance(verdict, dict) or not verdict.get("exceeds"):
            return result

        claim = str(verdict.get("unsupported_claim") or "").strip()[:200]
        claim_part = f' "{claim}"' if claim else " above"
        suffix = (
            "\n\nCritic note: the claim" + claim_part +
            " is not supported by what actually executed this cycle — "
            "treat it as unconfirmed."
        )
        result = dict(result)
        result["assistant_reply"] = reply + suffix
        result["critic_correction"] = claim or "unsupported outcome claim"
        return result
    except Exception as exc:
        app_logger.debug(f"Reply critic skipped: {exc}")
        return result
