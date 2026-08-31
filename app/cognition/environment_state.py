"""Environment observation/reconciliation (review #3).

The invalidation contract until now is NOTIFICATION-based:
note_environment_change() bumps the environment revision and clears the
availability cache — but it only fires for changes Arena SEES (its own
package installs, registrations, owner declarations). A human running
``pip install`` in a terminal, or removing a package, sends no event:
cached availability facts stay stale until the TTL backstop (300s).

This module is the OBSERVATION half of the fix — state Arena can re-read
cheaply and honestly, without anyone notifying it:

    observed state (cheap, re-readable, no notification)
            ↓
    Environment Snapshot   (predicate -> bool)
            ↓
    fingerprint drift
            ↓
    environment revision   (the ONE invalidation contract)
            ↓
    capability availability

HONEST SCOPE — what this observer actually measures:
  the IMPORTABILITY of the pip distributions that gate the lazy tool
  modules (each entry below is the distribution a lazy ``app.tools.*``
  module hard-imports, so its presence is exactly what that module's
  availability probe observes). It does NOT observe device state,
  services, adb, or anything else; drift invisible to this snapshot
  still heals only via the TTL backstop. Adding an observer is a new
  entry in the predicate table, not an architecture change.

Fingerprints are deliberately HUMAN-READABLE (sorted ``name=0/1`` pairs,
not a hash): a drift event can state exactly which predicate moved.
"""

from typing import Callable, Dict

from app.utils.logger import app_logger

# The observation table: distribution name -> the lazy tool module(s) it
# gates. Kept in sync with the hard imports of the lazy modules declared
# in app.tools.manifest (the lazy proxies are the capabilities whose
# availability depends on these). A distribution listed here with NO
# currently-installed presence simply observes False.
OPTIONAL_DEPENDENCIES: Dict[str, str] = {
    "bs4": "app.tools.web_research",
    "pandas": "app.tools.data_analyzer, app.tools.opsec_manager",
    "youtube_transcript_api": "app.tools.youtube_learner",
    "pypdf": "app.tools.pdf_toolkit, app.tools.doc_manager",
    "pytesseract": "app.tools.ocr_reader",
    "mss": "app.tools.screen_capture",
    "docx": "app.tools.doc_manager",
}


def observe_environment() -> Dict[str, bool]:
    """Snapshot the observable environment surface: for every optional
    distribution, whether it is importable RIGHT NOW.

    importlib.util.find_spec answers without EXECUTING the module (a
    couple of path stats), so this is safe to call on the availability
    path. Any per-name failure observes as False — observation must never
    raise into the availability path.
    """
    import importlib.util

    snapshot: Dict[str, bool] = {}
    for name in OPTIONAL_DEPENDENCIES:
        try:
            snapshot[name] = importlib.util.find_spec(name) is not None
        except Exception:  # ValueError (None in sys.modules), etc.
            snapshot[name] = False
    return snapshot


def environment_fingerprint(snapshot: Dict[str, bool]) -> str:
    """Stable, human-readable fingerprint of a snapshot (sorted
    name=0/1 pairs). Deterministic across processes and runs — never a
    hash, so a drift log line can name the exact predicates that moved.
    """
    return "; ".join(
        f"{name}={'1' if snapshot.get(name) else '0'}"
        for name in sorted(snapshot)
    )


def default_environment_provider() -> Callable[[], Dict[str, bool]]:
    """The real provider (kept behind a function so tests and alternate
    deployments can inject their own through the registry constructor)."""
    return observe_environment


def log_observation_failure(exc: Exception) -> None:
    """Observation is best-effort by contract: a broken provider must
    never take the availability path down with it."""
    app_logger.warning(f"environment reconciliation observation failed: {exc}")
