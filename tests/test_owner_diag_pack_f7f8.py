"""F7/F8: the owner diagnostics pack must measure what it claims.

F7 (D7, live 2026-09-01): the control searched 'goal_verifier' — a REPO
file — but the owner's repo lives on F:\\, outside the C:\\Users\\<owner>
scope the search walks, so the control measured the repo's LOCATION, not
the search capability. The searched term is now a unique marker planted
in the OWNER'S HOME (in scope on every platform), deleted after the
check. Ground truth is the FOUND PATH appearing in the tool's results —
never the agent's own success claim, and never a mere query mention (the
query name is known to the agent; only the found path is evidence).

F8 (D2/D6): failures must be attributable from the paste-back block.
The live failures were 'mean missing from reply' (D2) and 'plan document
instead of an installed tool' (D6) — the REPLY is the evidence, so the
detail lines must carry reply excerpts.

These tests run the pack functions directly (the chat battery runs
offline in this sandbox; the offline baseline for D7 is PASS).
"""

import logging
from unittest.mock import patch

import scripts.owner_diagnostics as od

# The pack disables INFO logging at import for readable output; restore
# it so the rest of the session logs normally.
logging.disable(logging.NOTSET)


def _fake_chat_result(actions=None, reply=""):
    return {
        "success": True,
        "assistant_reply": reply,
        "executed_actions": actions or [],
        "goal_lifecycle_state": "achieved",
    }


# ── F7: the marker control ──────────────────────────────────────────────

def test_d7_plants_a_home_marker_and_finds_it():
    """Real offline run: the marker is planted in HOME (always in scope),
    the search finds it, and the file is cleaned up afterwards."""
    status, detail = od.d7_control_file_search()
    assert status == "pass", detail
    assert "marker in home" in detail


def test_d7_cleans_the_marker_up():
    import glob
    import pathlib
    before = set(glob.glob(str(pathlib.Path.home() / "arena_diag_marker_*")))
    od.d7_control_file_search()
    after = set(glob.glob(str(pathlib.Path.home() / "arena_diag_marker_*")))
    assert after == before, f"marker files left behind: {after - before}"


def test_d7_ground_truth_is_the_found_path_not_the_query():
    """A search that RAN for the name but produced no found path is NOT a
    pass — the query mention alone is not evidence (the offline baseline
    for this control is a real find)."""
    with patch.object(od, "_chat", return_value=_fake_chat_result(
        actions=["search_files: query=arena_diag_marker_x"],
        reply="I searched for arena_diag_marker_x but found nothing.")):
        status, detail = od.d7_control_file_search()
    assert status == "fail", detail


def test_d7_fails_when_a_browser_is_touched():
    with patch.object(od, "_chat", return_value=_fake_chat_result(
        actions=["browser_open google.com"],
        reply="I found things.")):
        status, detail = od.d7_control_file_search()
    assert status == "fail", detail


def test_d7_passes_only_on_a_real_found_path():
    """The found marker path in the tool results is the ground truth."""
    import pathlib
    # Run with a mocked chat that reports the REAL marker path — plant it
    # first so the path exists and matches what d7 planted.
    captured = {}

    def _capture(task, complexity="fast"):
        captured["task"] = task
        marker_name = task.split("matching ")[1].split(",")[0]
        marker_path = pathlib.Path.home() / marker_name
        return _fake_chat_result(
            actions=[f"Found local file '{marker_name}' at {marker_path}."],
            reply=f"Found it at {marker_path}.")

    with patch.object(od, "_chat", side_effect=_capture):
        status, detail = od.d7_control_file_search()
    assert status == "pass", detail


def test_d7_detail_carries_the_executed_actions():
    """A live miss is only attributable if the paste-back shows WHICH
    actions executed (the 2026-09-01 run truncated the reply excerpt at
    '[NATIVE OS ACTIONS E' — exactly where the evidence was)."""
    with patch.object(od, "_chat", return_value=_fake_chat_result(
        actions=["Searched local filesystem for 'x' (no matching files found)."],
        reply="I'll look for that file now." * 20)):
        status, detail = od.d7_control_file_search()
    assert status == "fail"
    assert "actions=" in detail
    assert "Searched local filesystem" in detail
    # The actions must survive record()'s 300-char detail cap — they are
    # positioned before the reply excerpt so truncation eats only the tail.
    assert detail.index("actions=") < 300


# ── F8: reply excerpts for D2/D6 ────────────────────────────────────────

def test_d2_detail_carries_a_reply_excerpt():
    """The live D2 failure ('mean missing from reply') is only attributable
    if the paste-back shows what the reply DID say."""
    reply = "I analyzed the CSV file for you. The data looks clean."
    with patch.object(od, "_chat", return_value=_fake_chat_result(
        actions=["analyze_data executed"],
        reply=reply)):
        status, detail = od.d2_csv_analysis()
    assert status == "fail"  # the mean is not in the reply
    assert "reply=" in detail
    assert "I analyzed the CSV" in detail


def test_d6_detail_carries_a_reply_excerpt_when_tool_not_installed():
    reply = "Here is my plan for the reverse_words tool."
    with patch.object(od, "_chat", return_value=_fake_chat_result(
        reply=reply)), \
         patch("app.cognition.tool_registry.get_shared_registry") as reg:
        reg.return_value.effective_capability.return_value = None
        status, detail = od.d6_self_evolution()
    assert status == "fail"
    assert "reply=" in detail
    assert "my plan" in detail


def test_d6_detail_carries_a_reply_excerpt_when_tool_misbehaves():
    reply = "I created and tested the reverse_words tool for you."
    with patch.object(od, "_chat", return_value=_fake_chat_result(
        reply=reply)), \
         patch("app.cognition.tool_registry.get_shared_registry") as reg:
        reg.return_value.effective_capability.return_value = {"name": "reverse_words"}
        reg.return_value.execute_registered_tool.return_value = {
            "result": "one two three"}  # did NOT reverse
        status, detail = od.d6_self_evolution()
    assert status == "fail"
    assert "reply=" in detail
    assert "created and tested" in detail
