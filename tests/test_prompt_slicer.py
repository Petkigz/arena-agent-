import pytest
from app.cognition.prompt_slicer import PromptSlicerEngine

def test_prompt_slicer():
    context = PromptSlicerEngine.slice_context_for_task("Open Firefox and search Ordinary")
    assert len(context.selected_instructions) >= 2
    assert "SystemAppInventory" in context.compact_prompt_str
