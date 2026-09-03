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

Contract under test (owner report #5, 2026-09-02):
  * an explicitly supplied root_dir is a CONSTRAINT — a search of one
    folder must never silently return results from other drives (the
    persistent-index test deleted a file, searched its root, and got a
    hit from another indexed drive: a correctness and trust problem);
  * escalation past an explicit root requires the caller's EXPLICIT
    request (allow_escalation=True — the D7 wrong-root recovery, kept
    as a decision, not a silent scope expansion). Recovery from a wrong
    planner root belongs to the replan layer, which sees the honest
    constrained miss;
  * named scopes (root_dir absent) keep the never-fabricate-absence
    escalation (a scope is a planner hint, not an explicit root);
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

def test_explicit_root_dir_miss_is_constrained_by_default(fake_home, tmp_path):
    """Owner report #5: an explicitly supplied root is a CONSTRAINT. The
    file sits in the user's home; the caller searched elsewhere. The
    default answer for that scope is NO MATCHES — a search of one folder
    must never silently return results from other drives."""
    marker = fake_home / "arena_diag_marker_zz"
    marker.write_text("x", encoding="utf-8")
    wrong_root = tmp_path / "elsewhere"
    wrong_root.mkdir()
    try:
        hits = UniversalFilesystem.search_filesystem(
            "arena_diag_marker_zz", root_dir=str(wrong_root))
        assert hits == [], (
            "an explicit root must constrain the search — no silent "
            f"escalation to other drives (got {[h.get('file_path') for h in hits]})")
    finally:
        marker.unlink()


def test_explicit_root_escalates_only_on_explicit_request(fake_home, tmp_path):
    """The D7 wrong-root recovery survives as an EXPLICIT opt-in: the
    caller that guesses a root (and wants recovery, not a constrained
    miss) requests escalation and gets the user-scope hit, tagged."""
    marker = fake_home / "arena_diag_marker_zz"
    marker.write_text("x", encoding="utf-8")
    wrong_root = tmp_path / "elsewhere"
    wrong_root.mkdir()
    try:
        hits = UniversalFilesystem.search_filesystem(
            "arena_diag_marker_zz", root_dir=str(wrong_root),
            allow_escalation=True)
        assert hits, "opted-in wrong-root miss must escalate, not report nothing"
        assert hits[0]["file_name"] == "arena_diag_marker_zz"
        assert hits[0].get("scope_escalated") is True
    finally:
        marker.unlink()


def test_explicit_root_never_leaks_out_of_scope_matches(fake_home, tmp_path):
    """The trust property, stated directly: a file that EXISTS somewhere
    else must not appear in a constrained search's results — even though
    an escalated search would find it."""
    outside = tmp_path / "other_drive" / "music"
    outside.mkdir(parents=True)
    (outside / "needle_xyz.mp3").write_text("x", encoding="utf-8")
    constrained_root = tmp_path / "elsewhere"
    constrained_root.mkdir()

    default = UniversalFilesystem.search_filesystem(
        "needle_xyz", root_dir=str(constrained_root))
    assert default == [], "out-of-scope matches must not leak into a constrained search"

    opted_in = UniversalFilesystem.search_filesystem(
        "needle_xyz", root_dir=str(constrained_root), allow_escalation=True)
    assert any(h["file_name"] == "needle_xyz.mp3" for h in opted_in)
    assert all(h.get("scope_escalated") for h in opted_in), (
        "escalated results must be TAGGED as escalated")


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
    """The payload's root_dir is honored (the search runs THERE) — and,
    by default (owner report #5), a miss is the HONEST constrained
    answer: result_found=False with no out-of-scope matches. The same
    payload with allow_escalation=true recovers the home hit, tagged
    (the D7 wrong-root recovery as an explicit planner decision)."""
    marker = fake_home / "arena_diag_marker_rr"
    marker.write_text("x", encoding="utf-8")
    wrong_root = tmp_path / "not_here"
    wrong_root.mkdir()
    try:
        result = MasterAgentOrchestrator.execute_proposal(
            _proposal({"query": "arena_diag_marker_rr",
                       "root_dir": str(wrong_root)}),
            "Find files matching arena_diag_marker_rr.")
        assert result.execution_status.value == "succeeded"
        assert result.outputs.get("result_found") is False, (
            "a constrained miss is the honest answer for the payload's root")
        assert not (result.outputs.get("matched_files") or [])

        recovered = MasterAgentOrchestrator.execute_proposal(
            _proposal({"query": "arena_diag_marker_rr",
                       "root_dir": str(wrong_root),
                       "allow_escalation": True}),
            "Find files matching arena_diag_marker_rr.")
        assert recovered.outputs.get("result_found") is True, (
            "opted-in wrong-root payload miss must escalate to the user scope")
        matched = recovered.outputs.get("matched_files") or []
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


def test_investigation_probe_uses_extracted_operand_not_the_question(fake_home):
    """D7 live failure (owner run 2026-09-03): the loop's synthesized
    information need carries the WHOLE user sentence as its question.
    _investigation_arguments used to overwrite the matcher's extracted
    operand ('arena_diag_marker_<hex>') with that sentence, so the probe
    searched for a SENTENCE as a filename and honestly returned [] for a
    file that WAS there — the offline control passed only because the
    matcher-forced ACT path honors the payload. Extracted operands must
    win; the raw question is only the fallback."""
    from app.cognition.information_gain import InformationNeed
    from app.cognition.action_selection import (
        InvestigationExecutor,
        InvestigationRegistry,
    )

    marker = fake_home / "arena_diag_marker_live01"
    marker.write_text("x", encoding="utf-8")
    try:
        need = InformationNeed(
            question="Find files matching arena_diag_marker_live01, then tell "
                     "me how many you found.",
            target="user",
            reason="Synthesized from the user's question (no explicit "
                   "information need supplied).",
            priority=0.6,
        )
        plan = InvestigationRegistry().plan(need)
        assert plan is not None and plan.tool == "search_files"
        payload = plan.arguments.get("payload") or {}
        assert payload.get("query") == "arena_diag_marker_live01", (
            "the matcher's extracted operand must not be clobbered by "
            "the raw question")
        result = InvestigationExecutor().execute(plan)
        assert result.success is True
        found = [e.get("file_path") for e in (result.output or [])]
        assert str(marker) in found, (
            "the probe must find the planted marker through the "
            "investigation path, not only the forced-ACT path")
    finally:
        marker.unlink()
