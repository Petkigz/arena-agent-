from app.cognition.action_selection import ActionSelector, InvestigationPlan
from app.cognition.information_gain import InformationNeed


def test_information_need_becomes_bounded_plan():
    selector = ActionSelector()
    selector.registry.register(
        "chrome",
        lambda need: InvestigationPlan(
            tool="process_inspector",
            arguments={"name": "chrome.exe"},
            target=need.target,
            reason=need.reason,
            priority=need.priority,
        ),
    )
    need = InformationNeed("Is Chrome responsive?", "chrome", "conflicting observations", 0.9)
    plan = selector.select(need)
    assert plan is not None
    assert plan.tool == "process_inspector"
    assert plan.arguments["name"] == "chrome.exe"


def test_unknown_probe_does_not_guess_a_tool():
    selector = ActionSelector()
    need = InformationNeed("What is this?", "unknown", "insufficient context")
    assert selector.select(need) is None
