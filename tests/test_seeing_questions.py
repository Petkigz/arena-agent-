"""Regressions from the live 'can you see my desktop' session.

1. The desktop token/room handlers were mangled by a patch (the token
   handler's `if done:` block landed inside _handle_room_message) — replies
   streamed but the bubble stayed 'thinking' and room messages crashed with
   NameError. Pinned by asserting the two handlers are distinct and complete.
2. 'can you see my desktop' matched no observation pattern, so the 3B freely
   claimed 'I don't have direct access to your local system' — false. The
   router now maps seeing-questions to screen_capture, and the persona
   forbids claiming lack of host access.
"""
from app.cognition.observation_router import plan_observation


def test_seeing_questions_get_eyes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.cognition.observation_router._desktop_directories",
        lambda: [str(tmp_path)])
    for question in (
        "can you see my desktop",
        "can you see my screen?",
        "could you look at my display",
        "do you have access to my screen",
    ):
        plan = plan_observation(question)
        assert plan is not None, question
        assert plan.action_type == "screen_capture", question
    # The original icon-count question still routes to the filesystem.
    assert plan_observation("how many icons do i have on my desktop").action_type == "list_directory"


def test_persona_never_claims_lack_of_host_access():
    from app.memory.coworker_brain import CoworkerBrain
    persona = CoworkerBrain.COWORKER_PERSONA
    assert "NEVER claim you lack access to the local system" in persona
    assert "read-only observation tools" in persona


def test_desktop_handlers_are_distinct_and_complete():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "desktop" / "app.py").read_text(encoding="utf-8")

    token_block = source[source.index("def _handle_chat_token"):source.index("def _handle_room_message")]
    assert "stream_token(token, done)" in token_block
    assert 'if done:' in token_block                      # the status reset lives HERE
    assert 'beanie.set_message("I\'m here.")' in token_block

    room_block = source[source.index("def _handle_room_message"):source.index("@Slot(list)")]
    assert "show_user_message(message_id, content)" in room_block
    assert "done" not in room_block.replace("message_id", "")  # no stray token logic
    assert "@Slot(str, str)" in source
