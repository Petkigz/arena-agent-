from app.cognition.runtime import CognitiveRuntime
from app.cognition.action_selection import InvestigationPlan
from app.cognition.information_gain import InformationNeed


def test_runtime_composes_phase3_components(tmp_path):
    runtime = CognitiveRuntime(db_path=str(tmp_path / "arena.db"), max_steps=1)
    runtime.actions.registry.register(
        "service",
        lambda need: InvestigationPlan(
            tool="service_probe", arguments={}, target=need.target,
            reason=need.reason, priority=need.priority, predicate="health",
        ),
    )
    runtime.executor.register("service_probe", lambda: "healthy")
    trace = runtime.loop.run(
        "service", "status", value="unknown", source="monitor", confidence=0.2,
        information_needs=[InformationNeed("Is it healthy?", "service", "uncertain", 0.9)],
    )
    assert trace.results[0].success
    assert runtime.world.latest_observation("service", "health").value == "healthy"
