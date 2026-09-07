"""Behavior protected while removing obsolete/ignored code paths."""

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.tools.connectors import ConnectorsTool
from app.tools.doc_manager import DocumentManager
import validate


def test_email_draft_cannot_claim_success_when_its_writer_failed(monkeypatch):
    monkeypatch.setattr(DocumentManager, "create_document", Mock(return_value={
        "success": False, "error": "Policy blocked the write",
    }))
    result = ConnectorsTool.prepare_email_draft("owner@example.test", "Subject", "Body")
    assert result["success"] is False
    assert "Policy blocked" in result["error"]
    assert "draft_file" not in result


def test_email_draft_keeps_the_real_writer_artifact_reference(monkeypatch, tmp_path):
    path = str(tmp_path / "email.md")
    monkeypatch.setattr(DocumentManager, "create_document", Mock(return_value={
        "success": True, "file_path": path,
    }))
    result = ConnectorsTool.prepare_email_draft("owner@example.test", "Subject", "Body")
    assert result["success"] is True
    assert result["file_path"] == path


def test_adb_diagnostic_does_not_turn_a_failed_listing_into_a_pass(monkeypatch):
    from scripts import owner_diagnostics
    from app.tools.android_adb_controller import AndroidADBController

    monkeypatch.setattr(AndroidADBController, "is_adb_available", Mock(return_value=True))
    monkeypatch.setattr(AndroidADBController, "list_connected_devices", Mock(return_value={
        "success": False, "error": "ADB disconnected",
    }))
    status, detail = owner_diagnostics.h_adb_phone()
    assert status == "fail"
    assert "ADB disconnected" in detail


@pytest.mark.parametrize("quick", [False, True])
def test_validator_runs_one_selected_suite_and_uses_junit_not_output_word_counts(monkeypatch, quick):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["env"]["ARENA_LLM_DISABLED"] == "1"
        assert kwargs["env"]["LPA_AUTONOMY_MODE"] == "off"
        assert Path(kwargs["env"]["LPA_DB_PATH"]).parent.is_dir()
        report = Path(next(item.split("=", 1)[1] for item in command if item.startswith("--junitxml=")))
        report.write_text('<testsuites><testsuite><testcase/><testcase><skipped/></testcase></testsuite></testsuites>')
        return subprocess.CompletedProcess(command, 0, stdout="999 PASSED is not the result", stderr="")

    monkeypatch.setattr(validate.subprocess, "run", run)
    result = validate.run_validation(quick=quick)
    assert len(calls) == 1
    assert result["success"] is True
    assert result["passed"] == 1
    assert result["skipped"] == 1
    assert result["scope"] == ("quick" if quick else "full")
    if quick:
        assert all(target in calls[0] for target in validate.QUICK_TESTS)
        assert "tests/" not in calls[0]
    else:
        assert "tests/" in calls[0]
        assert not any(target in calls[0] for target in validate.QUICK_TESTS)


def test_validator_honors_documented_flags_and_rejects_invalid_combinations():
    assert validate.parse_args(["--quick"]).quick is True
    assert validate.parse_args(["--full"]).quick is False
    with pytest.raises(SystemExit):
        validate.parse_args(["--quick", "--full"])
    with pytest.raises(SystemExit):
        validate.parse_args(["--timeout", "0"])
