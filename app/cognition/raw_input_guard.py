"""Mandatory grounding gate for legacy raw-coordinate input actions.

Raw mouse/keyboard/hotkey events affect whatever window happens to sit under
the cursor or hold keyboard focus at execution time. Arena never emits such an
event on trust. Before any raw input is authorized, this guard re-observes the
world and refuses the action unless ALL of the following hold:

  * a persistent OS grounding identifies the exact target window and process,
  * the owning process is still alive and its executable path (when readable)
    still matches the grounded path,
  * the target window was observed immediately (observation age is bounded),
  * a freshly captured display topology still matches the SHA-256 digest the
    planner observed when the coordinates were computed, and
  * for coordinate actions, the point lies inside the grounded display and
    inside the grounded window region when one is recorded.

The guard never fabricates focus evidence: desktop OS focus is not portably
observable, so keyboard actions record ``focus_observation: 'unknown'`` and
rely on window/process grounding plus immediate re-observation instead of a
claimed focus verification.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psutil

from app.config import settings
from app.cognition.os_grounding import OSGroundingStore
from app.tools.display_topology import DisplayTopologyTool
from app.utils.logger import app_logger, audit_logger


def _refusal(reason: str, detail: str, **extra: Any) -> Dict[str, Any]:
    result = {
        "success": False,
        "refused": True,
        "guard_passed": False,
        "attempted": False,
        "guard_reason": reason,
        "error": detail,
    }
    result.update(extra)
    return result


class RawInputGuard:
    """Single authorization gate for every raw-coordinate input path."""

    store = OSGroundingStore(settings.DATA_DIR / "os_grounding.db")
    max_observation_age_seconds = 10.0

    @classmethod
    def authorize(
        cls,
        grounding_id: Optional[str],
        expected_topology_sha256: Optional[str],
        *,
        coordinate: Optional[Dict[str, int]] = None,
        fresh_observation: Optional[Dict[str, Any]] = None,
        store: Optional[OSGroundingStore] = None,
        max_observation_age_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Return guard evidence, or a typed refusal. Never executes input."""
        if not grounding_id or not isinstance(grounding_id, str):
            return _refusal(
                "missing_grounding",
                "Raw input requires an exact OS grounding ID for the target window/process.",
            )
        if not expected_topology_sha256 or not isinstance(expected_topology_sha256, str):
            return _refusal(
                "missing_topology_digest",
                "Raw input requires the display-topology SHA-256 digest observed when the action was planned.",
            )

        s = store or cls.store
        grounding = s.get(grounding_id)
        if grounding is None or grounding.status != "active":
            return _refusal("unknown_grounding", f"No active OS grounding {grounding_id!r}.", grounding_id=grounding_id)
        if not grounding.window_id:
            return _refusal(
                "grounding_missing_window",
                "Raw input requires a window binding on the grounding; re-bind the exact window first.",
                grounding_id=grounding_id,
            )

        # Immediate process re-observation.
        if not psutil.pid_exists(grounding.pid):
            return _refusal(
                "process_gone",
                f"Grounded process PID {grounding.pid} is no longer running.",
                grounding_id=grounding_id,
                pid=grounding.pid,
            )
        exe_verified: Optional[bool] = None
        try:
            live_exe = psutil.Process(grounding.pid).exe()
            if grounding.executable_path:
                exe_verified = str(live_exe) == str(grounding.executable_path)
                if exe_verified is False:
                    return _refusal(
                        "executable_changed",
                        f"Grounded executable {grounding.executable_path} no longer matches PID {grounding.pid} ({live_exe}).",
                        grounding_id=grounding_id,
                        pid=grounding.pid,
                    )
        except psutil.Error:
            exe_verified = None  # Honest: executability of the match is unknown.
        except Exception:
            exe_verified = None

        # Immediate target-window observation freshness.
        now = datetime.now(timezone.utc)
        max_age = float(max_observation_age_seconds if max_observation_age_seconds is not None else cls.max_observation_age_seconds)
        if fresh_observation is not None:
            obs_age = float(fresh_observation.get("age_seconds", -1))
            obs_evidence: List[str] = [str(e) for e in fresh_observation.get("evidence", [])]
            if not obs_evidence:
                return _refusal("missing_fresh_observation", "fresh_observation requires evidence.", grounding_id=grounding_id)
        else:
            try:
                obs_age = (now - datetime.fromisoformat(grounding.updated_at)).total_seconds()
            except ValueError:
                return _refusal("unreadable_observation_time", "Grounding updated_at is not a readable timestamp.", grounding_id=grounding_id)
            obs_evidence = [f"os_grounding:{grounding_id}"]
        if obs_age < 0 or obs_age > max_age:
            return _refusal(
                "stale_observation",
                f"Target window was observed {obs_age:.1f}s ago; raw input requires an observation newer than {max_age:.0f}s.",
                grounding_id=grounding_id,
                observation_age_seconds=round(obs_age, 3),
            )

        # Fresh display topology with digest comparison.
        topology = DisplayTopologyTool.capture()
        if not topology.get("success") or not topology.get("topology_sha256"):
            return _refusal(
                "topology_unavailable",
                f"Display topology could not be observed: {topology.get('error', 'unknown error')}",
                grounding_id=grounding_id,
            )
        fresh_digest = topology["topology_sha256"]
        if fresh_digest != expected_topology_sha256:
            return _refusal(
                "topology_changed",
                "Display topology changed between planning and execution; recompute coordinates against the new layout.",
                grounding_id=grounding_id,
                expected_topology_sha256=expected_topology_sha256,
                observed_topology_sha256=fresh_digest,
            )
        monitors = topology.get("monitors", [])

        # Coordinate containment against the freshly observed topology.
        observed_display: Optional[str] = None
        if coordinate is not None:
            try:
                px, py = int(coordinate["x"]), int(coordinate["y"])
            except (KeyError, TypeError, ValueError):
                return _refusal("invalid_coordinate", "Coordinate must be {'x': int, 'y': int}.", grounding_id=grounding_id)
            if grounding.display_id:
                monitor = next((m for m in monitors if m.get("display_id") == grounding.display_id), None)
                if monitor is None:
                    return _refusal(
                        "display_missing_from_topology",
                        f"Grounded display {grounding.display_id!r} is absent from the fresh topology.",
                        grounding_id=grounding_id,
                    )
                if not (monitor["x"] <= px < monitor["x"] + monitor["width"] and monitor["y"] <= py < monitor["y"] + monitor["height"]):
                    return _refusal(
                        "coordinate_outside_display",
                        f"Point ({px},{py}) is outside grounded display {grounding.display_id!r} ({monitor['x']},{monitor['y']},{monitor['width']}x{monitor['height']}).",
                        grounding_id=grounding_id,
                        display_id=grounding.display_id,
                    )
                observed_display = grounding.display_id
            else:
                containing = [m for m in monitors if m["x"] <= px < m["x"] + m["width"] and m["y"] <= py < m["y"] + m["height"]]
                if not containing:
                    return _refusal(
                        "coordinate_outside_all_displays",
                        f"Point ({px},{py}) is inside no observed display.",
                        grounding_id=grounding_id,
                    )
                observed_display = containing[0]["display_id"]
            region = grounding.screen_region
            if region:
                if not (region["x"] <= px < region["x"] + region["width"] and region["y"] <= py < region["y"] + region["height"]):
                    return _refusal(
                        "coordinate_outside_window_region",
                        f"Point ({px},{py}) is outside the grounded window region {region}.",
                        grounding_id=grounding_id,
                    )

        audit_logger.info(
            "RawInputGuard passed grounding=%s window=%s pid=%s topology=%s age=%.1fs",
            grounding_id, grounding.window_id, grounding.pid, fresh_digest[:12], obs_age,
        )
        return {
            "success": True,
            "guard_passed": True,
            "grounding_id": grounding_id,
            "window_id": grounding.window_id,
            "pid": grounding.pid,
            "process_alive": True,
            "executable_verified": exe_verified,
            "observation_age_seconds": round(obs_age, 3),
            "observation_evidence": obs_evidence,
            "topology_sha256": fresh_digest,
            "observed_display": observed_display,
            # Honesty: desktop focus is not portably observable; this action is
            # grounded by window/process identity, not by a claimed focus proof.
            "focus_observation": "unknown",
        }
