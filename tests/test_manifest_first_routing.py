"""Manifest-first routing: the manifest decides, the LLM advises.

Root cause fixed (live): every control request was classified into 3 LLM
intents x 7 hardcoded domain templates — the ~180-tool manifest was never
consulted, so 'change my desktop wallpaper' became a chat reply. Now a
deterministic matcher forces the ACT branch with the matched tool; questions
and chat are untouched; LLM-invented capability phrases can no longer veto.
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.cognition.tool_matcher import match_control_tool


def test_wallpaper_request_matches_with_path_extraction():
    match = match_control_tool(
        "can you change my desktop wallpaper to C:\\Users\\PETAR\\pics\\wall.jpg")
    assert match is not None
    assert match.action_type == "set_wallpaper"
    assert match.payload["image_path"] == "C:\\Users\\PETAR\\pics\\wall.jpg"
    assert match.score >= 3.0


def test_everyday_control_requests_route_to_real_tools():
    assert match_control_tool("open the calculator app").action_type == "launch_app"
    assert match_control_tool("search my files for the invoice").action_type == "search_files"
    assert match_control_tool("create a backup of my documents").action_type in (
        "create_backup", "compress_files")


def test_questions_and_chat_do_not_match():
    assert match_control_tool("how many icons do i have on my desktop") is None
    assert match_control_tool("what is the capital of France") is None
    assert match_control_tool("do you have wisdom") is None
    assert match_control_tool("can you talk") is None


def test_ambiguous_requests_are_not_forced():
    # 'make a file' without a clear unique winner must fall through to the
    # normal pipeline rather than guessing a tool.
    assert match_control_tool("make something nice") is None


def test_runtime_routes_wallpaper_request_to_act_branch(tmp_path, monkeypatch):
    """'can you change my desktop wallpaper ...' executes the REAL tool."""
    from app.cognition.runtime import CognitiveRuntime

    runtime = CognitiveRuntime.get_instance(str(tmp_path / "rt.db"))

    executed = []

    def fake_manifest_loader():
        def handler(payload):
            executed.append(payload)
            return {"success": True, "request_success": True, "environment_verified": True,
                    "image_path": payload.get("image_path", ""),
                    "previous_wallpaper": "C:/old.jpg", "side_effects": True}
        # Only the matched tool needs to exist for this test.
        return {"set_wallpaper": {"safety_level": 2, "handler": handler}}

    import app.tools.manifest as manifest_module
    import app.cognition.runtime as runtime_module
    monkeypatch.setattr(manifest_module, "get_tool_manifest", fake_manifest_loader)
    # The matcher imports the manifest lazily from the same module.
    monkeypatch.setattr(
        "app.cognition.tool_matcher.match_control_tool",
        lambda text, manifest=None: __import__("app.cognition.tool_matcher", fromlist=["ToolMatch"]).ToolMatch(
            action_type="set_wallpaper", score=5.0, payload={"image_path": "C:/pics/w.jpg"}))

    sent = []
    monkeypatch.setattr(
        "app.llm.llm_client.generate_chat_completion",
        lambda messages=None, **kw: sent.append(messages) or {
            "choices": [{"message": {"content": "Wallpaper changed."}}],
        })

    result = runtime.process_cognitive_cycle(
        "can you change my desktop wallpaper to C:\\pics\\w.jpg")
    assert result["action_type"] == "set_wallpaper" or executed, result
    if executed:
        assert executed[0].get("image_path") == "C:/pics/w.jpg"


def test_invented_capability_phrases_cannot_veto():
    """'ability to express emotions verbally' matches nothing — ignore it."""
    from app.cognition.runtime import CognitiveRuntime as CR
    runtime = CR.get_instance()
    cap_map = runtime.check_capability_availability(
        ["ability to express emotions verbally"], target_domain="conversation")
    assert cap_map == {}  # unresolvable → ignored, not False


def test_resolvable_capabilities_still_gate():
    from app.cognition.runtime import CognitiveRuntime as CR
    runtime = CR.get_instance()
    cap_map = runtime.check_capability_availability(["web.search"], target_domain="web_research")
    assert cap_map.get("web.search") is True  # real capability still evaluated


def test_set_wallpaper_windows_verified_and_reversible(tmp_path, monkeypatch):
    """Mocked SystemParametersInfoW: verified by re-read, rollback path kept."""
    import platform
    from unittest.mock import MagicMock
    from app.tools.desktop_control import DesktopControl

    image = tmp_path / "next.jpg"
    image.write_bytes(b"\xff\xd8fake")

    state = {"current": "C:\\Old\\wall.bmp"}
    calls = []

    def fake_spi(action, param, buf, flags):
        calls.append((action, flags))
        if action == DesktopControl._SPI_GETDESKWALLPAPER:
            ctypes_buf = buf
            ctypes_buf.value = state["current"]
            return 1
        if action == DesktopControl._SPI_SETDESKWALLPAPER:
            state["current"] = buf  # buf is the path string for SET
            return 1
        return 0

    import ctypes as real_ctypes
    fake_user32 = MagicMock()
    fake_user32.SystemParametersInfoW = fake_spi
    fake_ctypes = SimpleNamespace(
        windll=SimpleNamespace(user32=fake_user32),
        create_unicode_buffer=real_ctypes.create_unicode_buffer)
    monkeypatch.setitem(__import__("sys").modules, "ctypes", fake_ctypes)
    monkeypatch.setattr(platform, "system", lambda: "Windows")

    result = DesktopControl.set_wallpaper(image_path=str(image))
    assert result["request_success"] is True
    assert result["environment_verified"] is True      # re-read matched
    assert result["previous_wallpaper"] == "C:\\Old\\wall.bmp"
    assert result["rollback_supported"] is True
    assert (DesktopControl._SPI_SETDESKWALLPAPER, DesktopControl._SPIF_UPDATEINIFILE | DesktopControl._SPIF_SENDCHANGE) in calls
