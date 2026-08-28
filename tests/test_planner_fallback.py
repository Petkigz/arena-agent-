"""OS planner model fallback: main fails (400/simulated) → retry with fast.

Live failure: the inference profile named main=qwen2.5-9b-instruct which
LM Studio doesn't have loaded → every planner call returned a simulated
response → planner returned None → the request fell through to the 3B,
which improvised 'I don't have direct control over the taskbar' — a
falsehood (the tooling exists; planning failed).
"""
import json
from unittest.mock import patch

from app.cognition.os_control_planner import plan_os_action


class _Reply:
    def __init__(self, content, simulated=False):
        self._content = content
        self._simulated = simulated

    def __call__(self, messages=None, **kw):
        if self._simulated:
            return {"id": "chat-simulated", "choices": [{"message": {"content": self._content}}]}
        return {"choices": [{"message": {"content": self._content}}]}


GOOD_PLAN = json.dumps({
    "command": "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced' -Name TaskbarAl -Value 0",
    "description": "Show the taskbar",
    "verify_command": "(Get-ItemProperty 'HKCU:\\...').TaskbarAl",
    "risk_level": "reversible",
})


def test_planner_falls_back_to_fast_when_main_is_simulated():
    calls = []

    def fake_llm(messages=None, complexity="main", **kw):
        calls.append(complexity)
        if complexity == "main":
            return {"id": "chat-simulated", "choices": [{"message": {"content": "..."}}]}
        return {"choices": [{"message": {"content": GOOD_PLAN}}]}

    plan = plan_os_action("open taskbar", llm_client=type("L", (), {"generate_chat_completion": staticmethod(fake_llm)}))
    assert plan is not None, "planner should succeed via the fast model"
    assert plan.command.startswith("Set-ItemProperty")
    assert calls == ["main", "fast"]  # tried main first, fell back


def test_planner_returns_none_when_both_models_fail():
    def fake_llm(messages=None, complexity="main", **kw):
        return {"id": "chat-simulated", "choices": [{"message": {"content": "..."}}]}

    plan = plan_os_action("open taskbar", llm_client=type("L", (), {"generate_chat_completion": staticmethod(fake_llm)}))
    assert plan is None  # honest failure, not a fabricated plan


def test_planner_uses_main_when_available():
    calls = []

    def fake_llm(messages=None, complexity="main", **kw):
        calls.append(complexity)
        return {"choices": [{"message": {"content": GOOD_PLAN}}]}

    plan = plan_os_action("open taskbar", llm_client=type("L", (), {"generate_chat_completion": staticmethod(fake_llm)}))
    assert plan is not None
    assert calls == ["main"]  # no fallback needed


def test_planner_refuses_dangerous_commands():
    evil = json.dumps({"command": "rm -rf /", "description": "bad",
                       "verify_command": "", "risk_level": "reversible"})
    plan = plan_os_action("delete everything", llm_client=type("L", (), {"generate_chat_completion": staticmethod(_Reply(evil))}))
    assert plan is None
