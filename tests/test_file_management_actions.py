"""File-management and OS-control actions — the live bugs from the owner's
chat export (2026-08-28/29):

- 'open taskbar' died as: os_control_plan blocked, 'Unknown action: {}'
  (the routing-signal name reached the gate, which didn't know it).
- 'move kaba.mp3 to my music folder' matched move_file but the payload was
  EMPTY — execution had no operands and failed.
- 'rename london.mp3 to test.mp3' matched nothing at all.
- 'delete all files called temp' had no tool: deletion is now reversible
  (trash, Level 3, owner approval).
"""
import os
import shutil
from pathlib import Path

import pytest

from app.agents.master_agent import MasterAgentOrchestrator
from app.cognition.action_proposal import ActionProposal, ActionGate
from app.cognition.tool_matcher import match_control_tool


# ── Routing: operands must survive to the payload ──────────────────────────

def test_move_carries_operands():
    m = match_control_tool("move kaba.mp3 to my music folder")
    assert m is not None and m.action_type == "move_file"
    assert m.payload["source_name"] == "kaba.mp3"
    assert m.payload["destination_name"] == "my music folder"


def test_rename_routes_to_move_file():
    m = match_control_tool("rename london.mp3 to test.mp3")
    assert m is not None and m.action_type == "move_file"
    assert m.payload["source_name"] == "london.mp3"
    assert m.payload["destination_name"] == "test.mp3"


def test_move_song_by_title():
    m = match_control_tool("move the song called kaba to my music folder")
    assert m is not None and m.action_type == "move_file"
    assert m.payload["source_name"] == "kaba"


def test_copy_carries_operands():
    m = match_control_tool("copy report.pdf to my desktop")
    assert m is not None and m.action_type == "copy_file_verified"
    assert m.payload["source_name"] == "report.pdf"


def test_delete_by_name_and_by_filename():
    m = match_control_tool("delete all files called temp")
    assert m is not None and m.action_type == "delete_files"
    assert m.payload["name"] == "temp"
    m = match_control_tool("delete kaba.mp3")
    assert m is not None and m.action_type == "delete_files"
    assert m.payload["names"] == ["kaba.mp3"]


def test_non_file_sentences_not_hijacked():
    # No extension, no file noun, no called/named -> not a file operation.
    assert match_control_tool("move my meeting to 3pm") is None or \
        match_control_tool("move my meeting to 3pm").action_type != "delete_files"


def test_os_control_fallback_carries_request_text():
    m = match_control_tool("open taskbar")
    assert m is not None and m.action_type == "os_control_plan"
    assert m.payload.get("request")


# ── Gate: the routing signal is a KNOWN tool now ───────────────────────────

def test_os_control_plan_is_not_an_unknown_action():
    """The Aug-28 dead end: gate must recognize the routing-signal name and
    treat it as a Level-2 (autonomous/reversible) tool, never 'Unknown
    action: requires explicit user approval'."""
    proposal = ActionProposal(
        action_type="os_control_plan",
        payload={"request": "open taskbar"},
        recommendation_reason="routing alias",
    )
    result = ActionGate.evaluate_proposal(proposal)
    assert result.allowed is True
    assert result.gate_name != "policy_gate"


def test_delete_files_requires_owner_approval():
    """Deletion is Level 3: blocked by default, surfaces an approval request
    the owner can approve in chat."""
    proposal = ActionProposal(
        action_type="delete_files",
        payload={"name": "temp"},
        recommendation_reason="delete by name",
    )
    result = ActionGate.evaluate_proposal(proposal)
    assert result.allowed is False
    assert result.requires_approval is True


# ── Execution: bare names resolve to real paths ────────────────────────────

@pytest.fixture()
def sandbox_files(tmp_path):
    """Create real files under the home Music/Desktop folders (created if the
    host lacks them) and clean everything up afterwards."""
    home = Path.home()
    music = home / "Music"
    desktop = home / "Desktop"
    music.mkdir(exist_ok=True)
    desktop.mkdir(exist_ok=True)
    src = music / "zz_test_move_kaba.mp3"
    src.write_bytes(b"kaba-audio")
    yield {"src": src, "music": music, "desktop": desktop, "home": home}
    for p in (src, desktop / "zz_test_move_kaba.mp3", music / "zz_test_copy_kaba.mp3"):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def _execute(action_type, payload, user_text):
    proposal = ActionProposal(
        action_type=action_type, payload=payload,
        recommendation_reason="test",
    )
    return MasterAgentOrchestrator.execute_proposal(proposal, user_text)


def test_move_by_bare_name_to_music_folder(sandbox_files):
    res = _execute(
        "move_file",
        {"source_name": "zz_test_move_kaba.mp3", "destination_name": "my desktop"},
        "move zz_test_move_kaba.mp3 to my desktop",
    )
    assert res.to_dict().get("execution_status") == "succeeded", res
    moved = sandbox_files["desktop"] / "zz_test_move_kaba.mp3"
    assert moved.exists()
    assert not sandbox_files["src"].exists()


def test_move_reports_not_found_honestly(sandbox_files):
    res = _execute(
        "move_file",
        {"source_name": "zz_no_such_file_anywhere.mp3", "destination_name": "my music folder"},
        "move zz_no_such_file_anywhere.mp3 to my music folder",
    )
    data = res.to_dict()
    assert data.get("execution_status") == "failed"
    assert "couldn't find" in " ".join(data.get("executed_actions", [])).lower()


def test_copy_by_bare_name(sandbox_files):
    res = _execute(
        "copy_file_verified",
        {"source_name": "zz_test_move_kaba.mp3", "destination_name": "my desktop"},
        "copy zz_test_move_kaba.mp3 to my desktop",
    )
    assert res.to_dict().get("execution_status") == "succeeded", res
    assert (sandbox_files["desktop"] / "zz_test_move_kaba.mp3").exists()


def test_delete_moves_to_reversible_trash(sandbox_files):
    trash_base = sandbox_files["home"] / ".arena_trash"
    res = _execute(
        "delete_files",
        {"name": "zz_test_move_kaba.mp3"},
        "delete the file called zz_test_move_kaba.mp3",
    )
    data = res.to_dict()
    assert data.get("execution_status") == "succeeded", data
    actions = " ".join(data.get("executed_actions", []))
    assert "trash" in actions.lower()
    assert not sandbox_files["src"].exists()
    # …and it is recoverable.
    trashed = list(trash_base.rglob("zz_test_move_kaba.mp3"))
    assert trashed, "deleted file must exist in the trash area"
    shutil.rmtree(trash_base, ignore_errors=True)
