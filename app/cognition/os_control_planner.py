"""General OS control: one planner for every OS action, every platform.

THE PERMANENT FIX the owner asked for: writing one tool per OS action
(wallpaper, icon size, dark mode, ...) is an infinite treadmill — and doing
it per-platform triples the work. This module replaces the treadmill:

  The LLM PLANS the command (it knows PowerShell / defaults / gsettings).
  The deterministic layer EXECUTES it through the existing gate system and
  VERIFIES the outcome. The LLM never touches the machine directly.

Flow:
  1. plan_os_action(user_text) — the LLM is asked to emit a structured plan:
     {command, platform, description, verify_command, risk_level}
     constrained to the detected platform's shell. No free-form shell.
  2. execute_os_plan(plan) — runs through the existing ActionGate (Level 2
     for reversible, Level 3 for destructive), the cooperative-cancellation
     subprocess runner, and verify_command for evidence.
  3. The result carries the command, stdout, verify evidence — honest.

Platform shells:
  Windows: PowerShell (SystemParametersInfo, registry, Get-/Set-*)
  macOS:   defaults / osascript
  Linux:   gsettings / dbus-send

The tool_matcher routes ANY unrecognized control request containing an OS
action verb here instead of falling through to chat — one routing rule,
not one tool per action.
"""
from __future__ import annotations

import platform
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import app_logger, audit_logger

# OS action verbs: the SAME set as tool_matcher.CONTROL_VERBS so routing
# is consistent — a request that looks like control to one module looks like
# control to both. Plus OS-settings-specific additions.
# COMPREHENSIVE: superset of tool_matcher.CONTROL_VERBS plus OS-specific terms.
# The consistency test (test_intent_coverage.py) enforces that every
# tool_matcher.CONTROL_VERBS entry appears here too.
OS_ACTION_VERBS = {
    # Change/mutate
    "change", "set", "make", "modify", "adjust", "configure", "edit",
    "update", "upgrade", "reset", "restore", "revert", "toggle", "switch",
    "enable", "disable", "turn",
    # File operations
    "move", "rename", "copy", "delete", "remove", "create", "write",
    "save", "compress", "archive", "extract", "unzip", "zip",
    "upload", "download", "send", "share", "unshare",
    "encrypt", "decrypt", "backup", "burn", "print", "eject", "mount",
    "unmount",
    # App/OS operations
    "open", "close", "launch", "start", "run", "stop", "quit", "exit", "kill",
    "terminate", "restart", "reboot", "shutdown", "sleep", "hibernate",
    "wake", "lock", "unlock", "login", "logout", "logoff",
    "install", "uninstall", "repair", "force",
    # Browser operations
    "navigate", "visit", "browse", "refresh", "reload", "scroll", "zoom",
    "fill", "enter", "submit", "click", "select", "check", "uncheck",
    "hover", "bookmark",
    # Display/UI operations
    "screenshot", "capture", "record", "minimize", "maximize", "restore",
    "snap", "tile", "cascade", "arrange", "resize", "scale", "rotate",
    "extend", "duplicate", "mirror", "hide", "show", "pin", "unpin",
    "wallpaper",
    # System/network operations
    "connect", "disconnect", "pair", "unpair", "scan", "sync", "block",
    "allow", "forward", "map", "clear", "empty", "clean", "purge",
    "flush", "release", "renew",
    # Audio/media
    "play", "pause", "mute", "unmute",
    # Search/observation commands
    "search", "find", "list", "count", "check", "verify", "test",
    "analyze", "inspect", "monitor", "track",
    # Communication (NOT call/text/message — too generic)
    "notify",
    # OS-specific terms
    "volume", "brightness", "wifi", "bluetooth", "notification",
    "display", "resolution", "refresh", "power", "battery", "background",
    "theme", "dark", "light", "sign",
}

# Domains this planner handles (NOT files, browser, email, etc. — those
# have dedicated tools and routes).
OS_SETTINGS_DOMAINS = {
    "desktop", "display", "screen", "wallpaper", "background", "theme",
    "appearance", "volume", "audio", "brightness", "power", "wifi",
    "network", "bluetooth", "notification", "notifications", "icons",
    "icon", "taskbar", "dock", "keyboard", "mouse", "cursor", "font",
    "fonts", "language", "region", "timezone", "time", "date",
    "resolution", "monitor", "color", "night", "blue", "light",
    "lock", "screensaver", "sleep", "hibernate", "shutdown", "restart",
    "dark", "mode", "size", "medium", "small", "large", "default",
    "airplane", "focus", "assist", "timer", "alarm", "reminder",
    "tabs", "tab", "browser", "browsers", "chrome", "edge", "firefox",
    "window", "windows", "app", "apps", "application", "applications",
    "program", "programs", "process", "processes", "running", "clipboard",
    "tray", "startup", "services", "users", "login", "desktop",
    # Hardware/system
    "memory", "ram", "cpu", "gpu", "disk", "storage", "drive", "drives",
    "usb", "bluetooth", "wifi", "network", "ethernet", "adapter",
    "printer", "printers", "scanner", "scanners", "camera", "cameras",
    "microphone", "speakers", "headphones", "keyboard", "mouse", "touchpad",
    "battery", "power", "charger", "ac", "thermal", "fan", "temperature",
    # System info/settings
    "version", "build", "edition", "license", "activation", "update",
    "updates", "patch", "hotfix", "uptime", "boot", "firmware", "bios",
    "driver", "drivers", "device", "devices", "hardware", "system",
    # User/system state
    "password", "pin", "account", "accounts", "profile", "profiles",
    "permission", "permissions", "admin", "administrator", "sudo",
    "environment", "variables", "path", "registry", "group", "policy",
    # Network settings
    "dns", "proxy", "vpn", "firewall", "port", "ports", "host", "hosts",
    "hosts", "ip", "address", "subnet", "gateway", "route", "routes",
    # Appearance/UI
    "taskbar", "dock", "menu", "start", "sidebar", "notification",
    "notifications", "icon", "icons", "cursor", "pointer", "font",
    "fonts", "language", "region", "timezone", "time", "date",
    "locale", "format", "keyboard", "layout",
    # Browser-specific
    "bookmark", "bookmarks", "history", "cache", "cookies", "extension",
    "extensions", "plugin", "plugins", "password", "passwords",
    "download", "downloads", "homepage", "search", "engine", "proxy",
    "incognito", "private", "javascript", "popup", "popups", "adblock",
    "hidden", "visible", "associations", "extension", "mime", "protocol",
    "handler", "default", "file", "type", "folder", "directory",
}


def _is_os_control_request(text: str) -> bool:
    """Deterministic: does this message ask for an OS/settings change?"""
    t = (text or "").lower().strip()
    if len(t) < 6:
        return False
    words = set(re.findall(r"[a-z_]+", t))
    if not (words & OS_ACTION_VERBS):
        return False
    # Must also mention an OS-settings domain word.
    return bool(words & OS_SETTINGS_DOMAINS)


def _shell_for_platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "powershell"
    if system == "darwin":
        return "bash"  # defaults/osascript via bash
    return "bash"  # gsettings/dbus via bash


@dataclass
class OSActionPlan:
    """A structured, reviewable OS command plan — never free-form shell."""
    plan_id: str
    user_request: str
    command: str
    shell: str
    description: str
    verify_command: str
    risk_level: str  # "reversible" | "destructive"
    platform: str
    created_at: str = field(default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Prompt for the LLM planner ─────────────────────────────────────────────

_PLANNER_SYSTEM = """You are an OS command planner. Given the user's request and the current platform, emit ONE JSON object with EXACTLY these keys:

{{
  "command": "the exact shell command to run (PowerShell on Windows, bash on macOS/Linux)",
  "description": "one sentence: what this command does",
  "verify_command": "a command that, if run after, confirms the change took effect (or empty string if not verifiable)",
  "risk_level": "reversible" or "destructive"
}}

Rules:
- Windows → PowerShell syntax (e.g. Set-ItemProperty, reg add, [SystemParametersInfo])
- macOS → defaults write / osascript
- Linux → gsettings set / dbus-send
- The command must accomplish the user's request in ONE execution
- If the request needs a file path the user hasn't provided, set command to "" and description to what's missing
- risk_level "destructive" only if the action cannot be undone (shutdown, format, delete)

Emit ONLY the JSON object, no markdown, no explanation.
"""

DANGEROUS_PATTERNS = re.compile(
    r"\b(format|rm\s+-rf|del\s+/[sq]|shutdown\s+(/s|-s)|diskpart|cipher\s+/w|"
    r"reg\s+delete\s+HKLM\\SYSTEM|Remove-Item\s+-Recurse\s+-Force\s+C:\\|"
    r"del\s+C:\\Windows|rd\s+/s\s+/q\s+C:\\|mkfs|dd\s+if=)"
    , re.I
)


def plan_os_action(user_text: str, llm_client=None) -> Optional[OSActionPlan]:
    """Have the LLM plan the OS command. Returns None on any failure."""
    import datetime
    import uuid

    if llm_client is None:
        from app.llm import llm_client as default_client
        llm_client = default_client

    shell = _shell_for_platform()
    platform_name = platform.system()

    try:
        messages = [
            {"role": "system", "content": _PLANNER_SYSTEM},
            {"role": "user", "content": f"Platform: {platform_name}\nRequest: {user_text}"},
        ]
        # Try the MAIN model first (better commands); fall back to FAST when
        # the main route is broken (live case: profile named a model LM
        # Studio doesn't have loaded -> HTTP 400 -> simulated response ->
        # planner dead -> every OS request fell through to chat deflection).
        response = llm_client.generate_chat_completion(
            messages=messages, complexity="main", max_tokens=300)
        if response.get("simulated") or response.get("id") == "chat-simulated":
            app_logger.info("OS planner: main model unavailable; retrying with fast model.")
            response = llm_client.generate_chat_completion(
                messages=messages, complexity="fast", max_tokens=300)
        if response.get("simulated") or response.get("id") == "chat-simulated":
            app_logger.warning("OS planner refused simulated LLM response (no real model).")
            return None
        raw = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not raw.strip():
            return None

        # Extract JSON from the reply
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        parsed = SemanticGoalInterpreter.extract_json_object(raw)
        if not parsed or not isinstance(parsed, dict):
            return None

        command = str(parsed.get("command", "")).strip()
        if not command:
            return None

        # Safety: refuse obviously destructive patterns regardless of what
        # the LLM says about risk.
        if DANGEROUS_PATTERNS.search(command):
            audit_logger.warning(f"OS planner refused dangerous command: {command[:120]}")
            return None

        return OSActionPlan(
            plan_id=f"osplan_{uuid.uuid4().hex[:12]}",
            user_request=user_text,
            command=command,
            shell=shell,
            description=str(parsed.get("description", ""))[:500],
            verify_command=str(parsed.get("verify_command", "")).strip(),
            risk_level="destructive" if str(parsed.get("risk_level", "")).lower() == "destructive" else "reversible",
            platform=platform_name,
        )
    except Exception as exc:
        app_logger.warning(f"OS action planning failed: {exc}")
        return None


def execute_os_plan(plan: OSActionPlan, runner=None) -> Dict[str, Any]:
    """Execute a plan through the cooperative-cancellation subprocess runner.

    The caller is responsible for having passed the ActionGate; this function
    runs the command and the verify command, then reports honestly.
    """
    from app.cognition.execution_control import run_cancellable_subprocess

    if runner is None:
        runner = run_cancellable_subprocess

    args: List[str]
    if plan.shell == "powershell":
        args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", plan.command]
    else:
        args = ["bash", "-c", plan.command]

    result: Dict[str, Any] = {
        "success": False,
        "plan_id": plan.plan_id,
        "user_request": plan.user_request,
        "command": plan.command,
        "description": plan.description,
        "platform": plan.platform,
        "risk_level": plan.risk_level,
        "stdout": "",
        "stderr": "",
        "verify_output": "",
        "environment_verified": False,
        "verification_unknown": True,
    }

    try:
        completed = runner(args, timeout=30)
        result["stdout"] = (completed.stdout or "")[:2000]
        result["stderr"] = (completed.stderr or "")[:2000]
        result["returncode"] = completed.returncode
        result["request_success"] = completed.returncode == 0
        result["success"] = completed.returncode == 0
        result["side_effects"] = True

        if plan.verify_command:
            verify_args = (
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", plan.verify_command]
                if plan.shell == "powershell"
                else ["bash", "-c", plan.verify_command]
            )
            try:
                verify_result = runner(verify_args, timeout=15)
                result["verify_output"] = (verify_result.stdout or "")[:1000]
                result["verify_returncode"] = verify_result.returncode
                if verify_result.returncode == 0 and (verify_result.stdout or "").strip():
                    result["environment_verified"] = True
                    result["verification_unknown"] = False
                    result["success"] = result["request_success"] and True
            except Exception as exc:
                result["verify_error"] = str(exc)[:200]

        audit_logger.info(
            "OS action executed: %s -> %s (verified=%s)",
            plan.user_request[:60], plan.command[:80], result["environment_verified"],
        )
        return result
    except Exception as exc:
        result["error"] = str(exc)[:500]
        result["side_effects"] = True  # the command may have partially run
        return result
