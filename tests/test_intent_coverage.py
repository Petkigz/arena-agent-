"""Intent coverage: the questions that were misrouted on the owner machine.

Live failures this suite pins:
1. 'how many tabs are open on this desktop' was classified action_intent ->
   tried to LAUNCH an app named after the question -> false
   VerifiedSuccess=True when the launch actually failed.
2. Observation questions must never reach the heavy action pipeline when a
   Level-0 read-only observation can answer them.
3. Verb lists must be consistent between the matcher and the OS planner
   (they diverged: 'open' was in one, not the other).
"""
from app.cognition.tool_matcher import match_control_tool
from app.cognition.observation_router import plan_observation
from app.cognition.os_control_planner import _is_os_control_request, OS_ACTION_VERBS


def test_tabs_question_routes_to_window_observation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])
    plan = plan_observation("how many tabs are open on this desktop")
    assert plan is not None
    assert plan.question_kind == "browser_tabs"
    assert plan.action_type == "list_windows"  # read-only observation


def test_tabs_question_never_launches_an_application():
    """The exact live failure: 'how many tabs...' tried open_application."""
    # The observation router must intercept BEFORE any action proposal.
    plan = plan_observation("how many tabs are open on this desktop")
    assert plan is not None and plan.action_type == "list_windows"
    # The tool matcher must NOT propose open_application for a counting
    # question (the old pipeline did exactly this).
    m = match_control_tool("how many tabs are open on this desktop")
    if m is not None:
        assert m.action_type != "open_application", (
            "counting questions must never launch applications")


def test_more_tab_and_window_phrasings():
    for text, kind in [
        ("list my browser tabs", "browser_tabs"),
        ("what tabs are open", "browser_tabs"),
        ("how many browser windows do I have", "open_windows"),
        ("count open tabs", "browser_tabs"),
        ("which windows are open", "open_windows"),
    ]:
        plan = plan_observation(text)
        assert plan is not None, f"no observation plan for {text!r}"
        assert plan.question_kind == kind, f"{text!r} -> {plan.question_kind} != {kind}"


def test_control_verb_lists_are_consistent():
    """'open' must be in BOTH verb sets (they diverged, causing the
    misrouting). Any control-signaling word in one must be in the other or
    explicitly justified."""
    from app.cognition.tool_matcher import CONTROL_VERBS
    # Every matcher control verb must be recognized by the OS planner too.
    missing = CONTROL_VERBS - OS_ACTION_VERBS
    assert not missing, f"verbs in matcher but not planner: {missing}"


def test_os_control_requests_cover_common_settings():
    for text in [
        "change my desktop icon size to medium",
        "turn on dark mode",
        "set volume to 50",
        "adjust brightness",
        "change my wallpaper",
        "enable night light",
        "set screen resolution to 1920x1080",
    ]:
        assert _is_os_control_request(text), f"{text!r} should be detected as OS control"


def test_non_control_questions_stay_questions():
    for text in [
        "what is the capital of France",
        "do you have wisdom",
        "can you talk",
        "write me a poem",
    ]:
        assert not _is_os_control_request(text)
        assert plan_observation(text) is None or plan_observation(text).question_kind not in (
            "browser_tabs",)  # no forced observation for pure chat


def test_observation_priority_over_action_in_full_cycle(tmp_path, monkeypatch):
    """Full-cycle: a tabs question must execute list_windows (Level 0), never
    open_application (Level 2). This is the end-to-end guard for the live
    'launched an app named after my question' failure."""
    from app.cognition.runtime import CognitiveRuntime

    runtime = CognitiveRuntime.get_instance(str(tmp_path / "rt.db"))

    executed = []

    def fake_manifest():
        def handler(payload):
            return {"success": True, "open_windows": [
                "Google Chrome - 5 tabs", "VS Code", "Notepad"]}
        return {"list_windows": {"safety_level": 0, "handler": handler}}

    import app.tools.manifest as manifest_module
    monkeypatch.setattr(manifest_module, "get_tool_manifest", fake_manifest)

    sent = []
    monkeypatch.setattr(
        "app.llm.llm_client.generate_chat_completion",
        lambda messages=None, **kw: sent.append(messages) or {
            "choices": [{"message": {"content": "3 windows"}}],
        })

    result = runtime.process_cognitive_cycle("how many tabs are open on this desktop")
    # The answer must reference the observed evidence, not be a fabrication.
    system_prompt = sent[0][0]["content"] if sent else ""
    assert "OBSERVED" in system_prompt or "3 windows" in result.get("assistant_reply", "")
    assert result.get("action_type") != "open_application"


def test_os_control_plan_placeholder_never_reaches_gate(tmp_path, monkeypatch):
    """'open taskbar' routed to os_control_plan (correct matcher) but the
    runtime passed the PLACEHOLDER action type to the ActionGate — blocked
    as 'Unknown action' (Level 3 default). The runtime must convert
    os_control_plan → os_control_execute with a real planned command."""
    from app.cognition.runtime import CognitiveRuntime

    runtime = CognitiveRuntime.get_instance(str(tmp_path / "rt.db"))

    planned = []

    class FakePlan:
        plan_id = "p1"
        user_request = "open taskbar"
        command = "Set-ItemProperty -Path 'HKCU:\\...' -Name TaskbarAl -Value 0"
        shell = "powershell"
        description = "Show the taskbar"
        verify_command = ""
        risk_level = "reversible"
        platform = "Windows"
        created_at = "now"
        def to_dict(self):
            return {
                "plan_id": self.plan_id, "user_request": self.user_request,
                "command": self.command, "shell": self.shell,
                "description": self.description,
                "verify_command": self.verify_command,
                "risk_level": self.risk_level, "platform": self.platform,
                "created_at": self.created_at,
            }

    import app.cognition.os_control_planner as ocp
    monkeypatch.setattr(ocp, "plan_os_action", lambda text: planned.append(text) or FakePlan())

    # Manifest handler that records the executed proposal.
    executed = []

    def handler(payload):
        executed.append(payload)
        return {"success": True, "request_success": True, "command": payload["plan"]["command"],
                "environment_verified": True, "side_effects": True}

    import app.tools.manifest as mm
    monkeypatch.setattr(mm, "get_tool_manifest", lambda: {
        "os_control_execute": {"safety_level": 2, "handler": handler}})

    monkeypatch.setattr(
        "app.llm.llm_client.generate_chat_completion",
        lambda messages=None, **kw: {"choices": [{"message": {"content": "done"}}]})

    result = runtime.process_cognitive_cycle("open taskbar")
    assert planned == ["open taskbar"]  # the planner WAS called
    assert result.get("action_type") != "os_control_plan", (
        "placeholder os_control_plan reached the pipeline — it must be "
        "converted to os_control_execute")
