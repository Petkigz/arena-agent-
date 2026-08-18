import pytest
from app.cognition.prompt_slicer import PromptSlicerEngine

def test_prompt_slicer_context_budget():
    history = [
        {"role": "user", "content": "How's the weather?"},
        {"role": "assistant", "content": "Nice and sunny."},
        {"role": "user", "content": "Search for Python tutorials"},
        {"role": "assistant", "content": "Found 5 tutorials."},
        {"role": "user", "content": "Open Firefox"}
    ]

    ctx = PromptSlicerEngine.slice_context_for_task("Open Firefox", message_history=history)
    assert ctx.history_summarized is True
    assert ctx.token_budget_used < PromptSlicerEngine.MAX_CONTEXT_TOKEN_BUDGET
    assert "CONTEXT BUDGET COMPRESSION" in ctx.compact_prompt_str
