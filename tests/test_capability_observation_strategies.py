"""
Finding #7 Regression Tests: Capability-Specific Observation Strategies.

Verifies that web_search, screen_capture, phone_command, run_command,
and diagnostic/investigate each have dedicated environmental observation
strategies that independently probe the environment AFTER execution.

Execution success is NEVER used as evidence.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from app.cognition.perception import ObservationCollector
from app.cognition.action_proposal import ActionProposal
from app.cognition.world_model import WorldModel


def _make_proposal(action_type: str, payload: dict = None) -> ActionProposal:
    return ActionProposal(action_type=action_type, payload=payload or {})


def _make_exec_result(success=True, raw_output=None, execution_facts=None):
    return {
        "success": success,
        "raw_output": raw_output or {},
        "execution_facts": execution_facts or [],
        "executed_actions": ["test action"],
        "assistant_reply": "test reply"
    }


# ── Web Search ────────────────────────────────────────────────────────


class TestWebSearchObservation:

    # Simulated Google search response with actual result structure
    MOCK_SEARCH_HTML = b"""
    <html><body>
    <a href="/url?q=https://docs.python.org/3/&amp;sa=U&amp;ved=abc"><h3>Python Documentation</h3></a>
    <a href="/url?q=https://fastapi.tiangolo.com/&amp;sa=U&amp;ved=def"><h3>FastAPI Framework</h3></a>
    <a href="/url?q=https://stackoverflow.com/questions/python-fastapi&amp;sa=U&amp;ved=ghi"><h3>Python FastAPI StackOverflow</h3></a>
    </body></html>
    """

    MOCK_NO_RESULTS_HTML = b"<html><body><p>Your search did not match any documents.</p></body></html>"

    def test_web_search_extracts_result_urls_and_titles(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("web_search", {"query": "python fastapi"})
        exec_result = _make_exec_result(success=True)

        mock_response = MagicMock()
        mock_response.read.return_value = self.MOCK_SEARCH_HTML
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        web_obs = [o for o in obs if o.source == "web_search_probe"]
        assert len(web_obs) == 1
        assert web_obs[0].predicate == "search_results_retrieved"
        assert web_obs[0].confidence == 1.0

        # Structured result data
        value = web_obs[0].value
        assert isinstance(value, dict)
        assert value["results_found"] is True
        assert value["result_count"] == 3
        assert len(value["results"]) == 3
        assert value["results"][0]["url"] == "https://docs.python.org/3/"
        assert "Python" in value["results"][0]["title"]
        assert value["query"] == "python fastapi"
        assert "timestamp" in value
        # Query relevance: "python" and "fastapi" should appear in results
        assert value["query_relevance_hits"] >= 2

    def test_web_search_no_results_records_zero_confidence(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("web_search", {"query": "nonexistent query xyz"})
        exec_result = _make_exec_result(success=True)

        mock_response = MagicMock()
        mock_response.read.return_value = self.MOCK_NO_RESULTS_HTML
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        web_obs = [o for o in obs if o.source == "web_search_probe"]
        assert len(web_obs) == 1
        assert web_obs[0].confidence == 0.0
        value = web_obs[0].value
        assert value["results_found"] is False
        assert value["result_count"] == 0

    def test_web_search_probe_failure_records_zero_confidence(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("web_search", {"query": "test"})
        exec_result = _make_exec_result(success=True)

        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        web_obs = [o for o in obs if o.source == "web_search_probe"]
        assert len(web_obs) == 1
        assert web_obs[0].confidence == 0.0

    def test_web_search_filters_google_internal_links(self, tmp_path):
        """Google navigation/account links must be filtered out."""
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("web_search", {"query": "test"})
        exec_result = _make_exec_result(success=True)

        # Only Google-internal links, no actual results
        html = b"""
        <html><body>
        <a href="https://accounts.google.com/signin">Sign in</a>
        <a href="https://play.google.com/store">Play Store</a>
        <a href="https://www.google.com/preferences">Settings</a>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.read.return_value = html
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        web_obs = [o for o in obs if o.source == "web_search_probe"]
        assert web_obs[0].confidence == 0.0  # No real results after filtering
        assert web_obs[0].value["result_count"] == 0

    def test_web_search_query_relevance_score(self, tmp_path):
        """Results should include query relevance metric."""
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("web_search", {"query": "machine learning"})
        exec_result = _make_exec_result(success=True)

        html = b"""
        <html><body>
        <a href="/url?q=https://sklearn.org/&amp;sa=U"><h3>Machine Learning with scikit-learn</h3></a>
        <a href="/url?q=https://unrelated-site.com/&amp;sa=U"><h3>Cookie Recipes</h3></a>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.read.return_value = html
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        web_obs = [o for o in obs if o.source == "web_search_probe"]
        value = web_obs[0].value
        assert value["results_found"] is True
        assert value["result_count"] == 2
        # "machine" or "learning" should match in first result but not second
        assert value["query_relevance_hits"] >= 1


# ── Screen Capture ────────────────────────────────────────────────────


class TestScreenCaptureObservation:

    def test_screen_capture_validates_artifact_on_disk(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        # Create a minimal valid PNG file
        screenshot = tmp_path / "screenshot.png"
        try:
            from PIL import Image
            img = Image.new("RGB", (10, 10), color="blue")
            img.save(str(screenshot), "PNG")
        except ImportError:
            screenshot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        proposal = _make_proposal("screen_capture")
        exec_result = _make_exec_result(
            success=True,
            raw_output={"cap_res": {"file_path": str(screenshot), "file_name": "screenshot.png"}}
        )

        obs = ObservationCollector.collect_and_ingest_observations(
            proposal, exec_result, world_model=wm
        )

        cap_obs = [o for o in obs if o.source == "screen_capture_file_probe"]
        assert len(cap_obs) >= 1
        # File exists and is non-empty → should be valid
        assert cap_obs[0].value == "true"
        assert cap_obs[0].confidence == 1.0

    def test_screen_capture_missing_file_records_failure(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("screen_capture")
        exec_result = _make_exec_result(
            success=True,
            raw_output={"cap_res": {"file_path": "/nonexistent/screenshot.png", "file_name": "screenshot.png"}}
        )

        obs = ObservationCollector.collect_and_ingest_observations(
            proposal, exec_result, world_model=wm
        )

        cap_obs = [o for o in obs if o.source == "screen_capture_file_probe"]
        assert len(cap_obs) >= 1
        assert cap_obs[0].value == "false"
        assert cap_obs[0].confidence == 0.0

    def test_screen_capture_execution_success_but_no_artifact(self, tmp_path):
        """Execution claims success but no file path provided → observation fails."""
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("screen_capture")
        exec_result = _make_exec_result(
            success=True,
            raw_output={"cap_res": {"success": True}}  # No file_path
        )

        obs = ObservationCollector.collect_and_ingest_observations(
            proposal, exec_result, world_model=wm
        )

        cap_obs = [o for o in obs if o.source == "screen_capture_file_probe"]
        assert len(cap_obs) >= 1
        assert cap_obs[0].value == "false"


# ── Phone Command ─────────────────────────────────────────────────────


class TestPhoneCommandObservation:

    def test_battery_probe_creates_observation(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("phone_command", {"query": "check battery level"})
        exec_result = _make_exec_result(success=True)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Current Battery Service state: OFF\n  level: 85\n  scale: 100"

        with patch("subprocess.run", return_value=mock_result):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        battery_obs = [o for o in obs if o.predicate == "battery_status"]
        assert len(battery_obs) == 1
        assert battery_obs[0].source == "adb_battery_probe"
        assert battery_obs[0].confidence == 1.0
        assert isinstance(battery_obs[0].value, dict)
        assert battery_obs[0].value.get("level") == "85"

    def test_sms_action_remains_unknown_no_sensor(self, tmp_path):
        """SMS has no reliable postcondition sensor → explicit UNKNOWN."""
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("send_sms", {"query": "send sms to 555-0199"})
        exec_result = _make_exec_result(success=True)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "device"

        with patch("subprocess.run", return_value=mock_result):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        # Should have an explicit unknown observation, not a success claim
        phone_obs = [o for o in obs if o.subject == "phone"]
        assert len(phone_obs) >= 1
        assert any("unknown" in str(o.value).lower() or o.confidence == 0.0 for o in phone_obs)

    def test_call_state_probe_creates_observation(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("make_phone_call", {"query": "call 555-0199", "phone_number": "555-0199"})
        exec_result = _make_exec_result(success=True)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "mCallState=1\nmForegroundCallState=ACTIVE"

        with patch("subprocess.run", return_value=mock_result):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        call_obs = [o for o in obs if o.predicate == "call_state"]
        assert len(call_obs) == 1
        assert call_obs[0].source == "adb_telephony_probe"


# ── Run Command ───────────────────────────────────────────────────────


class TestRunCommandObservation:

    def test_run_command_without_postcondition_is_unknown(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("run_command", {"command": "echo hello"})
        exec_result = _make_exec_result(success=True)

        obs = ObservationCollector.collect_and_ingest_observations(
            proposal, exec_result, world_model=wm
        )

        cmd_obs = [o for o in obs if o.predicate == "command_postcondition_satisfied"]
        assert len(cmd_obs) == 1
        assert cmd_obs[0].confidence == 0.0
        assert "unknown" in str(cmd_obs[0].value).lower() or "no_postcondition" in str(cmd_obs[0].value).lower()

    def test_run_command_file_postcondition_verified(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        output_file = tmp_path / "output.txt"
        output_file.write_text("result data")

        proposal = _make_proposal("run_command", {
            "command": "generate output",
            "verification": {"type": "file_exists", "path": str(output_file)}
        })
        exec_result = _make_exec_result(success=True)

        obs = ObservationCollector.collect_and_ingest_observations(
            proposal, exec_result, world_model=wm
        )

        cmd_obs = [o for o in obs if o.predicate == "command_postcondition_satisfied"]
        assert len(cmd_obs) == 1
        assert cmd_obs[0].value == "true"
        assert cmd_obs[0].confidence == 1.0

    def test_run_command_exit_code_alone_does_not_verify(self, tmp_path):
        """Even if execution reports success, without postcondition probe → UNKNOWN."""
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("run_command", {"command": "complex operation"})
        exec_result = _make_exec_result(success=True, raw_output={"exit_code": 0})

        obs = ObservationCollector.collect_and_ingest_observations(
            proposal, exec_result, world_model=wm
        )

        cmd_obs = [o for o in obs if o.predicate == "command_postcondition_satisfied"]
        assert len(cmd_obs) == 1
        assert cmd_obs[0].confidence == 0.0


# ── Diagnostic / Investigate ──────────────────────────────────────────


class TestDiagnosticObservation:

    def test_diagnostic_performs_independent_probes(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("diagnostic", {"query": "system health"})
        exec_result = _make_exec_result(success=True)

        with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=[]):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        diag_obs = [o for o in obs if o.source == "diagnostic_system_probe"]
        assert len(diag_obs) >= 1
        evidence_obs = [o for o in diag_obs if o.predicate == "diagnostic_evidence_gathered"]
        assert len(evidence_obs) == 1
        # Hardware probe should succeed in any environment
        assert evidence_obs[0].value == "true"
        assert evidence_obs[0].confidence == 1.0

    def test_investigate_action_type_also_gets_diagnostic_observation(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("investigate", {"query": "check logs"})
        exec_result = _make_exec_result(success=True)

        with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=[]):
            obs = ObservationCollector.collect_and_ingest_observations(
                proposal, exec_result, world_model=wm
            )

        diag_obs = [o for o in obs if o.source == "diagnostic_system_probe"]
        assert len(diag_obs) >= 1


# ── Search Files Result Set (Finding #8 preview) ─────────────────────


class TestSearchFilesResultSet:

    def test_multi_file_result_set_observed(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("search_files", {"query": "report"})
        exec_result = _make_exec_result(
            success=True,
            raw_output={
                "matched_files": [
                    {"file_name": "report1.pdf", "file_path": "/docs/report1.pdf", "size_bytes": 100, "extension": ".pdf"},
                    {"file_name": "report2.pdf", "file_path": "/docs/report2.pdf", "size_bytes": 200, "extension": ".pdf"},
                ],
                "result_found": True,
                "query": "report"
            }
        )

        obs = ObservationCollector.collect_and_ingest_observations(
            proposal, exec_result, world_model=wm
        )

        # Should have both first-result and result-set observations
        fs_obs = [o for o in obs if o.predicate == "file_path"]
        assert len(fs_obs) >= 1
        assert fs_obs[0].source == "filesystem_probe"

        set_obs = [o for o in obs if o.predicate == "search_result_set"]
        assert len(set_obs) == 1
        assert set_obs[0].source == "filesystem_probe"
        assert set_obs[0].confidence == 1.0
        result_set = set_obs[0].value
        assert isinstance(result_set, dict)
        assert result_set["count"] == 2
        assert len(result_set["items"]) == 2

    def test_empty_search_result_set_observed(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal("search_files", {"query": "nonexistent"})
        exec_result = _make_exec_result(
            success=True,
            raw_output={
                "matched_files": [],
                "result_found": False,
                "query": "nonexistent"
            }
        )

        obs = ObservationCollector.collect_and_ingest_observations(
            proposal, exec_result, world_model=wm
        )

        set_obs = [o for o in obs if o.predicate == "search_result_set"]
        assert len(set_obs) == 1
        result_set = set_obs[0].value
        assert result_set["count"] == 0
        assert result_set["items"] == []
        assert result_set["status"] == "observed"
