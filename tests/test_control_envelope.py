"""The control envelope (owner report 2026-09-05, final generalization):
'not only applicable to playing music but to everything.'

The kaba lesson generalized: the agent must use the control it actually
has, for every kind of request — not under-claim capability when no tool
NAME matches. Three rules, each demonstrated with non-music examples:

  1. The OS-control layer is the GENERAL executor: a control-verb request
     no specific tool wins routes to the OS planner (which plans a real
     platform command through the safety gates) instead of falling
     through to a no-capability ask.
  2. Mutation polarity: a request that says CLEAR/SET/DELETE wants a
     WRITE — a read-only tool (nothing mutation-shaped in its vocabulary)
     must not steal it.
  3. Operand completion: manifest tools taking a file path resolve bare
     names ('image_path': 'kaba.jpg') and missing operands by real
     filesystem search before execution — the same self-serve idiom as
     move/open-by-bare-name, for every tool.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")


# ── Rule 1: OS control is the general executor ──────────────────────────────


class TestOSControlGeneralExecutor:
    def test_control_requests_without_specific_tool_reach_os_planner(self):
        from app.cognition.tool_matcher import match_control_tool
        # Live gaps before the fix: each fell through to None and the
        # no-capability ask while full OS control sat unused.
        for text in (
            "empty the recycle bin",
            "add kaba to my startup programs",
            "burn the playlist to a cd",
            "set an alarm for 7am",
        ):
            m = match_control_tool(text)
            assert m is not None and m.action_type == "os_control_plan", (text, m)
            assert m.payload.get("request") == text

    def test_specific_tools_still_win_over_os_planner(self):
        from app.cognition.tool_matcher import match_control_tool, rank_tools
        # The general executor is a FALLBACK: a specific tool that serves
        # the request must keep winning.
        pins = {
            "find the file kaba": "search_files",
            "move kaba.mp3 to my music folder": "move_file",
            "play kaba": "open_file",
            "find duplicates in my pictures folder": "detect_duplicate_files",
            "set kaba.jpg as my wallpaper": "set_wallpaper",
        }
        for text, expected in pins.items():
            m = match_control_tool(text)
            assert m is not None and m.action_type == expected, (text, m)
        # Discovery-level pin: 'group my photos by date' has always been
        # margin-ambiguous for the forced matcher (pre-existing); the
        # candidate it proposes is the date grouper.
        hits = rank_tools("group my photos by date", limit=3)
        assert hits and hits[0].action_type == "group_files_by_date", hits


# ── Rule 2: mutation polarity ───────────────────────────────────────────────


class TestMutationPolarity:
    def test_clear_clipboard_goes_to_the_write_tool(self):
        from app.cognition.tool_matcher import match_control_tool
        m = match_control_tool("clear my clipboard")
        assert m is not None
        assert m.action_type == "clipboard_clear_sensitive", m
        assert m.action_type != "clipboard_inspect"

    def test_read_only_requests_still_reach_the_inspector(self):
        from app.cognition.tool_matcher import match_control_tool
        # No mutation verb -> no polarity enforcement -> the read-only
        # inspector serves the read-only request.
        m = match_control_tool("what did i copy")
        assert m is not None and m.action_type == "clipboard_inspect", m

    def test_mutation_request_never_answered_by_readonly_winner(self):
        from app.cognition.tool_matcher import match_control_tool
        # Even when the inspector would have outscored the write tool,
        # the write direction must survive.
        m = match_control_tool("delete the clipboard contents")
        assert m is None or m.action_type != "clipboard_inspect"


# ── Rule 3: operand completion ──────────────────────────────────────────────


@pytest.fixture()
def home_with_pictures(monkeypatch, tmp_path):
    pics = tmp_path / "Pictures"
    pics.mkdir()
    (pics / "kaba.jpg").write_bytes(b"\x00" * 8)
    (pics / "beach.jpg").write_bytes(b"\x00" * 8)
    monkeypatch.setenv("HOME", str(tmp_path))
    yield tmp_path
    monkeypatch.setenv("HOME", str(Path("/home/user")))


class TestOperandCompletion:
    def test_bare_name_path_resolved(self, home_with_pictures):
        from app.agents.master_agent import _complete_path_operand
        out = _complete_path_operand(
            "set_wallpaper",
            {"image_path": "kaba.jpg", "path": "kaba.jpg",
             "source_path": "kaba.jpg", "file_path": "kaba.jpg"},
            "set kaba.jpg as my wallpaper",
        )
        assert out.get("note"), out
        assert out["payload"]["image_path"].endswith("Pictures/kaba.jpg") \
            or out["payload"]["image_path"].endswith("Pictures\\kaba.jpg")
        assert Path(out["payload"]["image_path"]).exists()

    def test_missing_path_filled_from_request(self, home_with_pictures):
        from app.agents.master_agent import _complete_path_operand
        out = _complete_path_operand(
            "set_wallpaper", {}, "set kaba.jpg as my wallpaper")
        assert out["payload"].get("image_path"), out
        assert Path(out["payload"]["image_path"]).exists()

    def test_operand_extraction_strips_tool_vocabulary(self):
        from app.agents.master_agent import _extract_operand_name
        assert _extract_operand_name(
            "set kaba.jpg as my wallpaper", "set_wallpaper") == "kaba.jpg"

    def test_ambiguity_asks_rather_than_guesses(self, home_with_pictures):
        from app.agents.master_agent import _complete_path_operand
        (home_with_pictures / "kaba.png").write_bytes(b"\x00" * 8)
        # 'kaba' now matches kaba.jpg and kaba.png only if the payload says
        # 'kaba' — build that directly:
        out = _complete_path_operand(
            "set_wallpaper", {"image_path": "kaba"}, "set kaba as my wallpaper")
        assert out.get("ask") and "tell me which one" in out["ask"], out

    def test_multi_path_tools_left_alone(self, home_with_pictures):
        from app.agents.master_agent import _complete_path_operand
        # A tool with TWO missing path params keeps its explicit contract;
        # completion never guesses which operand goes where.
        out = _complete_path_operand(
            "__fake_merge__", {"a": 1}, "merge the reports")
        assert "note" not in out and "ask" not in out

    def test_completion_runs_before_registry_execution(self, home_with_pictures, monkeypatch):
        """Integration: the ToolRegistry branch resolves the bare name and
        the handler receives a REAL path — the 'find' step self-served."""
        import app.cognition.tool_registry as tr_mod
        import app.cognition.tool_matcher  # noqa: F401  (matcher imports ok)
        from app.cognition.action_proposal import ActionProposal
        from app.agents.master_agent import MasterAgentOrchestrator

        seen = {}

        class _StubReg:
            _registry = {"set_wallpaper": object()}

            def execute_registered_tool(self, action_type, payload):
                seen["action_type"] = action_type
                seen["payload"] = dict(payload)
                return {"success": True, "note": "wallpaper set"}

        monkeypatch.setattr(tr_mod, "get_shared_registry", lambda: _StubReg())
        proposal = ActionProposal(
            action_type="set_wallpaper",
            payload={"image_path": "kaba.jpg", "path": "kaba.jpg",
                     "source_path": "kaba.jpg", "file_path": "kaba.jpg"},
            recommendation_reason="test")
        res = MasterAgentOrchestrator.execute_proposal(
            proposal, "set kaba.jpg as my wallpaper").to_dict()
        assert res["execution_status"] == "succeeded", res
        assert seen["payload"]["image_path"].endswith("kaba.jpg")
        assert Path(seen["payload"]["image_path"]).exists()
        # The resolution is reported, not silent.
        assert any("Resolved" in str(a) for a in res["executed_actions"]), res


# ── Generality: the same chain for non-media, non-wallpaper requests ────────


class TestGeneralityBeyondMedia:
    def test_full_cycle_wallpaper_compound_routes_and_resolves(self, monkeypatch, tmp_path):
        """'find the photo and set it as my wallpaper' — the compound
        pattern that broke kaba, in a different domain."""
        import tempfile
        fake_home = Path(tempfile.mkdtemp(prefix="arena_gen_"))
        pics = fake_home / "Pictures"
        pics.mkdir()
        (pics / "kaba.jpg").write_bytes(b"\x00" * 8)
        old = os.environ.get("HOME")
        os.environ["HOME"] = str(fake_home)
        try:
            from app.cognition.tool_matcher import match_control_tool
            m = match_control_tool("find the photo kaba and set it as my wallpaper")
            # The wallpaper tool wins the route and the matcher carries the
            # operand; completion resolves it at execution.
            assert m is not None and m.action_type == "set_wallpaper", m
            from app.agents.master_agent import _complete_path_operand
            out = _complete_path_operand(
                "set_wallpaper", dict(m.payload or {}),
                "find the photo kaba and set it as my wallpaper")
            resolved = out["payload"].get("image_path") or out["payload"].get("path")
            assert resolved and Path(resolved).exists(), out
        finally:
            os.environ["HOME"] = old or str(Path("/home/user"))
            import shutil
            shutil.rmtree(fake_home, ignore_errors=True)
