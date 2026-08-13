import pytest
from app.tools.win32_ghost_operator import Win32GhostOperator

def test_win32_ghost_operator():
    wins = Win32GhostOperator.list_open_windows()
    assert isinstance(wins, list)

    res = Win32GhostOperator.send_background_window_message("Chrome", message_type="click")
    assert res["success"] is True
    assert "background_operation" in res
