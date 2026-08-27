"""The persona prompt must not hand the model a verbatim reply to parrot.

Live case: the 3B fast model answered 'do you have wisdom?' by copying the
persona's example clarification sentence word-for-word. The prompt now
describes the BEHAVIOR without quoting any example reply, and adds a rule
that self-referential questions are answered directly, never deflected.
"""
from app.memory.coworker_brain import CoworkerBrain


def test_persona_contains_no_example_reply_to_parrot():
    persona = CoworkerBrain.COWORKER_PERSONA
    assert "I don't have full context" not in persona
    assert "quick note or rule" not in persona
    # The behavior is still described, in behavioral terms.
    assert "lack knowledge or context" in persona
    assert "Never copy any example phrasing" in persona


def test_prompt_for_self_referential_questions_directs_honest_answers():
    prompt = CoworkerBrain.format_coworker_prompt("do you have wisdom?")
    assert "answered directly and honestly" in prompt
    assert "never deflected" in prompt
