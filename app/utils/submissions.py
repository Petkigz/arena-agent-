"""Small idempotency helpers for append-only owner measurement submissions.

IDs identify retries, not owners or authorization grants. Stores must compare
normalized payloads under the same SQLite transaction before reusing a receipt.
"""

import re
from typing import Any, Mapping, Optional
from uuid import uuid4


def submission_record_id(prefix: str, submission_id: Optional[str]) -> str:
    if submission_id is None:
        return f"{prefix}{uuid4().hex[:12]}"
    if not isinstance(submission_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", submission_id):
        raise ValueError("submission_id must contain 8–128 letters, numbers, hyphens, or underscores")
    return f"{prefix}{submission_id}"


def require_same_submission(existing: Mapping[str, Any], proposed: Mapping[str, Any]) -> None:
    """Never reuse an ID for a different trace, rating, or evaluation payload."""
    if any(existing.get(key) != value for key, value in proposed.items() if key != "created_at"):
        raise ValueError("submission_id was already used with different content; the existing record was not changed")
