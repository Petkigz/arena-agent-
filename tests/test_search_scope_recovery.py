"""P1 (live 2026-09-01, D7, owner review item 5): a search scoped to the
WRONG root must recover via escalation, and the executor must honor the
payload's scope instead of silently dropping it.

Live incident: the marker was planted in Path.home(); the agent
narrated 'I'll search ... in the Documents folder' and the goal stalled
in waiting_for_evidence — the found path never materialized. Two
deterministic defects made the execution layer fragile no matter which
layer picked the wrong scope:

  * master_agent's search_files handler DROPPED payload['scope'] and
    payload['root_dir'], calling the tool with neither — a payload
    contract leak: a planner that DID pick a scope had it silently
    ignored;
  * the never-fabricate-absence escalation (P0 #12) covered named
    scopes only — an explicit root_dir miss reported 'no matching
    files' with no escalation, so one wrong root could hide a file
    that exists in the user's scope.

Contract under test:
  * an explicit root_dir that MISSES escalates once to the user scope
    before reporting absence (same rule as named scopes — a miss in a
    narrow root is not proof of absence);
  * master_agent honors the payload's scope and root_dir;
  * a payload-less search still defaults to the user's files.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.universal_filesystem import UniversalFilesystem
from app.agents.master_agent import MasterAgentOrchestrator


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    (tmp_path / "Documents").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


def _proposal(payload):
    return SimpleNamespace(action_type="search_files",
                           payload=payload, proposal_id="prop_test")


# ── tool layer: the live D7 shape — wrong explicit root ────────────────

def test_explicit_root_dir_miss_escalates_to_user_scope(fake_home, tmp_path):
    """The live shape: something searched a root that does not contain
    the file while the file sits in the user's home. Escalation must
    recover it — never 'no matching files'."""
    marker = fake_home / "arena_diag_marker_zz"
    marker.write_text("x", encoding="utf-8")
    wrong_root = tmp_path / "elsewhere"
    wrong_root.mkdir()
    try:
        hits = UniversalFilesystem.search_filesystem(
            "arena_diag_marker_zz", root_dir=str(wrong_root))
        assert hits, "wrong-root miss must escalate, not report nothing"
        assert hits[0]["file_name"] == "arena_diag_marker_zz"
        assert hits[0].get("scope_escalated") is True
    finally:
        marker.unlink()


def test_explicit_root_dir_hit_is_unchanged(tmp_path):
    """The pinned behavior stays: a root_dir that CONTAINS the match
    returns it without scope tagging."""
    d = tmp_path / "somewhere"
    d.mkdir()
    (d / "needle.txt").write_text("x")
    hits = UniversalFilesystem.search_filesystem(
        "needle", root_dir=str(d))
    assert hits and hits[0]["file_name"] == "needle.txt"
    assert "scope" not in hits[0]


# ── executor layer: payload scope/root_dir are honored ────────────────

def test_master_agent_honors_payload_scope(fake_home):
    """A planner-chosen scope (e.g. 'documents' — the live narration) is
    passed through. The file lives ONLY in Music: a honored documents
    scope MISSES and escalates (scope_escalated=True); a dropped scope
    would find it directly as all_user_files with NO escalation flag —
    the flag is what distinguishes honored from dropped."""
    (fake_home / "Music").mkdir(exist_ok=True)
    marker = fake_home / "Music" / "arena_diag_marker_qq.mp3"
    marker.write_text("x", encoding="utf-8")
    try:
        result = MasterAgentOrchestrator.execute_proposal(
            _proposal({"query": "arena_diag_marker_qq",
                       "scope": "documents"}),
            "Find files matching arena_diag_marker_qq, then tell me "
            "how many you found.")
        assert result.execution_status.value == "succeeded"
        assert result.outputs.get("result_found") is True
        matched = result.outputs.get("matched_files") or []
        assert matched, "the action string alone is not the ground truth"
        assert matched[0].get("scope") == "documents", (
            "the payload's named scope must be honored")
        assert matched[0].get("scope_escalated") is True
    finally:
        marker.unlink()


def test_master_agent_honors_payload_root_dir(fake_home, tmp_path):
    """The payload's root_dir is honored (the search runs THERE first) —
    and a root_dir miss escalates instead of fabricating absence: the
    file in home is recovered with scope_escalated=True."""
    marker = fake_home / "arena_diag_marker_rr"
    marker.write_text("x", encoding="utf-8")
    wrong_root = tmp_path / "not_here"
    wrong_root.mkdir()
    try:
        result = MasterAgentOrchestrator.execute_proposal(
            _proposal({"query": "arena_diag_marker_rr",
                       "root_dir": str(wrong_root)}),
            "Find files matching arena_diag_marker_rr.")
        assert result.outputs.get("result_found") is True, (
            "wrong-root payload miss must escalate to the user scope")
        matched = result.outputs.get("matched_files") or []
        assert matched
        assert matched[0].get("scope_escalated") is True
    finally:
        marker.unlink()


def test_master_agent_search_without_scope_still_uses_user_files(fake_home):
    """Regression guard: a payload with just a query searches the user's
    files (all_user_files) — the behavior that works offline today."""
    marker = fake_home / "arena_diag_marker_ss"
    marker.write_text("x", encoding="utf-8")
    try:
        result = MasterAgentOrchestrator.execute_proposal(
            _proposal({"query": "arena_diag_marker_ss"}),
            "Find files matching arena_diag_marker_ss.")
        assert result.outputs.get("result_found") is True
    finally:
        marker.unlink()
