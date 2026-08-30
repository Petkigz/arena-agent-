import os
import sys
import ctypes
import platform
import subprocess
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger, audit_logger

class Win32GhostOperator:
    """
    Background Win32 HWND Application Operator.
    Enables the assistant to send direct window messages (clicks, text input, key presses)
    to background/minimized Windows applications without moving the physical mouse cursor
    or stealing display focus from the user.
    """

    @staticmethod
    def list_open_windows() -> List[Dict[str, Any]]:
        """
        Enumerates all active desktop window handles (HWNDs) and window titles.
        """
        windows = []
        host_os = platform.system().lower()

        if host_os == "windows":
            try:
                user32 = ctypes.windll.user32
                EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)

                def enum_handler(hwnd, lparam):
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buff, length + 1)
                            title = buff.value.strip()
                            if title:
                                windows.append({"hwnd": int(hwnd), "title": title})
                    return True

                user32.EnumWindows(EnumWindowsProc(enum_handler), 0)
            except Exception as e:
                app_logger.warning(f"Win32 EnumWindows notice: {e}")

        # Empty is authoritative: non-Windows hosts and enumeration failures do
        # not have real HWNDs. Never invent window handles or titles.
        return windows

    @staticmethod
    def bind_window(windows, query: str) -> Dict[str, Any]:
        """Bind ONE window from a title query — uniquely, or refuse.

        Exact (case-insensitive) title match wins when unique; otherwise a
        substring match must be UNIQUE — ambiguity lists candidates instead of
        silently choosing the first window.
        """
        query_clean = (query or "").lower().strip()
        if not query_clean:
            return {"success": False, "error": "Window title query is required"}
        exact = [w for w in windows if w["title"].lower() == query_clean]
        candidates = exact or [w for w in windows if query_clean in w["title"].lower()]
        if not candidates:
            return {"success": False, "error": f"No visible window matched '{query}'."}
        if len(candidates) > 1:
            return {
                "success": False,
                "error": f"Ambiguous window query '{query}': {len(candidates)} windows matched.",
                "candidates": [{"hwnd": w["hwnd"], "title": w["title"]} for w in candidates[:10]],
            }
        return {"success": True, "window": candidates[0]}

    @staticmethod
    def window_pid(hwnd: int) -> Optional[int]:
        """Owning process id for a window handle, when the platform exposes it."""
        try:
            if platform.system().lower() == "windows":
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(
                    ctypes.c_size_t(hwnd), ctypes.byref(pid))
                return int(pid.value) or None
        except Exception as exc:
            app_logger.debug(f"Window PID lookup unavailable: {exc}")
        return None

    def send_background_window_message(
        window_title_query: str,
        message_type: str = "click",
        text_payload: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends asynchronous background Win32 messages (WM_CLICK, WM_SETTEXT, WM_KEYDOWN)
        directly to a minimized/background window handle without disturbing the user's mouse.
        """
        host_os = platform.system().lower()
        if host_os != "windows":
            return {
                "success": False,
                "available": False,
                "attempted": False,
                "error": "Background HWND messaging is available only on Windows.",
            }

        binding = Win32GhostOperator.bind_window(
            Win32GhostOperator.list_open_windows(), window_title_query)
        if not binding.get("success"):
            return {
                "success": False,
                "available": True,
                "attempted": False,
                "error": binding.get("error", "window binding failed"),
                "candidates": binding.get("candidates"),
            }
        target_win = binding["window"]

        hwnd = target_win["hwnd"]
        title = target_win["title"]
        # Ground the window to its owning process when the platform allows it.
        pid = Win32GhostOperator.window_pid(hwnd)

        app_logger.info(f"Win32GhostOperator sending background '{message_type}' to HWND {hwnd} ('{title}')")

        success = False
        if host_os == "windows":
            try:
                user32 = ctypes.windll.user32
                WM_SETTEXT = 0x000C
                WM_LBUTTONDOWN = 0x0201
                WM_LBUTTONUP = 0x0202

                if message_type == "text" and text_payload:
                    success = bool(user32.SendMessageW(hwnd, WM_SETTEXT, 0, text_payload))
                elif message_type == "click":
                    down = bool(user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, 0))
                    up = bool(user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, 0))
                    success = down and up
            except Exception as e:
                app_logger.warning(f"Win32 Direct Message error: {e}")

        db.create_audit_log(
            "send_background_window_message",
            "success" if success else "failed",
            f"Background '{message_type}' for window '{title}' (HWND: {hwnd}, PID: {pid})",
            level=1,
        )

        return {
            "success": success,
            "attempted": True,
            "hwnd": hwnd,
            "window_title": title,
            "window_pid": pid,
            "message_type": message_type,
            "background_operation": success,
            "error": None if success else "Win32 message could not be delivered.",
        }
