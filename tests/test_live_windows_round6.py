"""Round 6 — the owner's Windows verification run (2026-09-11), pinned.

Her live transcript, as tests:
  * "open itunes on my pc" reached the inventory scan as a WHOLE SENTENCE
    (payload echoed the request; 5 words slipped under the launcher's
    6-word guard) — the executor seam must re-extract the app name;
  * the Plan-B tool 'list_windows' crashed the registry with "list
    indices must be integers or slices, not str" — handlers must return
    dicts, and the registry must normalize honestly instead of crashing;
  * suite hermeticity: her live embedding model flipped
    test_associative_memory, and a machine with capture but no analysis
    backend flipped test_vision (both fixed in those files).
"""

from unittest.mock import patch

import pytest

from app.agents.master_agent import MasterAgentOrchestrator, extract_app_query
from app.cognition.action_proposal import ActionProposal


# ── the sentence-as-app-name bug ──────────────────────────────────────────


class TestExtractionFromTranscript:
    @pytest.mark.parametrize("text,expected", [
        ("open itunes on my pc", "itunes"),
        ("open itunes on my computer", "itunes"),
        ("launch spotify on the pc", "spotify"),
        ("start vlc on my machine now", "vlc"),
        ("open richst tv on my desktop", "richst tv"),
    ])
    def test_locative_tails_are_stripped(self, text, expected):
        assert extract_app_query(text) == expected

    def test_plain_requests_still_work(self):
        # the pre-existing contract is untouched
        assert extract_app_query("open firefox") == "firefox"
        assert extract_app_query("launch the calculator") == "calculator"
        assert extract_app_query("what is the weather") == ""


def _run_launch(payload_app_name, user_text):
    calls = []

    def fake_launch(query):
        calls.append(query)
        return {"success": True, "app_name": "iTunes",
                "executable_path": "C:/iTunes.exe"}

    with patch("app.tools.app_inventory.SystemAppInventory.launch_any_app",
               side_effect=fake_launch), \
         patch("app.agents.master_agent.llm_client.generate_chat_completion",
               return_value={"error": "provider offline in test"}):
        MasterAgentOrchestrator.execute_proposal(
            ActionProposal(action_type="open_application",
                           payload={"app_name": payload_app_name}),
            user_text)
    return calls


class TestSeamSanitizesSentencePayloads:
    def test_echoed_request_is_reextracted(self):
        # Her exact failure: payload app_name == the whole request.
        calls = _run_launch("open itunes on my pc", "open itunes on my pc")
        assert calls == ["itunes"]  # the SENTENCE never reaches the inventory

    def test_verb_prefixed_payload_is_reextracted(self):
        calls = _run_launch("launch spotify please", "launch spotify please")
        assert calls == ["spotify"]

    def test_clean_payload_is_untouched(self):
        calls = _run_launch("RichST TV", "open RichST TV")
        assert calls == ["RichST TV"]


# ── the list_windows crash ────────────────────────────────────────────────


class TestListWindowsContract:
    def test_handler_returns_the_dict_contract(self):
        from app.tools.manifest import get_tool_manifest
        entry = get_tool_manifest()["list_windows"]
        result = entry["handler"]({})
        assert isinstance(result, dict), (
            "tool results must be dicts — the bare list crashed the "
            "registry scoring pass on the owner's machine")
        assert result["success"] is True
        assert isinstance(result["windows"], list)
        assert result["count"] == len(result["windows"])

    def test_observation_router_shape_is_served(self):
        # observation_router reads data["success"] and
        # data["open_windows"]/["windows"] — the contract must keep both.
        from app.tools.manifest import get_tool_manifest
        result = get_tool_manifest()["list_windows"]["handler"]({})
        assert "open_windows" in result and "windows" in result
