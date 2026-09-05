"""Search autonomy (live owner report 2026-09-05): 'find the file kaba and
play it'.

The assistant must SELF-SERVE the information it can obtain with its own
tools instead of asking the owner. The live failure chain, reproduced and
fixed:

  1. the search query carried instruction verbs and discourse ('kaba on
     system play') — a phrase no filename ever contains, so the search
     was a GUARANTEED miss even though the file existed;
  2. the guaranteed miss cascaded into a replan that executed
     resize_image with an empty placeholder payload, and the raw
     missing-parameter validation error became the owner-facing reply;
  3. with zero evidence in context, the reply generation asked the owner
     to confirm the file type — information a single search would have
     revealed.

These tests pin the general fixes: clean query extraction, a token-tier
search fallback for contaminated queries, no placeholder execution in
replans, honest partial-completion reporting for ungroundable steps
(playback), and preserved discovery breadth.
"""

import re

import pytest

from app.cognition.goal_interpreter import (
    SemanticGoalInterpreter,
    extract_search_query,
)
from app.cognition.goal_replanner import GoalReplanner
from app.tools.manifest import (
    missing_required_payload_keys,
    payload_required_keys,
)
from app.tools.universal_filesystem import UniversalFilesystem


# ── 1. Query extraction: content terms only ─────────────────────────────────


class TestExtractSearchQueryHygiene:
    def test_compound_find_and_play_yields_the_filename_only(self):
        assert extract_search_query("find the file kaba and play it") == "kaba"

    def test_device_discourse_verbs_are_stripped(self):
        # 'on'/'play' are instruction/discourse, never filename content.
        q = extract_search_query("find the file kaba on my system and play it")
        assert "kaba" in q.split()
        assert "play" not in q.split()
        assert "on" not in q.split()

    def test_apposition_marker_is_stripped(self):
        q = extract_search_query("do i have a song called kaba on my pc")
        assert "called" not in q.split()
        assert "kaba" in q.split()

    def test_existing_extraction_pins_unchanged(self):
        # Standing routing ground truth: these queries must keep their shape.
        assert extract_search_query("find document report.pdf") == "document report.pdf"
        assert extract_search_query(
            "find the file matching goal_verifier, then tell me how many you found"
        ) == "goal_verifier"


# ── 2. Token-tier search fallback ───────────────────────────────────────────


@pytest.fixture()
def media_tree(tmp_path):
    (tmp_path / "music").mkdir()
    (tmp_path / "music" / "Kaba - Song.mp3").write_bytes(b"x" * 10)
    (tmp_path / "music" / "Another Song.mp3").write_bytes(b"y" * 10)
    (tmp_path / "music" / "system_info.txt").write_text("z")
    (tmp_path / "kaba").mkdir()  # a directory literally named kaba
    (tmp_path / "kaba" / "notes.md").write_text("n")
    return tmp_path


class TestTokenTierSearchFallback:
    def test_contaminated_query_still_finds_the_file(self, media_tree):
        # The exact query the old extraction produced — the whole phrase can
        # never be a filename substring, but its distinctive token must hit.
        res = UniversalFilesystem.search_filesystem(
            "kaba on system play", root_dir=str(media_tree)
        )
        names = {r["file_name"] for r in res}
        assert "Kaba - Song.mp3" in names
        assert "kaba" in names  # directories are searched too
        assert all(r["match"] == "token" and r.get("matched_token") == "kaba" for r in res)

    def test_generic_type_token_does_not_flood_results(self, media_tree):
        # 'song' is content-type vocabulary: it must not match alone, or the
        # answer is every song on the machine instead of the named one.
        res = UniversalFilesystem.search_filesystem(
            "song kaba", root_dir=str(media_tree)
        )
        names = {r["file_name"] for r in res}
        assert "Kaba - Song.mp3" in names
        assert "Another Song.mp3" not in names

    def test_device_word_does_not_outrank_content(self, media_tree):
        # 'system' is device discourse — excluded from the token tier so it
        # cannot drag in unrelated system-named files ahead of the content.
        res = UniversalFilesystem.search_filesystem(
            "kaba system", root_dir=str(media_tree)
        )
        assert {r["file_name"] for r in res} == {"Kaba - Song.mp3", "kaba"}

    def test_phrase_pass_still_ranks_above_token_tier(self, media_tree):
        res = UniversalFilesystem.search_filesystem("kaba", root_dir=str(media_tree))
        assert res and all(r["match"] == "exact" for r in res)

    def test_honest_miss_still_reported(self, media_tree):
        res = UniversalFilesystem.search_filesystem(
            "zzzznotpresent", root_dir=str(media_tree)
        )
        assert res == []

    def test_filename_shaped_query_is_never_decomposed(self, media_tree):
        """A precise filename query must stay precise: decomposing
        'zz_test_move_kaba.mp3' into words ('test', 'move', 'kaba') matches
        unrelated paths and — worse — can fill the result budget before the
        walk reaches the real exact match (live regression found by the
        full suite, 2026-09-05: move-by-bare-name resolved to tests/ and
        pytest.ini instead of the file)."""
        res = UniversalFilesystem.search_filesystem(
            "zz_test_move_kaba.mp3", root_dir=str(media_tree), max_results=4
        )
        # 'test' is a token of the decomposed name; none of these may match.
        names = {r["file_name"] for r in res}
        assert "system_info.txt" not in names
        assert all(r["match"] == "exact" for r in res), res
        # And a filename that EXISTS in a later-walked subdir is still
        # found exactly (no early stop on provisional token hits).
        (media_tree / "zzdir").mkdir()
        (media_tree / "zzdir" / "zz_test_move_kaba.mp3").write_bytes(b"m")
        res = UniversalFilesystem.search_filesystem(
            "zz_test_move_kaba.mp3", root_dir=str(media_tree), max_results=4
        )
        assert {r["file_name"] for r in res} == {"zz_test_move_kaba.mp3"}
        assert all(r["match"] == "exact" for r in res)


# ── 3. Manifest required-keys introspection ─────────────────────────────────


class TestManifestRequiredKeys:
    def test_required_keys_exposed_without_execution(self):
        assert set(payload_required_keys("resize_image")) == {
            "image_path_str", "target_width", "target_height"
        }

    def test_zero_arg_tools_require_nothing(self):
        # Operand-free capabilities must never be gated as placeholders.
        assert payload_required_keys("list_apps") == []

    def test_placeholder_payload_detected(self):
        assert missing_required_payload_keys(
            "resize_image", {"query": "find the file kaba and play it"}
        ) == ["image_path_str", "target_width", "target_height"]

    def test_alias_covers_required_key(self):
        # 'image_path' is the public alias of 'image_path_str'.
        missing = missing_required_payload_keys(
            "resize_image", {"image_path": "a.png", "target_width": 8, "target_height": 6}
        )
        assert missing == []

    def test_unknown_action_is_never_a_placeholder(self):
        assert missing_required_payload_keys("__no_such_tool__", {}) == []


# ── 4. Replanner: no placeholder execution ──────────────────────────────────


class TestReplannerPlaceholderGate:
    def test_placeholder_candidate_is_detected(self):
        assert GoalReplanner._is_operand_placeholder({
            "action_type": "resize_image",
            "payload": {"query": "find the file kaba and play it"},
        }) is True

    def test_candidate_with_extracted_operands_passes(self):
        assert GoalReplanner._is_operand_placeholder({
            "action_type": "search_files",
            "payload": {"query": "kaba"},
        }) is False

    def test_zero_arg_candidate_passes(self):
        assert GoalReplanner._is_operand_placeholder({
            "action_type": "list_apps",
            "payload": {"query": "what is installed"},
        }) is False

    def test_failed_find_and_play_never_replans_into_operandless_tools(self):
        # The deterministic candidate set for the owner's exact request used
        # to contain resize_image / move_file / read_document placeholders.
        goal_rep = SemanticGoalInterpreter.interpret_goal(
            "find the file kaba on my system and play it", complexity="fast"
        )
        placeholders = [
            c for c in goal_rep.recommended_candidates
            if GoalReplanner._is_operand_placeholder(c)
        ]
        # They may exist as discovery signals, but the replan filter must
        # reject every one of them.
        assert all(
            GoalReplanner._is_operand_placeholder(c) for c in placeholders
        )
        replan_pool = [
            c for c in goal_rep.recommended_candidates
            if not GoalReplanner._is_operand_placeholder(c)
        ]
        assert "search_files" in {c.get("action_type") for c in replan_pool}
        assert "resize_image" not in {c.get("action_type") for c in replan_pool}


# ── 5. Discovery breadth preserved (regression guard) ───────────────────────


class TestDiscoveryBreadthPreserved:
    def test_compress_discovery_still_proposed(self):
        # P0 #3 arc: the manifest discovery must still reach beyond the
        # domain baseline. The placeholder gate lives in the REPLANNER
        # only — primary candidate generation keeps its breadth (the
        # executor's per-action branches resolve bare names themselves).
        goal_rep = SemanticGoalInterpreter.interpret_goal(
            "compress my vacation photos into a zip", complexity="fast"
        )
        actions = {c.get("action_type") for c in goal_rep.recommended_candidates}
        assert "compress_files" in actions


# ── 6. Honest partial-completion reporting ──────────────────────────────────


class TestHonestPlaybackReporting:
    def _executor_note_fires(self, user_text):
        from app.agents.master_agent import _MEDIA_VERB_RE, _no_media_playback_capability
        return bool(_MEDIA_VERB_RE.search(user_text)) and _no_media_playback_capability()

    def test_playback_verbs_trigger_the_honest_note(self):
        for text in (
            "find the file kaba and play it",
            "find kaba and watch it",
            "locate the recording and listen to it",
        ):
            assert self._executor_note_fires(text), text

    def test_non_media_requests_do_not_get_the_note(self):
        assert not self._executor_note_fires("find the file kaba")
        assert not self._executor_note_fires("find document report.pdf and summarize it")

    def test_note_is_self_limiting_when_playback_tool_registered(self):
        # The day a playback capability is actually installed, the honest
        # 'cannot play' note must disappear — it tracks reality.
        from app.cognition.tool_registry import get_shared_registry
        from app.agents.master_agent import _no_media_playback_capability
        assert _no_media_playback_capability() is True  # precondition
        reg = get_shared_registry()
        reg._registry["play_media_file"] = object()  # dynamic install
        try:
            assert _no_media_playback_capability() is False
        finally:
            reg._registry.pop("play_media_file", None)


# ── 7. Full-cycle integration: the owner's exact request ────────────────────


class TestFindAndPlayFullCycle:
    def test_search_finds_file_and_reports_missing_playback_honestly(self, tmp_path):
        """End-to-end: 'find the file kaba and play it' with the file present.

        The assistant must (a) route to search_files, (b) actually find the
        file, (c) reply with the located path, and (d) state honestly that
        playback is not a registered capability — never ask the owner for
        self-serveable information."""
        import time
        from pathlib import Path

        from app.cognition.runtime import CognitiveRuntime

        # The cycle's search runs over the user's files; plant a decoy-named
        # real media file in a fresh HOME directory (created via mkdtemp so
        # it is outside the repo and unique per run).
        import tempfile
        fake_home = Path(tempfile.mkdtemp(prefix="arena_kaba_"))
        media_dir = fake_home / "Music"
        media_dir.mkdir()
        media_file = media_dir / "Kaba - Song.mp3"
        media_file.write_bytes(b"\x00" * 16)

        old_home = Path.home()
        import os
        os.environ["HOME"] = str(fake_home)
        try:
            rt = CognitiveRuntime.get_instance()
            result = rt.process_cognitive_cycle(
                user_text="find the file kaba on my system and play it",
                complexity="fast",
            )
        finally:
            os.environ["HOME"] = str(old_home)
            import shutil
            shutil.rmtree(fake_home, ignore_errors=True)

        assert result.get("action_type") == "search_files"
        executed = " ".join(str(a) for a in (result.get("executed_actions") or []))
        reply = str(result.get("assistant_reply") or "")
        assert "Kaba - Song.mp3" in executed, executed
        assert "playback capability" in executed, executed
        # The reply must not interrogate the owner for information the
        # search itself just obtained (the live bug: 'can you confirm if
        # kaba is a specific type of file (e.g., MP3, AVI)?').
        assert not re.search(r"confirm.{0,40}(type of file|MP3|AVI)", reply, re.I)
        # And it must never leak a raw tool validation error.
        assert "resize_image" not in reply
        assert "missing required parameter" not in reply

    def test_miss_is_honest_not_fabricated(self):
        """No kaba anywhere: the cycle must report the miss without
        executing operand-less tools and without inventing results."""
        from app.cognition.runtime import CognitiveRuntime
        rt = CognitiveRuntime.get_instance()
        result = rt.process_cognitive_cycle(
            user_text="find the file zzqqx_not_anywhere and play it",
            complexity="fast",
        )
        executed = " ".join(str(a) for a in (result.get("executed_actions") or []))
        reply = str(result.get("assistant_reply") or "")
        assert "resize_image" not in executed + reply
        assert "missing required parameter" not in executed + reply
        assert "playback capability" in executed  # still honest about 'play'
