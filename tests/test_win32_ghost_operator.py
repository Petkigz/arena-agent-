import pytest
from app.tools.win32_ghost_operator import Win32GhostOperator

def test_win32_ghost_operator(monkeypatch):
    monkeypatch.setattr("app.tools.win32_ghost_operator.platform.system", lambda: "Linux")
    wins = Win32GhostOperator.list_open_windows()
    assert wins == []

    res = Win32GhostOperator.send_background_window_message("Chrome", message_type="click")
    assert res["success"] is False
    assert res["available"] is False
    assert res["attempted"] is False
