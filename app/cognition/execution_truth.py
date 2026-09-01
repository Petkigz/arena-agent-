"""Execution Truth Layer (owner review item 12 / P0 #2, 2026-09-01).

The owner's diagnosis: Arena's failures are at the INTERFACES between
cognitive layers — interpreter → matcher → planner → executor →
verifier → lifecycle. The tools exist; the layers don't consistently
agree about what actually happened. The prescription is ONE subsystem
between execution and verification that answers "What objectively
happened?" from evidence — never from the LLM's own account:

    TOOL EXECUTION
          │
    ┌──────────────────┐
    │ Execution Truth  │
    │     Layer        │
    └──────────────────┘
          │
      RESULT         — deterministic computations (the answer IS the
                       computation; the reply must restate it)
      STATE CHANGE   — durable-store rows created this cycle
                       (projects, tasks), re-read FRESH from the stores
      ARTIFACT       — files created/modified this cycle, re-stat'ed
                       on disk at collection time
          │
        VERIFY → GOAL STATE

Evidence discipline shared by all three classes (established D6/D9):

* The truth layer re-reads the AUTHORITATIVE SOURCE at collection —
  the durable store, the filesystem — never the create-call's own
  returned object and never the model's narration of the call.
* Everything is cycle-scoped (``cycle_started_at``): evidence from an
  earlier cycle can never verify a later goal.
* Absence of evidence stays absence: an empty class is recorded as
  empty (or omitted) so the verifier remains honestly UNKNOWN — it
  never fabricates a verdict in either direction.
* Classes never cross-satisfy: a file artifact is not a project row;
  a deterministic answer is not a state change.

Where the classes live:

* RESULT — produced by the observation router / ANSWER branch
  (``deterministic_answers``, D2/D8 fixes) and mirrored into the truth
  record's ``results`` field by the runtime.
* STATE CHANGE — :meth:`collect_state_changes` (consolidated from the
  item-8 runtime helper; ProjectManager / TaskManager are the
  authority).
* ARTIFACT — :meth:`extract_artifact_candidates` digs path-like values
  out of execution result payloads at the runtime's choke points;
  :meth:`collect_artifacts` re-stats them on disk at capture time.

The consumer is the GoalVerifier (``execution_truth`` key on the
observed state), which resolves artifact-creation conditions from this
record; the legacy ``creation_events`` / ``deterministic_answers`` keys
remain as backward-compatible aliases.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.logger import app_logger

__all__ = [
    "ExecutionTruth",
    "ARTIFACT_CANDIDATE_KEYS",
]

# Result-payload keys whose values are treated as candidate artifact
# paths. Deliberately narrow: only keys that mean "a file was produced
# at this path" in the tool contracts (screen_capture.file_path,
# document_generator output paths, etc.).
ARTIFACT_CANDIDATE_KEYS = frozenset({
    "file_path",
    "path",
    "output_path",
    "save_path",
    "saved_path",
    "image_path",
    "screenshot_path",
    "document_path",
    "destination",
    "result_path",
    "artifact_path",
    "backup_path",
    "output_file",
    "export_path",
})


def _looks_like_path(value: str) -> bool:
    """Cheap sanity check that a string plausibly names a file location
    (absolute path or explicit relative path) — NOT a verdict that it
    exists. Existence is decided by the disk re-stat, never here."""
    if not value or len(value) > 4096 or "\n" in value:
        return False
    candidate = value.strip()
    if not candidate:
        return False
    if "/" not in candidate and "\\" not in candidate:
        return False
    # Reject obvious free text that merely contains a slash.
    if " " in candidate:
        return False
    return True


class ExecutionTruth:
    """The one place "what objectively happened this cycle" is answered."""

    # ── STATE CHANGE ─────────────────────────────────────────────────────

    @staticmethod
    def collect_state_changes(
        runtime: Any,
        cycle_started_at: Optional[datetime] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Rows created in the durable stores during this cycle.

        Consolidated from the item-8 runtime helper (D9/D3 family): the
        durable stores (ProjectManager / TaskManager) are the authority
        — re-read FRESH here, never the create-call's own object — and
        filtered to rows created during THIS cycle so an earlier cycle's
        row can never verify a later goal.

        Unlike the legacy ``creation_events`` alias (which omits the key
        entirely when nothing was created), this always returns a dict
        so the truth record's shape is stable; emptiness is honest.
        """
        started = cycle_started_at
        if started is None:
            started = getattr(runtime, "_cycle_started_at", None)
        if started is None:
            return {"projects": [], "tasks": []}

        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)

        def _created_at(obj) -> Optional[datetime]:
            try:
                parsed = datetime.fromisoformat(
                    str(getattr(obj, "created_at", "")))
            except (ValueError, TypeError):
                return None
            # The stores mix naive UTC (TaskManager: utcnow().isoformat())
            # and timezone-aware (ProjectManager: now(timezone.utc)) —
            # normalize to aware UTC before comparing.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed

        projects_created: List[Dict[str, Any]] = []
        tasks_created: List[Dict[str, Any]] = []
        try:
            for proj in list(getattr(
                    runtime.project_manager, "_projects", {}).values()):
                created = _created_at(proj)
                if created is not None and created >= started:
                    projects_created.append({
                        "project_id": str(getattr(proj, "project_id", "")),
                        "name": str(getattr(proj, "name", ""))[:80],
                        "description": str(getattr(proj, "description", ""))[:200],
                        "milestones": len(getattr(proj, "milestones", []) or []),
                    })
        except Exception as e:
            app_logger.warning(f"Project creation evidence unavailable: {e}")
        try:
            from app.tasks import TaskManager
            for t in TaskManager.get_all_tasks():
                created = _created_at(t)
                if created is not None and created >= started:
                    tasks_created.append({
                        "task_id": str(getattr(t, "id", "")),
                        "title": str(getattr(t, "title", ""))[:120],
                    })
        except Exception as e:
            app_logger.warning(f"Task creation evidence unavailable: {e}")

        if projects_created or tasks_created:
            app_logger.info(
                f"Execution truth (state changes, this cycle): "
                f"{len(projects_created)} project(s), "
                f"{len(tasks_created)} task(s)")
        return {"projects": projects_created, "tasks": tasks_created}

    # ── ARTIFACT ─────────────────────────────────────────────────────────

    @staticmethod
    def extract_artifact_candidates(payload: Any) -> List[str]:
        """Dig path-like values out of an execution result payload.

        Only values under the artifact keys (:data:`ARTIFACT_CANDIDATE_KEYS`)
        are considered, at any dict depth (tool results nest outputs).
        These are CANDIDATES — mere claims by the execution result — and
        carry no truth until :meth:`collect_artifacts` re-stats them on
        disk. A path that doesn't exist on disk never becomes truth.
        """
        found: List[str] = []
        seen: set = set()

        def _visit(node: Any) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    if (isinstance(k, str) and k in ARTIFACT_CANDIDATE_KEYS
                            and isinstance(v, str) and _looks_like_path(v)
                            and v not in seen):
                        seen.add(v)
                        found.append(v)
                    else:
                        _visit(v)
            elif isinstance(node, (list, tuple)):
                for item in node:
                    _visit(item)

        try:
            _visit(payload)
        except Exception as e:  # never let evidence gathering break a cycle
            app_logger.warning(f"Artifact candidate extraction failed: {e}")
        return found

    @staticmethod
    def collect_artifacts(
        candidate_paths: Optional[List[str]],
        cycle_started_at: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        """Re-stat candidate paths on disk NOW; keep only real files.

        An artifact is truth iff (a) the path exists on disk at capture
        time and (b) its modification time falls inside this cycle's
        window — a file created before the cycle began is not this
        cycle's evidence, and a path that vanished (created then
        deleted, or never created) is not evidence either.
        """
        if not candidate_paths or cycle_started_at is None:
            return []
        started = cycle_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)

        artifacts: List[Dict[str, Any]] = []
        for raw in candidate_paths:
            try:
                p = Path(str(raw))
                if not p.exists() or not p.is_file():
                    continue
                stat = p.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                if mtime < started:
                    continue
                artifacts.append({
                    "path": str(p),
                    "size_bytes": int(stat.st_size),
                    "modified_at": mtime.isoformat(),
                    "exists": True,
                })
            except (OSError, ValueError, TypeError) as e:
                app_logger.debug(f"Artifact candidate not verifiable "
                                 f"on disk ({raw}): {e}")
        if artifacts:
            app_logger.info(
                f"Execution truth (artifacts, this cycle): "
                f"{len(artifacts)} disk-verified file(s)")
        return artifacts

    # ── the record the verifier consumes ─────────────────────────────────

    @staticmethod
    def build_observed_payload(
        state_changes: Optional[Dict[str, List[Dict[str, Any]]]],
        artifacts: Optional[List[Dict[str, Any]]],
        results: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Assemble the ``execution_truth`` record that rides on the
        observed state into verification.

        Provenance is declared once, honestly: STATE CHANGE came from
        the durable stores, ARTIFACT from the filesystem, RESULT from
        deterministic computation — all direct observation, none of it
        the model's account of itself.
        """
        return {
            "results": list(results or []),
            "state_changes": (
                dict(state_changes)
                if isinstance(state_changes, dict) else {}
            ),
            "artifacts": list(artifacts or []),
            "provenance": {
                "source": "durable_store+filesystem",
                "observation_type": "direct",
                "confidence": 1.0,
            },
        }
