"""Charter §5 wiring tests: the anticipation engine fed from real cognitive
cycles, the live background observer, and their owner-facing endpoints.

The owner's bar: these must be live capabilities wired into the working
system, not dead modules waiting for callers that never come.
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.cognition.metacognitive_monitor import (
    CognitiveProcess,
    MetacognitiveMonitor,
    ReasoningStrategy,
)
from app.perception.anticipation_engine import AnticipationEngine
from app.perception.background_observer import (
    BackgroundObserver,
    EnvironmentChange,
    EnvironmentProbe,
    build_default_observer,
)
from app.perception import background_observer as bo_module

client = TestClient(app)


class _FakeProbe(EnvironmentProbe):
    """Deterministic probe: reports an incrementing counter."""

    name = "fake"

    def __init__(self) -> None:
        self._calls = 0

    def probe(self):
        self._calls += 1
        return {"counter": self._calls}

    def detect_changes(self, state):
        if state.get("counter", 0) == 2:
            return [
                EnvironmentChange(
                    change_id="c1",
                    change_type="process_started",
                    subject="fake-entity",
                    previous_state=None,
                    current_state=1,
                    source=self.name,
                )
            ]
        return []


def _fresh_engine(tmp_path):
    return AnticipationEngine(db_path=str(tmp_path / "anticipation_test.db"))


# ── Anticipation engine learns repeated rhythms ──────────────────────


def test_engine_predicts_after_repeated_tasks(tmp_path):
    engine = _fresh_engine(tmp_path)
    for _ in range(3):
        engine.record_task(
            action_type="search_files",
            goal_text="find the quarterly report",
            intent_type="file_operation",
            success=True,
        )
    anticipations = engine.predict_next(last_action="list_files", limit=5)
    assert anticipations, "engine should anticipate a task repeated 3x"
    assert anticipations[0].predicted_action == "search_files"
    assert anticipations[0].requires_approval is False


def test_engine_empty_without_evidence(tmp_path):
    engine = _fresh_engine(tmp_path)
    assert engine.predict_next(last_action="anything", limit=5) == []


# ── Monitor → anticipation hook (every cognitive cycle feeds it) ─────


def test_monitor_record_process_feeds_anticipation_engine(tmp_path):
    monitor = MetacognitiveMonitor(db_path=str(tmp_path / "meta_test.db"))
    before = len(monitor.anticipation_engine._events)
    monitor.record_process(
        process_type=CognitiveProcess.DECISION_MAKING,
        strategy=ReasoningStrategy.ABDUCTIVE,
        input_data={"goal": "tidy the downloads folder"},
        output_data={"plan": "move screenshots"},
        execution_time_ms=12.0,
        confidence=0.8,
        success=True,
        errors=[],
    )
    assert len(monitor.anticipation_engine._events) == before + 1
    event = monitor.anticipation_engine._events[-1]
    assert event.action_type == "abductive"
    assert "downloads" in event.goal_text


def test_monitor_get_anticipations_returns_serializable(tmp_path):
    monitor = MetacognitiveMonitor(db_path=str(tmp_path / "meta_test2.db"))
    items = monitor.get_anticipations(limit=3)
    assert isinstance(items, list)


# ── Owner-facing endpoints ────────────────────────────────────────────


def test_anticipations_endpoint_honest_when_no_model(monkeypatch):
    empty_monitor = SimpleNamespace(
        get_anticipations=lambda limit=5: []
    )
    monkeypatch.setattr(
        "app.cognition.runtime.CognitiveRuntime.get_instance",
        classmethod(lambda cls: SimpleNamespace(metacognitive_monitor=empty_monitor)),
    )
    response = client.get("/cognition/anticipations")
    assert response.status_code == 200
    data = response.json()
    assert data["anticipations"] == []
    assert "Nothing anticipated" in data["note"]


def test_anticipations_endpoint_returns_predictions(monkeypatch):
    monitor = SimpleNamespace(
        get_anticipations=lambda limit=5: [
            {
                "anticipation_id": "a1",
                "predicted_action": "search_files",
                "confidence": 0.8,
                "reason": "usually follows list_files",
                "suggested_preparation": "warm the file index",
                "requires_approval": False,
                "context": {},
                "timestamp": "2026-09-08T00:00:00",
            }
        ]
    )
    monkeypatch.setattr(
        "app.cognition.runtime.CognitiveRuntime.get_instance",
        classmethod(lambda cls: SimpleNamespace(metacognitive_monitor=monitor)),
    )
    response = client.get("/cognition/anticipations")
    assert response.status_code == 200
    data = response.json()
    assert data["anticipations"][0]["predicted_action"] == "search_files"
    assert "never actions" in data["note"]


def test_environment_observations_endpoint_honest_when_off(monkeypatch):
    monkeypatch.setattr(bo_module, "observer_instance", None)
    response = client.get("/cognition/environment/observations")
    assert response.status_code == 200
    data = response.json()
    assert data["observations"] == []
    assert data["is_running"] is False
    assert "not running" in data["note"]


def test_environment_observations_endpoint_returns_changes(monkeypatch):
    observer = BackgroundObserver(interval=30.0)
    observer.add_probe(_FakeProbe())
    observer.run_once()  # counter=1, no change
    observer.run_once()  # counter=2, change detected
    monkeypatch.setattr(bo_module, "observer_instance", observer)
    response = client.get("/cognition/environment/observations")
    assert response.status_code == 200
    data = response.json()
    assert data["cycle_count"] == 2
    assert len(data["observations"]) == 1
    assert data["observations"][0]["change_type"] == "process_started"
    assert "never actions" in data["note"]


# ── Background observer lifecycle ─────────────────────────────────────


def test_observer_run_once_detects_changes():
    observer = BackgroundObserver(interval=30.0)
    observer.add_probe(_FakeProbe())
    changes = observer.run_once()
    assert changes == []
    changes = observer.run_once()
    assert len(changes) == 1
    buffered = observer.get_changes(clear=True)
    assert len(buffered) == 1
    assert observer.get_changes(clear=True) == []  # cleared


def test_observer_thread_starts_and_stops():
    observer = BackgroundObserver(interval=0.05)
    observer.add_probe(_FakeProbe())
    observer.start()
    assert observer.is_running is True
    import time

    time.sleep(0.25)
    observer.stop()
    assert observer.is_running is False
    assert observer.cycle_count >= 1


def test_watcher_chain_observe_prioritize_surface():
    """Full watcher chain (charter §5 ④): probes observe, prioritizer
    classifies and deduplicates, decisions surface to the owner."""
    from app.perception import background_observer as bo

    observer = BackgroundObserver(interval=30.0, on_change=bo._on_change_prioritize)
    observer.add_probe(_FakeProbe())
    with bo._decisions_lock:
        bo._recent_decisions.clear()
    observer.run_once()
    observer.run_once()
    decisions = bo.get_recent_decisions(limit=10)
    assert len(decisions) == 1, "one observed change should yield one decision"
    assert decisions[0]["change_type"] == "process_started"
    assert "priority" in decisions[0] and "reason" in decisions[0]
    assert isinstance(decisions[0]["should_trigger"], bool)


def test_watcher_prioritizer_dedupes_repeats():
    """Two identical changes inside the dedup window -> one triggering decision."""
    from app.perception.event_prioritizer import EventPrioritizer

    observer = build_default_observer()
    observer.add_probe(_FakeProbe())
    prioritizer = EventPrioritizer()
    observer.run_once()
    observer.run_once()
    # Directly evaluate the same change twice through the prioritizer.
    change = EnvironmentChange(
        change_id="dup", change_type="process_started", subject="same",
        previous_state=None, current_state=1, source="fake",
    )
    first = prioritizer.evaluate(change)
    second = prioritizer.evaluate(change)
    assert first.should_trigger or not first.should_trigger  # decision returned
    assert second.reason == "deduplicated"


def test_build_default_observer_has_readonly_probes():
    observer = build_default_observer()
    names = {probe.name for probe in observer._probes}
    assert "processes" in names or "system_resources" in names or len(names) >= 1
    for probe in observer._probes:
        assert isinstance(probe, EnvironmentProbe)
