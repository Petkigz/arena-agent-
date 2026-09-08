"""Decision trace: the tiniest-detail "why" log the owner asked for.

Every consequential decision — which model was picked and why, which route a
message took, why a plan was escalated to owner approval, what the watcher
noticed — is recorded here as a structured line, both to a ring buffer (for
the /debug/decisions endpoint) and to ``<DATA_DIR>/logs/decisions.jsonl``
(greppable forever). Fail-open: tracing must never break the decision.

Enable/disable with ``ARENA_DECISION_TRACE`` (default on).
"""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

_RING_SIZE = 500
_ring: deque = deque(maxlen=_RING_SIZE)
_lock = threading.Lock()
_sequence = 0

TRACE_DISABLED = os.environ.get("ARENA_DECISION_TRACE", "1") == "0"


def _data_dir() -> Path:
    try:
        from app.config import settings

        return Path(settings.DATA_DIR)
    except Exception:
        return Path("data")


def _log_path() -> Path:
    return _data_dir() / "logs" / "decisions.jsonl"


def record(
    component: str,
    decision: str,
    reason: str,
    *,
    conversation_id: str = "",
    **details: Any,
) -> Optional[Dict[str, Any]]:
    """Record one decision: WHO decided WHAT and WHY, with the details."""
    if TRACE_DISABLED:
        return None
    global _sequence
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "seq": 0,
        "component": str(component)[:60],
        "decision": str(decision)[:200],
        "reason": str(reason)[:500],
        "conversation_id": str(conversation_id or "")[:80],
        "details": _safe(details),
    }
    try:
        with _lock:
            _sequence += 1
            entry["seq"] = _sequence
            _ring.append(entry)
        _log_path().parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with open(_log_path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        app_logger.debug(
            f"[decision:{entry['component']}] {entry['decision']} — {entry['reason']}"
        )
    except Exception as exc:  # fail-open, always
        app_logger.debug(f"decision trace failed: {exc}")
    return entry


def _safe(value: Any, depth: int = 0) -> Any:
    """JSON-safe, size-bounded view of the details."""
    if depth > 4:
        return "…"
    try:
        if value is None or isinstance(value, (bool, int, float, str)):
            text = str(value)
            return text if len(text) <= 300 else text[:300] + "…"
        if isinstance(value, dict):
            return {str(k)[:60]: _safe(v, depth + 1) for k, v in list(value.items())[:12]}
        if isinstance(value, (list, tuple, set)):
            items = list(value)[:12]
            return [_safe(v, depth + 1) for v in items]
        return str(value)[:300]
    except Exception:
        return "unserializable"


def recent(limit: int = 100, component: str = "") -> List[Dict[str, Any]]:
    """The last `limit` decisions (optionally filtered by component), newest last."""
    with _lock:
        items = list(_ring)
    if component:
        prefix = str(component)
        items = [e for e in items if e.get("component", "").startswith(prefix)]
    return items[-max(0, min(limit, _RING_SIZE)):]


def tail_file(lines: int = 200) -> List[str]:
    """The last lines of the on-disk decisions log (empty when tracing off)."""
    try:
        path = _log_path()
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as fh:
            return fh.readlines()[-max(1, min(lines, 2000)):]
    except Exception:
        return []
