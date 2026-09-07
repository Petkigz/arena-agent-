"""Response review logic for the native desktop client (GUI-free).

Mirrors the web slice (frontend/src/services/responseFeedback.ts) against the
SAME backend endpoints and stores — no parallel feedback subsystem:

- ``POST/GET /cognition/traces/{trace_id}/usefulness`` — owner usefulness
  signal (feeds the existing bounded strategy-learning path).
- ``POST/GET /benchmarks/phase1/tasks/evaluations`` — owner-recorded task
  evaluations. Measurement ONLY: this never changes runtime truth, never
  authorizes work, and never approves training.
- ``GET /self-awareness/introspection/{trace_id}`` — grounded "why this
  response" facts (trace evidence, never a model narration).

Honesty rules carried over from the web slice:

- A review control exists ONLY for a reply that carries its exact trace id.
  Older unlinked replies are intentionally unreviewable — the owner is never
  asked to guess which response they are rating.
- ``submission_id`` is a retry identity, not a credential: retries of the
  SAME submission reuse the id so a flaky network cannot inflate evidence
  counts. It stays in use until the backend returns its matching receipt.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Iterable, List, Optional

#: Exact value domains enforced by the backend models (app/main.py).
USEFULNESS_LEVELS = ("helpful", "partially_helpful", "not_helpful")
TASK_OUTCOMES = ("success", "failure", "unknown")
EVALUATION_SPLITS = ("held_out", "contract")
EVALUATION_CONDITIONS = ("single", "baseline", "adapted")

#: The backend validates submission ids with ^[A-Za-z0-9_-]+$ (8..128 chars).
#: Pre-validating the same shape client-side fails fast without a round trip.
_SUBMISSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
SUBMISSION_ID_PREFIX = "desktop"

#: The backend caps evidence_ids at 20 per evaluation.
MAX_EVIDENCE_IDS = 20


class ResponseReviewError(ValueError):
    """A local payload problem — nothing was sent to the backend."""


def new_submission_id() -> str:
    """Retry identity for one submission. Prefix keeps clients distinguishable
    in the shared store (web uses ``web-…``); it is not a credential."""
    return f"{SUBMISSION_ID_PREFIX}-{uuid.uuid4().hex}"


def reviewable_trace(trace_id: Any) -> bool:
    """True only for a non-empty trace id — unlinked replies are unreviewable."""
    return isinstance(trace_id, str) and bool(trace_id.strip())


def _validate_submission_id(submission_id: str) -> str:
    sid = (submission_id or "").strip()
    if not _SUBMISSION_ID_RE.match(sid):
        raise ResponseReviewError(
            "submission id must be 8-128 characters of letters, digits, '-' or '_'"
        )
    return sid


def build_usefulness_payload(
    usefulness: str,
    note: str = "",
    submission_id: str = "",
) -> Dict[str, Any]:
    """Payload for POST /cognition/traces/{trace_id}/usefulness."""
    level = (usefulness or "").strip()
    if level not in USEFULNESS_LEVELS:
        raise ResponseReviewError(
            f"usefulness must be one of {', '.join(USEFULNESS_LEVELS)}"
        )
    return {
        "usefulness": level,
        "note": (note or "").strip(),
        "submission_id": _validate_submission_id(submission_id),
    }


def parse_evidence_ids(text: str) -> List[str]:
    """Parse a comma/whitespace-separated evidence id field: trimmed,
    de-duplicated (order kept), capped at the backend maximum."""
    seen: List[str] = []
    for raw in re.split(r"[,\s]+", (text or "").strip()):
        token = raw.strip()
        if token and token not in seen:
            seen.append(token)
        if len(seen) >= MAX_EVIDENCE_IDS:
            break
    return seen


def build_task_evaluation_payload(
    *,
    trace_id: str,
    task_key: str,
    observed_outcome: str,
    usefulness: str = "unknown",
    split: str = "held_out",
    condition: str = "single",
    correction_received: bool = False,
    evidence_ids: Optional[Iterable[str]] = None,
    note: str = "",
    submission_id: str = "",
) -> Dict[str, Any]:
    """Payload for POST /benchmarks/phase1/tasks/evaluations (measurement only)."""
    key = (task_key or "").strip()
    if not key:
        raise ResponseReviewError("a task key is required to record an evaluation")
    outcome = (observed_outcome or "").strip()
    if outcome not in TASK_OUTCOMES:
        raise ResponseReviewError(
            f"observed outcome must be one of {', '.join(TASK_OUTCOMES)}"
        )
    level = (usefulness or "unknown").strip() or "unknown"
    if level != "unknown" and level not in USEFULNESS_LEVELS:
        raise ResponseReviewError(
            f"usefulness must be 'unknown' or one of {', '.join(USEFULNESS_LEVELS)}"
        )
    evaluated_split = (split or "held_out").strip() or "held_out"
    if evaluated_split not in EVALUATION_SPLITS:
        raise ResponseReviewError(
            f"split must be one of {', '.join(EVALUATION_SPLITS)}"
        )
    eval_condition = (condition or "single").strip() or "single"
    if eval_condition not in EVALUATION_CONDITIONS:
        raise ResponseReviewError(
            f"condition must be one of {', '.join(EVALUATION_CONDITIONS)}"
        )
    if not reviewable_trace(trace_id):
        raise ResponseReviewError("a trace id is required to record an evaluation")
    evidence = [e for e in (evidence_ids or []) if str(e).strip()][:MAX_EVIDENCE_IDS]
    return {
        "task_key": key,
        "trace_id": trace_id.strip(),
        "observed_outcome": outcome,
        "usefulness": level,
        "split": evaluated_split,
        "condition": eval_condition,
        "correction_received": bool(correction_received),
        "evidence_ids": evidence,
        "note": (note or "").strip(),
        "submission_id": _validate_submission_id(submission_id),
    }
