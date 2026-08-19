"""Canonical source types for evidence provenance.

Replaces string-based source matching with explicit enum membership.
Each source is classified as either ADMISSIBLE (environmental probe) or
INADMISSIBLE (claim, not observation).

Phase 1: Canonical SourceType enum
Phase 2: Required ObservationType enum (no default)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class ObservationType(str, Enum):
    """
    Classification of how an observation was obtained.
    
    DIRECT: Direct OS/hardware/process perception probe (psutil, Win32 API, system inspection)
    ENVIRONMENTAL: Environmental topology sensor/probe
    SELF_REPORTED: Tool execution output claim or self-reported execution log
    INFERRED: Inferred/heuristic observation derived from other observations
    """
    DIRECT = "direct"
    ENVIRONMENTAL = "environmental"
    SELF_REPORTED = "self_reported"
    INFERRED = "inferred"


class SourceType(str, Enum):
    """
    Canonical source types for evidence provenance.
    
    ADMISSIBLE sources are environmental probes that directly observe reality.
    INADMISSIBLE sources are claims (user input, tool output, LLM, execution traces)
    that may or may not reflect reality.
    """
    
    # ── Admissible: Environmental Probes ──────────────────────────────
    # These directly observe the environment and are admissible as beliefs.
    
    OS_PROCESS_PROBE = "os_process_probe"
    FILESYSTEM_PROBE = "filesystem_probe"
    WEB_SEARCH_PROBE = "web_search_probe"
    SCREEN_CAPTURE_FILE_PROBE = "screen_capture_file_probe"
    ADB_BATTERY_PROBE = "adb_battery_probe"
    ADB_TELEPHONY_PROBE = "adb_telephony_probe"
    ADB_WINDOW_PROBE = "adb_window_probe"
    ADB_DEVICE_PROBE = "adb_device_probe"
    RUN_COMMAND_PROBE = "run_command_probe"
    DIAGNOSTIC_SYSTEM_PROBE = "diagnostic_system_probe"
    ENVIRONMENT_GROUNDING_ENGINE = "environment_grounding_engine"
    UNIVERSAL_FILESYSTEM = "universal_filesystem"
    PROCESS_INSPECTOR = "process_inspector"
    SYSTEM_PROBE = "system_probe"
    WEB_RESEARCHER = "web_researcher"
    
    # ── Inadmissible: Claims ─────────────────────────────────────────
    # These are claims about reality, not observations. They are tracked
    # as hypotheses but do not enter the environmental belief pool.
    
    USER_INPUT = "user_input"
    MASTER_AGENT = "master_agent"
    EXECUTION_RESULT = "execution_result"
    SELF_REPORTED = "self_reported"
    SYSTEM_APP_INVENTORY = "system_app_inventory"
    COGNITIVE_RUNTIME = "cognitive_runtime"
    TOOL_OUTPUT = "tool_output"  # prefix for tool:* sources
    
    # ── Legacy/Test: Inadmissible ────────────────────────────────────
    # Historical sources from tests and older code. All inadmissible.
    
    DESKTOP = "desktop"
    PROCESS = "process"
    FS = "fs"
    PROBE = "probe"
    SYSTEM = "system"
    UNKNOWN = "unknown"

    @property
    def is_admissible(self) -> bool:
        """Check if this source type is admissible as environmental evidence."""
        return self in ADMISSIBLE_SOURCES

    @classmethod
    def from_string(cls, source: str) -> SourceType:
        """
        Convert a source string to a SourceType enum value.
        
        Handles:
        - Exact matches: "os_process_probe" → OS_PROCESS_PROBE
        - Tool prefixes: "tool:health_check" → TOOL_OUTPUT
        - Unknown sources: "anything_else" → UNKNOWN
        """
        if not source:
            return cls.UNKNOWN
        
        source_lower = source.lower().strip()
        
        # Check tool: prefix
        if source_lower.startswith("tool:"):
            return cls.TOOL_OUTPUT
        
        # Check exact matches
        for member in cls:
            if member.value == source_lower:
                return member
        
        # Fallback: check if any known source is a substring
        # (conservative: if it contains an inadmissible source name, mark as unknown)
        return cls.UNKNOWN


# ── Admissibility Sets ────────────────────────────────────────────────

ADMISSIBLE_SOURCES: frozenset[SourceType] = frozenset({
    SourceType.OS_PROCESS_PROBE,
    SourceType.FILESYSTEM_PROBE,
    SourceType.WEB_SEARCH_PROBE,
    SourceType.SCREEN_CAPTURE_FILE_PROBE,
    SourceType.ADB_BATTERY_PROBE,
    SourceType.ADB_TELEPHONY_PROBE,
    SourceType.ADB_WINDOW_PROBE,
    SourceType.ADB_DEVICE_PROBE,
    SourceType.RUN_COMMAND_PROBE,
    SourceType.DIAGNOSTIC_SYSTEM_PROBE,
    SourceType.ENVIRONMENT_GROUNDING_ENGINE,
    SourceType.UNIVERSAL_FILESYSTEM,
    SourceType.PROCESS_INSPECTOR,
    SourceType.SYSTEM_PROBE,
    SourceType.WEB_RESEARCHER,
})

INADMISSIBLE_SOURCES: frozenset[SourceType] = frozenset({
    SourceType.USER_INPUT,
    SourceType.MASTER_AGENT,
    SourceType.EXECUTION_RESULT,
    SourceType.SELF_REPORTED,
    SourceType.SYSTEM_APP_INVENTORY,
    SourceType.COGNITIVE_RUNTIME,
    SourceType.TOOL_OUTPUT,
    SourceType.DESKTOP,
    SourceType.PROCESS,
    SourceType.FS,
    SourceType.PROBE,
    SourceType.SYSTEM,
    SourceType.UNKNOWN,
})


# ── Provenance Weights ────────────────────────────────────────────────

PROVENANCE_WEIGHTS: dict[SourceType, float] = {
    # High confidence: direct environmental probes
    SourceType.OS_PROCESS_PROBE: 1.0,
    SourceType.FILESYSTEM_PROBE: 1.0,
    SourceType.SCREEN_CAPTURE_FILE_PROBE: 1.0,
    SourceType.ADB_BATTERY_PROBE: 1.0,
    SourceType.ADB_TELEPHONY_PROBE: 1.0,
    SourceType.ADB_WINDOW_PROBE: 1.0,
    SourceType.ADB_DEVICE_PROBE: 0.9,
    SourceType.RUN_COMMAND_PROBE: 0.9,
    
    # Medium-high: search and diagnostic probes
    SourceType.WEB_SEARCH_PROBE: 0.9,
    SourceType.DIAGNOSTIC_SYSTEM_PROBE: 0.9,
    SourceType.WEB_RESEARCHER: 0.85,
    
    # Medium: system-level probes
    SourceType.ENVIRONMENT_GROUNDING_ENGINE: 0.85,
    SourceType.UNIVERSAL_FILESYSTEM: 0.8,
    SourceType.PROCESS_INSPECTOR: 0.8,
    SourceType.SYSTEM_PROBE: 0.8,
    
    # Low: claims and legacy sources (inadmissible, but weighted for hypothesis tracking)
    SourceType.DESKTOP: 0.7,
    SourceType.PROCESS: 0.7,
    SourceType.SYSTEM_APP_INVENTORY: 0.5,
    SourceType.TOOL_OUTPUT: 0.4,
    SourceType.EXECUTION_RESULT: 0.3,
    SourceType.SELF_REPORTED: 0.2,
    SourceType.USER_INPUT: 0.1,
    SourceType.MASTER_AGENT: 0.1,
    SourceType.COGNITIVE_RUNTIME: 0.1,
    SourceType.FS: 0.5,
    SourceType.PROBE: 0.5,
    SourceType.SYSTEM: 0.3,
    SourceType.UNKNOWN: 0.1,
}

DEFAULT_PROVENANCE_WEIGHT: float = 0.5
