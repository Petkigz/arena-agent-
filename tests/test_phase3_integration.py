from app.cognition.action_selection import ActionSelector, InvestigationExecutor, InvestigationPlan
from app.cognition.belief_engine import BeliefEngine
from app.cognition.beliefs import BeliefStore
from app.cognition.event_bus import EventBus
from app.cognition.information_gain import InformationNeed
from app.cognition.reasoning_loop import CognitiveReasoningLoop
from app.cognition.world_ingest import WorldIngestor
from app.cognition.world_model import WorldModel


def test_persistent_beliefs_round_trip(tmp_path):
    path = str(tmp_path / "beliefs.db")
    store = BeliefStore(path)
    store.observe("chrome", "status", "running", source="process", confidence=0.9)
    restored = BeliefStore(path).get("chrome", "status")
    assert restored is not None
    assert restored.value == "running"
    assert len(restored.evidence) == 1


def test_closed_loop_executes_probe_and_reasons_again(tmp_path):
    model = WorldModel(str(tmp_path / "world.db"))
    bus = EventBus()
    ingestor = WorldIngestor(model, bus)
    selector = ActionSelector()
    executor = InvestigationExecutor()

    need = InformationNeed("Is Chrome responsive?", "chrome", "vision is uncertain", 0.9)
    selector.registry.register(
        "chrome",
        lambda n: InvestigationPlan(
            tool="probe_chrome",
            arguments={},
            target=n.target,
            reason=n.reason,
            priority=n.priority,
            predicate="responsiveness",
        ),
    )
    executor.register("probe_chrome", lambda: "responsive")
    loop = CognitiveReasoningLoop(
        engine=BeliefEngine(), action_selector=selector, executor=executor,
        world_ingestor=ingestor, event_bus=bus, max_steps=2,
    )

    trace = loop.run("chrome", "status", value="unknown", source="vision", confidence=0.2, information_needs=[need])
    assert trace.results[0].success is True
    assert trace.results[0].output == "responsive"
    assert model.latest_observation("chrome", "responsiveness").value == "responsive"
    assert any(item.event_type == "investigation_completed" for item in bus.history())
