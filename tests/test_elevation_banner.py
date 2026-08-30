"""Startup elevation banner: owners often don't know whether the agent
process is elevated — an admin ACCOUNT is not an elevated PROCESS under
UAC (live question after the MFT/admin discussion)."""


class _Rec:
    def __init__(self):
        self.lines = []

    def info(self, msg, *a):
        self.lines.append(msg % a if a else msg)

    def warning(self, msg, *a):
        self.lines.append(msg % a if a else msg)


def test_elevated_run_logs_warning():
    from app.server import _log_elevation_status

    rec = _Rec()
    _log_elevation_status(is_elevated=True, platform="win32", logger=rec)
    assert any("ELEVATED" in line for line in rec.lines), rec.lines
    assert any("Recommended" in line for line in rec.lines)


def test_standard_run_logs_reassuring_info():
    from app.server import _log_elevation_status

    rec = _Rec()
    _log_elevation_status(is_elevated=False, platform="win32", logger=rec)
    assert any("standard user privileges" in line for line in rec.lines), rec.lines
    assert not any("ELEVATED" in line for line in rec.lines)


def test_non_windows_is_silent():
    from app.server import _log_elevation_status

    rec = _Rec()
    _log_elevation_status(is_elevated=True, platform="linux", logger=rec)
    assert rec.lines == []
