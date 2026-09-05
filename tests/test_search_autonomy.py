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


# ── 6. Playback as a REAL capability (owner report 2026-09-05, round 2) ─────
#
# The PC has media players and the agent has OS control: opening the found
# file with its default application IS playback. Reporting playback as a
# missing capability under-claimed the control the system actually has.
# The 'No media playback capability' note from round 18 stays as a guard
# that self-extinguishes the moment a playback-advertising tool exists —
# which open_file now does.


class TestPlaybackThroughOpenFile:
    def _exec(self, payload, user_text):
        from app.cognition.action_proposal import ActionProposal
        from app.agents.master_agent import MasterAgentOrchestrator
        proposal = ActionProposal(
            action_type="open_file", payload=payload,
            recommendation_reason="test",
        )
        return MasterAgentOrchestrator.execute_proposal(proposal, user_text).to_dict()

    def test_open_file_tool_opens_with_platform_opener(self, tmp_path, monkeypatch):
        """The real code path: a fake platform opener receives the file."""
        import app.tools.universal_filesystem as ufs
        target = tmp_path / "kaba.mp3"
        target.write_bytes(b"x")
        calls = []
        monkeypatch.setattr(
            ufs.subprocess, "Popen",
            lambda cmd, **kw: calls.append(cmd) or type("P", (), {"poll": lambda s: 0})())
        res = ufs.UniversalFilesystem.open_with_default_app(str(target))
        assert res["success"] is True, res
        assert res["opener"] == "xdg-open"
        assert calls == [["xdg-open", str(target)]]

    def test_open_file_honest_failure_names_the_reason(self, tmp_path):
        import app.tools.universal_filesystem as ufs
        target = tmp_path / "kaba.mp3"
        target.write_bytes(b"x")
        res = ufs.UniversalFilesystem.open_with_default_app(str(target))
        # This sandbox has no xdg-open: the failure must name exactly that,
        # never fabricate success. (On Windows os.startfile exists.)
        assert res["success"] is False
        assert "open" in str(res.get("error", "")).lower()

    def test_open_file_requires_a_path(self):
        import app.tools.universal_filesystem as ufs
        res = ufs.UniversalFilesystem.open_with_default_app("")
        assert res["success"] is False

    def test_play_by_bare_name_finds_then_opens(self, monkeypatch):
        """'play kaba' — the resolution search is the 'find' step; the open
        is the 'play' step. One action, real evidence, no clarifying
        question about file types the search itself reveals."""
        import app.tools.universal_filesystem as ufs
        opened = []
        monkeypatch.setattr(
            ufs.UniversalFilesystem, "open_with_default_app",
            classmethod(lambda cls, p: opened.append(p) or {
                "success": True, "file_path": p, "file_name": p.rsplit("/", 1)[-1],
                "opener": "stub", "note": "opened",
            }))
        import tempfile, shutil
        from pathlib import Path
        fake_home = Path(tempfile.mkdtemp(prefix="arena_open_"))
        media = fake_home / "Music"
        media.mkdir()
        (media / "Kaba - Song.mp3").write_bytes(b"\x00" * 8)
        old_home = Path.home()
        import os
        os.environ["HOME"] = str(fake_home)
        try:
            d = self._exec({"name": "kaba"}, "play kaba")
        finally:
            os.environ["HOME"] = str(old_home)
            shutil.rmtree(fake_home, ignore_errors=True)
        assert d["execution_status"] == "succeeded", d
        assert len(opened) == 1 and "Kaba - Song.mp3" in opened[0]
        assert "Kaba - Song.mp3" in " ".join(d["executed_actions"])
        assert "opened it with your default application" in " ".join(d["executed_actions"])

    def test_genuine_ambiguity_asks_which_file(self, monkeypatch):
        """Two kaba files = the one case where asking is correct."""
        import tempfile, shutil
        from pathlib import Path
        import os
        fake_home = Path(tempfile.mkdtemp(prefix="arena_ambig_"))
        media = fake_home / "Music"
        media.mkdir()
        (media / "kaba.mp3").write_bytes(b"\x00")
        (media / "kaba video.mp4").write_bytes(b"\x00")
        old_home = Path.home()
        os.environ["HOME"] = str(fake_home)
        try:
            d = self._exec({"name": "kaba"}, "play kaba")
        finally:
            os.environ["HOME"] = str(old_home)
            shutil.rmtree(fake_home, ignore_errors=True)
        assert d["execution_status"] == "failed"
        assert "tell me which one" in " ".join(d["executed_actions"])

    def test_miss_is_honest_not_fabricated(self):
        d = self._exec({"name": "zzqqx_not_anywhere"}, "play zzqqx_not_anywhere")
        assert d["execution_status"] == "failed"
        assert "couldn't find any file matching" in " ".join(d["executed_actions"])

    def test_media_playback_capability_now_resolves(self):
        """The capability ladder must see playback as backed — no ask-gate
        for 'find X and play it' when the control exists."""
        from app.cognition.runtime import CognitiveRuntime
        rt = CognitiveRuntime.get_instance()
        cap_map, _status, unresolved = rt._resolve_capability_status(
            required_capabilities=["filesystem.search", "media.playback"],
            target_domain="filesystem",
        )
        assert cap_map.get("media.playback") is True
        assert not unresolved

    def test_playback_note_self_extinguished_by_open_file(self):
        """The round-18 'No media playback capability' note must NOT fire
        now that open_file advertises playback — it tracked reality, and
        reality gained the capability."""
        from app.agents.master_agent import _no_media_playback_capability
        assert _no_media_playback_capability() is False

    def test_playback_note_would_fire_without_any_playback_tool(self, monkeypatch):
        """Guard: if a build genuinely lacks playback, the note fires."""
        import app.tools.manifest as manifest_mod
        import app.agents.master_agent as ma

        def bare_manifest():
            return {
                name: entry
                for name, entry in manifest_mod.get_tool_manifest().items()
                if name != "open_file"
            }
        monkeypatch.setattr(manifest_mod, "get_tool_manifest", bare_manifest)
        # master_agent imports the getter inside the function — patch the
        # module attribute it resolves from.
        import app.cognition.tool_registry as tr_mod
        monkeypatch.setattr(
            tr_mod, "get_shared_registry",
            lambda: type("R", (), {"_registry": {}})())
        assert ma._no_media_playback_capability() is True


# ── 7. Routing pins for the playback path ───────────────────────────────────


class TestPlaybackRoutingPins:
    def test_play_requests_route_to_open_file(self):
        from app.cognition.tool_matcher import match_control_tool
        for text, expect_name in (
            ("find the file kaba and play it", "kaba"),
            ("find the file kaba on my system and play it", "kaba"),
            ("play kaba", "kaba"),
            ("play kaba.mp3", "kaba.mp3"),
            ("watch the video kaba", "kaba"),
            ("listen to the song kaba", "kaba"),
            ("open kaba.mp3", "kaba.mp3"),
        ):
            m = match_control_tool(text)
            assert m is not None and m.action_type == "open_file", (text, m)
            assert m.payload.get("name") == expect_name or m.payload.get("file_path") == expect_name, (text, m.payload)

    def test_app_launch_not_stolen_by_open_file(self):
        """'open chrome' is an APPLICATION launch; open_file must not win
        via its name stem 'open' (the lone-control-verb name-bonus rule)."""
        from app.cognition.tool_matcher import match_control_tool
        m = match_control_tool("open chrome")
        assert m is None or m.action_type != "open_file"
        m = match_control_tool("open notepad")
        assert m is None or m.action_type != "open_file"

    def test_non_media_find_still_routes_to_search(self):
        from app.cognition.tool_matcher import match_control_tool
        m = match_control_tool("find the file kaba")
        assert m is not None and m.action_type == "search_files"

    def test_interpreter_models_playback_goal(self):
        from app.cognition.goal_interpreter import SemanticGoalInterpreter
        gr = SemanticGoalInterpreter.interpret_goal(
            "find the file kaba and play it", complexity="fast")
        assert gr.target_domain == "filesystem"
        assert "media.playback" in gr.required_capabilities
        assert "open_file" in {c.get("action_type") for c in gr.recommended_candidates}
        # Without the consumption verb the goal stays a plain search.
        gr2 = SemanticGoalInterpreter.interpret_goal(
            "find the file kaba", complexity="fast")
        assert "media.playback" not in gr2.required_capabilities


# ── 8. Full-cycle integration: the owner's exact request ────────────────────


class TestFindAndPlayFullCycle:
    def test_find_and_play_opens_the_file_end_to_end(self, monkeypatch):
        """'find the file kaba and play it' with the file present: route to
        open_file, resolve by real search, open with the default app, and
        report the found path — never ask the owner for the file type."""
        import tempfile, shutil, os
        from pathlib import Path
        import app.tools.universal_filesystem as ufs
        from app.cognition.runtime import CognitiveRuntime

        opened = []
        monkeypatch.setattr(
            ufs.UniversalFilesystem, "open_with_default_app",
            classmethod(lambda cls, p: opened.append(p) or {
                "success": True, "file_path": p, "file_name": p.rsplit("/", 1)[-1],
                "opener": "stub", "note": "opened",
            }))

        fake_home = Path(tempfile.mkdtemp(prefix="arena_cycle_"))
        media = fake_home / "Music"
        media.mkdir()
        (media / "Kaba - Song.mp3").write_bytes(b"\x00" * 16)
        old_home = Path.home()
        os.environ["HOME"] = str(fake_home)
        try:
            rt = CognitiveRuntime.get_instance()
            result = rt.process_cognitive_cycle(
                user_text="find the file kaba and play it", complexity="fast")
        finally:
            os.environ["HOME"] = str(old_home)
            shutil.rmtree(fake_home, ignore_errors=True)

        assert result.get("action_type") == "open_file"
        executed = " ".join(str(a) for a in (result.get("executed_actions") or []))
        reply = str(result.get("assistant_reply") or "")
        assert opened, "the open must actually be attempted"
        assert "Kaba - Song.mp3" in opened[0]
        assert "Kaba - Song.mp3" in executed or "Kaba - Song.mp3" in reply
        # The live bug: asking the owner for information the search itself
        # just obtained ('can you confirm if kaba is MP3, AVI?').
        assert not re.search(r"confirm.{0,40}(type of file|MP3|AVI)", reply, re.I)
        # And never a leaked tool validation error.
        assert "resize_image" not in reply
        assert "missing required parameter" not in reply
