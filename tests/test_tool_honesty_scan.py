"""
Regression guard: the systematic scan for the bug classes found live in
'now in contrrol panel open user accounts' (see test_launch_validation.py for
the first three fixes). The SAME classes repeated elsewhere:

1. Success claimed without subprocess evidence — app_inventory's
   `cmd /c start` ran uncaptured, so Windows printed 'The system cannot find
   the file …' while the tool returned success=True (the root cause under the
   original bug). play_media_file had the same blind-spawn pattern.
2. Blind 'Direct Command Fallback' — any unmatched ≤6-word string was executed
   as a shell command instead of being reported as not installed.
3. Bidirectional substring process matching in the ObservationCollector — a
   process named inside a sentence app_name counted as 'running', which could
   falsely verify a failed launch.
4. restart_process passed start_new_session=True, which raises ValueError on
   Windows — restart on Windows killed the process and never relaunched it.
5. WorldModel capability matching used bare bidirectional substrings
   ('phone' → 'microphone'), inconsistent with the token-boundary rule the
   same function applies to tool names.
"""

import subprocess
import sys
from unittest.mock import patch

from app.cognition.action_proposal import ActionProposal
from app.cognition.execution_result import ExecutionResult, ExecutionStatus
from app.cognition.perception import ObservationCollector
from app.cognition.runtime import CognitiveRuntime
from app.cognition.world_model import WorldModel
from app.tools.app_inventory import SystemAppInventory, _launch_failure_detail
from app.tools.process_manager import ProcessManager
from app.tools.universal_filesystem import UniversalFilesystem


# ─────────────────────────────────────────────────────────────────────────────
# 1+2. app_inventory: honest launch + no blind command fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_unmatched_short_query_is_not_blindly_executed():
    """'user accounts' (≤6 words, not installed, not on PATH) must be reported
    as not found — not executed as a shell command that fails silently."""
    SystemAppInventory._cached_apps = [
        {"app_name": "totally unrelated app", "executable_path": "/bin/true",
         "source_category": "test"}
    ]
    try:
        result = SystemAppInventory.launch_any_app("user accounts")
        assert result["success"] is False
        assert "no installed application matches" in result["error"].lower()
    finally:
        SystemAppInventory._cached_apps = []


def test_windows_start_failure_is_reported_not_swallowed():
    """The exact live failure mode: `cmd /c start` fails, Windows prints
    'The system cannot find the file' — the tool must return success=False
    with that error, not success=True."""
    SystemAppInventory._cached_apps = [
        {"app_name": "ghost app", "executable_path": "C:\\missing\\ghost.exe",
         "source_category": "test"}
    ]
    try:
        with patch("app.tools.app_inventory.platform.system", return_value="Windows"), \
             patch("app.tools.app_inventory.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="",
                stderr="The system cannot find the file C:\\missing\\ghost.exe.")
            result = SystemAppInventory.launch_any_app("ghost app")
        assert result["success"] is False
        assert "cannot find the file" in result["error"].lower()
    finally:
        SystemAppInventory._cached_apps = []


def test_windows_start_exit_zero_with_error_text_still_fails():
    """cmd can exit 0 while still printing a failure message — the captured
    text is checked, not just the exit code."""
    SystemAppInventory._cached_apps = [
        {"app_name": "ghost app", "executable_path": "C:\\missing\\ghost.exe",
         "source_category": "test"}
    ]
    try:
        with patch("app.tools.app_inventory.platform.system", return_value="Windows"), \
             patch("app.tools.app_inventory.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="",
                stderr="'ghost' is not recognized as an internal or external command.")
            result = SystemAppInventory.launch_any_app("ghost app")
        assert result["success"] is False
        assert "not recognized" in result["error"].lower()
    finally:
        SystemAppInventory._cached_apps = []


def test_windows_start_clean_output_still_succeeds():
    SystemAppInventory._cached_apps = [
        {"app_name": "real app", "executable_path": "C:\\apps\\real.exe",
         "source_category": "test"}
    ]
    try:
        with patch("app.tools.app_inventory.platform.system", return_value="Windows"), \
             patch("app.tools.app_inventory.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="")
            result = SystemAppInventory.launch_any_app("real app")
        assert result["success"] is True
    finally:
        SystemAppInventory._cached_apps = []


def test_launch_failure_detail_helper():
    assert _launch_failure_detail(0, "", "The system cannot find the file X") is not None
    assert _launch_failure_detail(1, "", "") == "exit code 1"
    assert _launch_failure_detail(0, "all good", "") is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. ObservationCollector: token-aware process probe
# ─────────────────────────────────────────────────────────────────────────────

class _FakeProc:
    def __init__(self, name):
        self.info = {"name": name}


def _probe(app_name: str, process_names, tmp_path) -> str:
    wm = WorldModel(str(tmp_path / "arena.db"))
    proposal = ActionProposal(action_type="open_application", payload={"app_name": app_name})
    exec_res = ExecutionResult(
        proposal_id=proposal.proposal_id,
        action_type=proposal.action_type,
        execution_status=ExecutionStatus.SUCCEEDED,
        attempted=True,
        executed_actions=[f"Launched application '{app_name}'"],
        assistant_reply="ok",
        execution_facts=[],
    )
    fakes = [_FakeProc(n) for n in process_names]
    with patch("psutil.process_iter", return_value=fakes):
        ObservationCollector.collect_and_ingest_observations(proposal, exec_res, world_model=wm)
    obs = wm.latest_observation(app_name, "status")
    assert obs is not None
    return obs.value


def test_sentence_app_name_never_matches_running_process(tmp_path):
    """The false-verification path: a process name appearing INSIDE a
    sentence app_name must not count as 'running'."""
    status = _probe(
        "now in contrrol panel open user accounts",
        ["panel.exe", "svchost.exe"],
        tmp_path,
    )
    assert status == "not_running"


def test_exact_app_name_still_matches_running_process(tmp_path):
    assert _probe("firefox", ["firefox.exe"], tmp_path) == "running"


def test_multiword_app_name_matches_process_token(tmp_path):
    """'visual studio code' should still see a running 'code.exe'."""
    assert _probe("visual studio code", ["code.exe"], tmp_path) == "running"


def test_absent_app_is_not_running(tmp_path):
    assert _probe("photoshop", ["explorer.exe"], tmp_path) == "not_running"


# ─────────────────────────────────────────────────────────────────────────────
# 4. process_manager: platform-aware restart flags
# ─────────────────────────────────────────────────────────────────────────────

class _FakePsutilProc:
    def __init__(self, pid):
        self._pid = pid

    def cmdline(self):
        return ["fakeapp", "--flag"]


def test_restart_on_windows_uses_creationflags_not_start_new_session():
    """start_new_session raises ValueError on Windows — restart used to kill
    the process and then always fail to relaunch it."""
    with patch("app.tools.process_manager.psutil.Process", _FakePsutilProc), \
         patch.object(ProcessManager, "kill_process", return_value={"success": True}), \
         patch("app.tools.process_manager.subprocess.Popen") as mock_popen, \
         patch("app.tools.process_manager.os.name", "nt"):
        result = ProcessManager.restart_process(4321)
    assert result["success"] is True
    kwargs = mock_popen.call_args.kwargs
    assert "start_new_session" not in kwargs
    assert "creationflags" in kwargs


def test_restart_on_posix_keeps_start_new_session():
    with patch("app.tools.process_manager.psutil.Process", _FakePsutilProc), \
         patch.object(ProcessManager, "kill_process", return_value={"success": True}), \
         patch("app.tools.process_manager.subprocess.Popen") as mock_popen, \
         patch("app.tools.process_manager.os.name", "posix"):
        result = ProcessManager.restart_process(4321)
    assert result["success"] is True
    kwargs = mock_popen.call_args.kwargs
    assert kwargs.get("start_new_session") is True
    assert "creationflags" not in kwargs


# ─────────────────────────────────────────────────────────────────────────────
# 5. runtime: token-boundary capability matching against WorldModel caps
# ─────────────────────────────────────────────────────────────────────────────

def test_capability_token_match_refuses_bare_substrings():
    match = CognitiveRuntime._capability_token_match
    assert match("phone", "microphone") is False          # the old bug
    assert match("microphone", "phone") is False
    assert match("os.launch_app", "os launch app") is True  # dotted vs spaced
    assert match("os launch", "os launch app") is True     # qualifier superset
    assert match("browser automation", "browser automation") is True
    assert match("totally invented phrase", "real capability") is False


# ─────────────────────────────────────────────────────────────────────────────
# 6. universal_filesystem: media open checks the launcher's exit code
# ─────────────────────────────────────────────────────────────────────────────

def test_play_media_reports_launcher_failure(tmp_path):
    media = tmp_path / "song.mp3"
    media.write_bytes(b"\x00" * 32)
    if sys.platform == "win32":
        # Windows route: os.startfile has no exit-code channel — an OS
        # error is the observable failure and must be reported honestly.
        with patch("app.tools.universal_filesystem.os.startfile",
                   side_effect=OSError("no file association")):
            result = UniversalFilesystem.play_media_file(str(media))
        assert result["success"] is False
        assert "no file association" in result["error"].lower()
    else:
        # POSIX route: xdg-open's non-zero exit must be surfaced.
        with patch("app.tools.universal_filesystem.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=2, stdout="", stderr="xdg-open: no method available")
            result = UniversalFilesystem.play_media_file(str(media))
        assert result["success"] is False
        assert "xdg-open failed" in result["error"].lower()


def test_play_media_succeeds_on_clean_exit(tmp_path):
    media = tmp_path / "song.mp3"
    media.write_bytes(b"\x00" * 32)
    if sys.platform == "win32":
        # Windows route: patch os.startfile so the test never actually
        # opens the owner's media player.
        with patch("app.tools.universal_filesystem.os.startfile") as mock_start:
            result = UniversalFilesystem.play_media_file(str(media))
        assert result["success"] is True
        mock_start.assert_called_once()
    else:
        with patch("app.tools.universal_filesystem.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="")
            result = UniversalFilesystem.play_media_file(str(media))
        assert result["success"] is True
