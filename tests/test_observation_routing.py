"""Host-state questions get real observations; questions sync across clients.

Live lesson: 'how many icons do I have on my desktop' was classified
knowledge_query and answered by pure LLM imagination — the agent has eyes
(filesystem, screen, process list) but nothing routed to them. The
observation router deterministically maps host-state questions to Level-0
read-only tools and the ANSWER branch answers from the evidence.
"""
import json
from unittest.mock import patch

from app.cognition.observation_router import plan_observation, render_observation_evidence
from app.tools.universal_filesystem import UniversalFilesystem


def test_host_state_questions_map_to_read_only_plans(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])
    plan = plan_observation("how many icons do I have on my desktop?")
    assert plan is not None and plan.action_type == "list_directory"
    assert plan.question_kind == "desktop_contents"
    assert "never" not in plan.evidence_hint  # evidence, not opinion

    assert plan_observation("what's on my screen right now?").action_type == "screen_capture"
    assert plan_observation("what apps are running?").action_type == "list_processes"
    assert plan_observation("which windows are open?").action_type == "list_windows"
    assert plan_observation("what programs do i have installed?").action_type == "list_apps"


def test_plain_chat_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])
    assert plan_observation("hi") is None
    assert plan_observation("what is the capital of France?") is None
    assert plan_observation("can you talk?") is None
    assert plan_observation("do you have wisdom?") is None


def test_list_directory_counts_real_entries(tmp_path):
    (tmp_path / "Chrome.lnk").write_text("x")
    (tmp_path / "readme.txt").write_text("x")
    (tmp_path / ".hidden").write_text("x")
    result = UniversalFilesystem.list_directory([{"path": str(tmp_path)}])
    listing = result["listings"][0]
    assert listing["count"] == 2  # hidden excluded
    assert "Chrome.lnk" in listing["entries"] and ".hidden" not in listing["entries"]
    assert result["side_effects"] is False
    missing = UniversalFilesystem.list_directory([{"path": str(tmp_path / "nope")}])
    assert missing["success"] is False and missing["errors"]


def test_evidence_rendering_for_the_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])
    evidence = render_observation_evidence(
        {"success": True, "listings": [
            {"directory": r"C:\Users\PETAR\Desktop", "count": 12, "entries": ["a.lnk"]}]},
        plan_observation("how many icons do i have on my desktop"))
    assert "12 total desktop entries" in evidence
    assert "OBSERVED" in evidence


def test_answer_branch_uses_observation_evidence(tmp_path, monkeypatch):
    """The runtime ANSWER branch must execute the plan and inject evidence."""
    from app.cognition.runtime import CognitiveRuntime

    runtime = CognitiveRuntime.get_instance(str(tmp_path / "rt.db"))

    captured = {}

    def fake_manifest():
        def handler(payload):
            captured.update(payload)
            return {"success": True, "listings": [
                {"directory": r"C:\Users\X\Desktop", "count": 7, "entries": ["a", "b"]}]}

        return {"list_directory": {"safety_level": 0, "handler": handler}}

    import app.tools.manifest as manifest_module
    monkeypatch.setattr(manifest_module, "get_tool_manifest", fake_manifest)
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [r"C:\Users\X\Desktop"])

    sent_messages = []
    monkeypatch.setattr(
        "app.llm.llm_client.generate_chat_completion",
        lambda messages=None, **kw: sent_messages.append(messages) or {
            "choices": [{"message": {"content": "7 icons"}}],
        })

    result = runtime.process_cognitive_cycle("how many icons do i have on my desktop?")
    assert result["assistant_reply"] == "7 icons"
    system_prompt = sent_messages[0][0]["content"]
    assert "OBSERVED HOST EVIDENCE" in system_prompt
    assert "7 total desktop entries" in system_prompt  # from the tool, not imagination


def test_room_message_broadcast_for_cross_client_sync():
    """Questions broadcast to the room so other clients render them."""
    import asyncio
    from unittest.mock import MagicMock
    from backend.message_router import MessageRouter

    sent = []

    async def send(cid, message):
        sent.append((cid, message))

    router = MessageRouter.__new__(MessageRouter)
    router._check_rate_limit = lambda cid: True

    async def fake_cycle(content, **kw):
        return "ok"

    router._call_cognitive_runtime = fake_cycle
    websocket = MagicMock()

    async def call():
        with patch("backend.message_router.ws_manager", SimpleNamespace := type("W", (), {
            "send_to_conversation": staticmethod(send),
            "join_conversation": staticmethod(lambda ws, cid: None),
        })()), \
             patch("backend.message_router.add_to_history"), \
             patch("backend.message_router.get_conversation_history", return_value=[]):
            handler = MessageRouter._handle_user_message.__get__(router)
            return await handler(websocket, {"conversation_id": "c1", "content": "hi"})

    asyncio.run(call())
    room = [m for cid, m in sent if m["type"] == "room_message"]
    assert room and room[0]["content"] == "hi" and room[0]["message_id"]
    # Dedupe key present so clients can avoid double-rendering their own copy.
    assert "message_id" in room[0]
