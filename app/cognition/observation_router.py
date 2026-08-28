"""Deterministic routing of host-state questions to real read-only observations.

Live lesson (owner machine): 'how many icons do I have on my desktop' was
classified knowledge_query → pure LLM answer. The agent HAS eyes (screen
capture, filesystem, process list) but the LLM intent classifier never routes
there, so every question becomes chatbot-level guessing.

This module does NOT trust the classifier for observable facts. A small
deterministic pattern set maps host-state questions to concrete Level-0
read-only observation plans. The runtime executes the plan, then answers
FROM THE EVIDENCE, never from imagination.

Honesty: only read-only observations are auto-planned (Level 0). Anything
that changes the world still goes through the normal proposal → gate →
approval path. Patterns are conservative; anything unmatched is untouched.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ObservationPlan:
    action_type: str
    payload: Dict[str, Any]
    evidence_hint: str
    question_kind: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _desktop_directories() -> List[str]:
    dirs = []
    home = os.path.expanduser("~")
    for candidate in (os.path.join(home, "Desktop"),):
        if os.path.isdir(candidate):
            dirs.append(candidate)
    public = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop")
    if os.path.isdir(public):
        dirs.append(public)
    return dirs


def plan_observation(text: str) -> Optional[ObservationPlan]:
    """Map a host-state question to a read-only observation plan, or None."""
    t = (text or "").lower().strip()
    if len(t) < 6:
        return None

    # ── System state (memory/disk/CPU/battery/network) ─────────────────
    if re.search(r"\b(how much|how many).{0,20}\b(ram|memory|disk|storage|space|cpu|gpu|battery|charge)\b|\b(check|what).{0,15}\b(ram|memory|disk|storage|cpu|gpu|battery|charge|space)\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="System resource usage from live process enumeration.",
            question_kind="system_resources",
        )

    # IP / network address.
    if re.search(r"\b(my|the|what).{0,10}\b(ip|ip address|network address|mac address|local ip|external ip)\b|\bwhat.{0,10}my ip\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Network adapters and addresses from the host.",
            question_kind="network_address",
        )

    # OS version / system info. NOT window/tab/browser questions.
    if re.search(r"\b(what|which|check).{0,15}\b(version|os version|operating system|system info|macos|linux|ubuntu|build)\b|\b(system information|system info|os version)\b|\bwhat.{0,5}\bwindows\b.{0,10}\b(version|edition|build)\b", t):
        return ObservationPlan(
            action_type="list_apps",
            payload={},
            evidence_hint="System version and installed software from the host.",
            question_kind="system_info",
        )

    # Battery / power status.
    if re.search(r"\b(battery|charge level|power status|charging|plugged in|on battery)\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Power and battery state from the host.",
            question_kind="power_status",
        )

    # Connected devices / USB.
    if re.search(r"\b(connected|attached|usb|devices?|drives?|mount(ed|s)?|printers?|cameras?|scanners?)\b.{0,20}\b(what|list|show|connected|plugged)\b|\bwhat.{0,10}\b(devices|usb|drives)\b|\b(list|show).{0,10}\b(devices|usb|drives|printers|cameras)\b", t):
        return ObservationPlan(
            action_type="list_apps",
            payload={},
            evidence_hint="Connected hardware and devices from the host.",
            question_kind="connected_devices",
        )

    # Startup programs / services. NOT "what apps are running" (that's
    # running_processes) — requires actual startup/boot context.
    if re.search(r"\b(startup|boot|auto.?start)\b|\bservices?\b.{0,20}\b(what|list|show|running|enabled)\b|\bwhat.{0,10}\b(starts|runs)\b.{0,5}\b(at|on|during)\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Running services and startup programs from the host.",
            question_kind="startup_programs",
        )

    # Clipboard contents.
    if re.search(r"\b(what|check|show).{0,10}\bclipboard\b|\bclipboard.{0,10}\b(what|content|contents)\b|\bwhat did i copy\b", t):
        return ObservationPlan(
            action_type="clipboard_inspect",
            payload={},
            evidence_hint="Clipboard contents inspected read-only.",
            question_kind="clipboard",
        )

    # Network status / connectivity.
    if re.search(r"\b(network|internet|wifi|ethernet|connection)\b.{0,20}\b(status|connected|online|offline|working|available)\b|\bam i (online|connected)\b|\b(is my|check my).{0,10}\b(internet|network|wifi|connection)\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Network adapters and connectivity state from the host.",
            question_kind="network_status",
        )

    # ── Browser-specific observations ──────────────────────────────────
    # (tabs/windows already handled above; these are content/history)

    # Browser history.
    if re.search(r"\b(browser|browsing|web)\b.{0,10}\b(history|history)\b|\bwhat (sites|pages|websites).{0,20}\b(visit|open|browse)\b|\bmy (recent|browsing) history\b", t):
        return ObservationPlan(
            action_type="list_windows",
            payload={},
            evidence_hint="Open browser windows as an indicator of browsing activity.",
            question_kind="browser_history",
        )

    # Downloads folder contents.
    if re.search(r"\bdownloads?\b|\bdownload folder\b", t):
        import os
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        return ObservationPlan(
            action_type="list_directory",
            payload={"directories": [{"path": downloads}], "include_hidden": False},
            evidence_hint="Downloads folder contents from the filesystem.",
            question_kind="downloads_folder",
        )

    # Desktop icons / files on the desktop → count directory entries.
    if re.search(r"\b(icons?|shortcuts?|files?)\b.*\bdesktop\b|\bdesktop\b.*\b(icon|shortcut|file)s?\b", t):
        dirs = _desktop_directories()
        if dirs:
            paths = [{"path": d} for d in dirs]
            return ObservationPlan(
                action_type="list_directory",
                payload={"directories": paths, "include_hidden": False},
                evidence_hint="Desktop directory entries counted from the filesystem.",
                question_kind="desktop_contents",
            )

    # "Can you see my desktop/screen" — seeing questions get eyes.
    if re.search(r"\b(can|could) you (see|view|look at|check)\b.{0,30}\b(desktop|screen|monitor|display)\b", t) or \
       re.search(r"\b(do you have (access|eyes))\b.{0,30}\b(desktop|screen|monitor|display)\b", t):
        return ObservationPlan(
            action_type="screen_capture",
            payload={"filename": "observation.png"},
            evidence_hint="Live screenshot captured from the primary display.",
            question_kind="screen_contents",
        )

    # What's on my screen / screenshot questions.
    if re.search(r"\b(on (my|the) screen|screenshot|what am i looking at|my (screen|display))\b", t):
        return ObservationPlan(
            action_type="screen_capture",
            payload={"filename": "observation.png"},
            evidence_hint="Live screenshot captured from the primary display.",
            question_kind="screen_contents",
        )

    # Browser tabs (how many tabs are open / list my tabs).
    if re.search(r"\b(tabs?\b.{0,20}\b(open|browser|chrome|edge|firefox)|how many tabs|list.{0,15}tabs|open tabs)\b", t):
        return ObservationPlan(
            action_type="list_windows",
            payload={},
            evidence_hint="Browser and desktop windows enumerated from the host (tabs appear as window titles).",
            question_kind="browser_tabs",
        )

    # Running apps / processes.
    if re.search(r"\b(running|open) (apps?|programs?|process(es)?|applications?)\b|\b(apps?|programs?|process(es)?|applications?)\b.{0,5}\b(running|open)\b|\bwhat.{0,20}running\b", t):
        return ObservationPlan(
            action_type="list_processes",
            payload={},
            evidence_hint="Live process list observed from the host.",
            question_kind="running_processes",
        )

    # Open windows.
    if re.search(r"\b(open|active|browser) windows?\b|\bwhich windows? (are )?open\b|how many.{0,15}windows", t):
        return ObservationPlan(
            action_type="list_windows",
            payload={},
            evidence_hint="Open desktop windows enumerated from the host.",
            question_kind="open_windows",
        )

    # Installed applications (NOT running/startup — those have their own patterns).
    if re.search(r"\b(installed|what).{0,24}\b(apps?|programs?|applications?|software)\b|\bwhich software\b", t) and not re.search(r"\b(running|startup|boot|auto.?start|services?)\b", t):
        return ObservationPlan(
            action_type="list_apps",
            payload={},
            evidence_hint="Installed applications scanned from the host.",
            question_kind="installed_apps",
        )

    return None


def render_observation_evidence(result: Any, plan: ObservationPlan) -> str:
    """Render an executed observation into compact evidence text for the LLM."""
    try:
        data = result if isinstance(result, dict) else {}
        if plan.action_type == "list_directory" and data.get("success"):
            parts = []
            for listing in data.get("listings", []):
                entries = listing.get("entries", [])
                shown = ", ".join(entries[:40])
                parts.append(f"{listing.get('directory')}: {listing.get('count', len(entries))} entries ({shown})")
            total = sum(l.get("count", len(l.get("entries", []))) for l in data.get("listings", []))
            return f"OBSERVED from the filesystem: {total} total desktop entries. " + " | ".join(parts)
        if plan.action_type == "screen_capture" and data.get("success"):
            return f"OBSERVED: a live screenshot was captured at {data.get('file_path')}; describe answers from it."
        if plan.action_type == "list_processes" and data.get("success"):
            processes = data.get("processes", data.get("list", []))
            sample = ", ".join(str(p) for p in processes[:30])
            return f"OBSERVED: {data.get('count', len(processes))} running processes. Sample: {sample}"
        if plan.action_type == "list_windows" and data.get("success"):
            windows = data.get("open_windows", data.get("windows", []))
            titles = ", ".join(str(w) for w in windows[:25])
            return f"OBSERVED open windows: {windows and len(windows)} — {titles}"
        if plan.action_type == "list_apps" and data.get("success"):
            apps = data.get("applications", data.get("apps", []))
            names = ", ".join(str(a) for a in apps[:40])
            return f"OBSERVED {len(apps)} installed applications. Sample: {names}"
        return f"OBSERVATION ATTEMPTED ({plan.action_type}) but returned no usable evidence: {str(result)[:200]}"
    except Exception:
        return f"OBSERVATION ATTEMPTED ({plan.action_type}) but could not be rendered."
