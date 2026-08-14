import pytest
from app.agents.proactive_coworker_daemon import ProactiveCoworkerDaemon

def test_proactive_coworker_daemon():
    res = ProactiveCoworkerDaemon.run_idle_proactive_cycle()
    assert res["success"] is True
    assert "proactive_insight" in res

    greeting = ProactiveCoworkerDaemon.get_proactive_greeting()
    assert len(greeting) > 0
    assert "Proactive Coworker Update" in greeting
