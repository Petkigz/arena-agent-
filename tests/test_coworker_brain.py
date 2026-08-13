import pytest
from app.memory.coworker_brain import CoworkerBrain

def test_coworker_brain_competence():
    eval_res = CoworkerBrain.evaluate_task_competence("How do I configure our company policy?")
    assert "needs_more_context" in eval_res

def test_coworker_brain_prompt_formatting():
    prompt = CoworkerBrain.format_coworker_prompt("Let's review the code together", executed_actions=["Opened VS Code"])
    assert "human workmate" in prompt
    assert "Opened VS Code" in prompt
