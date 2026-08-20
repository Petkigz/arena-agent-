"""
Finding #8 Regression Tests: Complete Search Result-Set Observations.

Verifies that search_files observes the complete bounded result set,
not just the first matching file. WorldModel receives entities for
every returned item, and the result-set observation includes count,
items, deduplication, completeness, and limit metadata.
"""

import pytest
from unittest.mock import patch
from app.cognition.perception import ObservationCollector
from app.cognition.action_proposal import ActionProposal
from app.cognition.world_model import WorldModel
from app.agents.master_agent import MasterAgentOrchestrator


def _make_proposal(payload: dict = None) -> ActionProposal:
    return ActionProposal(action_type="search_files", payload=payload or {})


# ── Result-Set Observation ────────────────────────────────────────────


class TestSearchResultSetObservation:

    def test_multi_file_result_set_has_all_items(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal({"query": "report"})
        exec_result = {
            "success": True,
            "raw_output": {
                "matched_files": [
                    {"file_name": "report1.pdf", "file_path": "/docs/report1.pdf", "size_bytes": 100, "extension": ".pdf"},
                    {"file_name": "report2.pdf", "file_path": "/docs/report2.pdf", "size_bytes": 200, "extension": ".pdf"},
                    {"file_name": "report3.pdf", "file_path": "/docs/report3.pdf", "size_bytes": 300, "extension": ".pdf"},
                ],
                "result_found": True,
                "query": "report",
                "max_results": 5
            },
            "execution_facts": [],
            "executed_actions": ["Found files"],
            "assistant_reply": "Found 3 reports."
        }

        obs = ObservationCollector.collect_and_ingest_observations(proposal, exec_result, world_model=wm)

        set_obs = [o for o in obs if o.predicate == "search_result_set"]
        assert len(set_obs) == 1
        result_set = set_obs[0].value
        assert result_set["count"] == 3
        assert len(result_set["items"]) == 3
        assert result_set["status"] == "observed"
        assert result_set["complete"] is True  # 3 < 5 limit

    def test_world_model_has_entity_for_each_result(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal({"query": "doc"})
        exec_result = {
            "success": True,
            "raw_output": {
                "matched_files": [
                    {"file_name": "a.pdf", "file_path": "/a.pdf"},
                    {"file_name": "b.pdf", "file_path": "/b.pdf"},
                ],
                "result_found": True,
                "query": "doc",
                "max_results": 5
            },
            "execution_facts": [],
            "executed_actions": [],
            "assistant_reply": ""
        }

        ObservationCollector.collect_and_ingest_observations(proposal, exec_result, world_model=wm)

        # Both files should be in WorldModel
        entities = wm.find_entities()
        entity_names = [e.name for e in entities]
        assert "a.pdf" in entity_names
        assert "b.pdf" in entity_names

    def test_duplicate_paths_deduplicated(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal({"query": "test"})
        exec_result = {
            "success": True,
            "raw_output": {
                "matched_files": [
                    {"file_name": "file.txt", "file_path": "/same/path.txt"},
                    {"file_name": "file_copy.txt", "file_path": "/same/path.txt"},  # duplicate
                ],
                "result_found": True,
                "query": "test",
                "max_results": 5
            },
            "execution_facts": [],
            "executed_actions": [],
            "assistant_reply": ""
        }

        obs = ObservationCollector.collect_and_ingest_observations(proposal, exec_result, world_model=wm)

        set_obs = [o for o in obs if o.predicate == "search_result_set"]
        assert len(set_obs) == 1
        assert set_obs[0].value["count"] == 1  # Deduplicated

    def test_first_result_compatibility_preserved(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal({"query": "contract"})
        exec_result = {
            "success": True,
            "raw_output": {
                "matched_files": [
                    {"file_name": "contract.pdf", "file_path": "/docs/contract.pdf"},
                    {"file_name": "contract_v2.pdf", "file_path": "/docs/contract_v2.pdf"},
                ],
                "result_found": True,
                "query": "contract",
                "max_results": 5
            },
            "execution_facts": [],
            "executed_actions": [],
            "assistant_reply": ""
        }

        obs = ObservationCollector.collect_and_ingest_observations(proposal, exec_result, world_model=wm)

        # First-result compatibility observation must still exist
        file_path_obs = [o for o in obs if o.predicate == "file_path"]
        assert len(file_path_obs) >= 1
        assert file_path_obs[0].value == "/docs/contract.pdf"
        assert file_path_obs[0].source == "filesystem_probe"

    def test_empty_result_set_observed_distinctly(self, tmp_path):
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal({"query": "nonexistent"})
        exec_result = {
            "success": True,
            "raw_output": {
                "matched_files": [],
                "result_found": False,
                "query": "nonexistent",
                "max_results": 5
            },
            "execution_facts": [],
            "executed_actions": [],
            "assistant_reply": ""
        }

        obs = ObservationCollector.collect_and_ingest_observations(proposal, exec_result, world_model=wm)

        # Should have not_found file_path observation
        fp_obs = [o for o in obs if o.predicate == "file_path"]
        assert len(fp_obs) >= 1
        assert fp_obs[0].value == "not_found"

        # Should have empty result set
        set_obs = [o for o in obs if o.predicate == "search_result_set"]
        assert len(set_obs) == 1
        assert set_obs[0].value["count"] == 0
        assert set_obs[0].value["items"] == []
        assert set_obs[0].value["status"] == "observed"

    def test_incomplete_result_set_when_limit_reached(self, tmp_path):
        """When search was truncated, set should be marked incomplete."""
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal({"query": "log", "all_matches": True})
        # Simulate 1000 results with truncation flag set
        files = [{"file_name": f"log_{i}.txt", "file_path": f"/logs/log_{i}.txt"} for i in range(1000)]
        exec_result = {
            "success": True,
            "raw_output": {
                "matched_files": files,
                "result_found": True,
                "query": "log",
                "max_results": 1000,
                "truncated": True
            },
            "execution_facts": [],
            "executed_actions": [],
            "assistant_reply": ""
        }

        obs = ObservationCollector.collect_and_ingest_observations(proposal, exec_result, world_model=wm)

        set_obs = [o for o in obs if o.predicate == "search_result_set"]
        assert len(set_obs) == 1
        result_set = set_obs[0].value
        # Truncated → incomplete
        assert result_set["complete"] is False

    def test_complete_result_set_when_not_truncated(self, tmp_path):
        """When search was NOT truncated, set should be marked complete even at limit."""
        wm = WorldModel(str(tmp_path / "test.db"))
        proposal = _make_proposal({"query": "report"})
        # Exactly 5 results but NOT truncated (there are exactly 5 matching files)
        files = [{"file_name": f"report_{i}.pdf", "file_path": f"/docs/report_{i}.pdf"} for i in range(5)]
        exec_result = {
            "success": True,
            "raw_output": {
                "matched_files": files,
                "result_found": True,
                "query": "report",
                "max_results": 5,
                "truncated": False
            },
            "execution_facts": [],
            "executed_actions": [],
            "assistant_reply": ""
        }

        obs = ObservationCollector.collect_and_ingest_observations(proposal, exec_result, world_model=wm)

        set_obs = [o for o in obs if o.predicate == "search_result_set"]
        assert len(set_obs) == 1
        result_set = set_obs[0].value
        # Not truncated → complete, even though count == limit
        assert result_set["complete"] is True


# ── Executor "Find All" Behavior ──────────────────────────────────────


class TestSearchFilesAllBehavior:

    def test_normal_search_uses_limit_5(self):
        """Normal search should request limit+1 to detect truncation."""
        proposal = _make_proposal({"query": "report"})
        with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=[]) as mock_search:
            MasterAgentOrchestrator.execute_proposal(proposal, user_text="find report")
            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args
            # Requests max_results=6 (5+1) to detect truncation
            actual_max = call_kwargs[1].get("max_results") or (call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None)
            assert actual_max == 6
            # But raw_output reports the user-facing limit of 5

    def test_all_keyword_uses_limit_1000(self):
        """Query containing 'all' should use limit of 1000."""
        proposal = _make_proposal({"query": "find all reports"})
        with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=[]):
            res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="find all reports")
            raw = res.get("raw_output", {})
            assert raw.get("max_results") == 1000

    def test_explicit_max_results_respected(self):
        """Explicit max_results in payload should be used (bounded to 1-1000)."""
        proposal = _make_proposal({"query": "logs", "max_results": 50})
        with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=[]):
            res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="find logs")
            raw = res.get("raw_output", {})
            assert raw.get("max_results") == 50

    def test_max_results_bounded_to_1000(self):
        """max_results cannot exceed 1000."""
        proposal = _make_proposal({"query": "everything", "max_results": 50000})
        with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=[]):
            res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="find everything")
            raw = res.get("raw_output", {})
            assert raw.get("max_results") == 1000

    def test_all_matches_flag_uses_limit_1000(self):
        """all_matches=True in payload should use limit of 1000."""
        proposal = _make_proposal({"query": "reports", "all_matches": True})
        with patch("app.tools.universal_filesystem.UniversalFilesystem.search_filesystem", return_value=[]):
            res = MasterAgentOrchestrator.execute_proposal(proposal, user_text="find reports")
            raw = res.get("raw_output", {})
            assert raw.get("max_results") == 1000
