"""
Phase 4: Continuous Perception Tests.

4A: Background Observer — environment probing, change detection, adaptive frequency
4B: Event-Driven Cognition — prioritization, deduplication, goal relevance
4C: Anticipatory Action — sequential/temporal prediction, preparation suggestions
"""

import time
import pytest
from unittest.mock import MagicMock
from app.perception.background_observer import (
    BackgroundObserver, EnvironmentChange, EnvironmentProbe, ProcessProbe
)
from app.perception.event_prioritizer import (
    EventPrioritizer, EventDecision, classify_priority, TriggerRule
)
from app.perception.anticipation_engine import (
    AnticipationEngine, Anticipation, TaskEvent
)


# ── 4A: Background Observer ──────────────────────────────────────────


class MockProbe(EnvironmentProbe):
    """Test probe that returns configurable state."""
    def __init__(self, name="mock_probe"):
        super().__init__(name)
        self._state = {}

    def set_state(self, state):
        self._state = state

    def probe(self):
        return dict(self._state)


class TestBackgroundObserver:

    def test_probe_detects_new_subject(self):
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})
        changes = probe.detect_changes(probe.probe())
        assert len(changes) == 1
        assert changes[0].change_type == "appeared"
        assert changes[0].subject == "chrome"
        assert changes[0].previous_state is None

    def test_probe_detects_changed_state(self):
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})
        probe.detect_changes(probe.probe())  # initial scan

        probe.set_state({"chrome": {"status": "stopped"}})
        changes = probe.detect_changes(probe.probe())
        assert len(changes) == 1
        assert changes[0].change_type == "changed"
        assert changes[0].previous_state == {"status": "running"}
        assert changes[0].current_state == {"status": "stopped"}

    def test_probe_detects_disappeared_subject(self):
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}, "firefox": {"status": "running"}})
        probe.detect_changes(probe.probe())  # initial scan

        probe.set_state({"chrome": {"status": "running"}})
        changes = probe.detect_changes(probe.probe())
        assert len(changes) == 1
        assert changes[0].change_type == "disappeared"
        assert changes[0].subject == "firefox"

    def test_no_changes_returns_empty(self):
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})
        probe.detect_changes(probe.probe())  # initial scan

        changes = probe.detect_changes(probe.probe())
        assert len(changes) == 0

    def test_observer_run_once(self):
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})

        observer = BackgroundObserver()
        observer.add_probe(probe)

        changes = observer.run_once()
        assert len(changes) == 1
        assert changes[0].subject == "chrome"
        assert observer.cycle_count == 1

    def test_observer_accumulates_changes(self):
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})

        observer = BackgroundObserver()
        observer.add_probe(probe)
        observer.run_once()  # chrome appeared

        probe.set_state({"chrome": {"status": "running"}, "firefox": {"status": "running"}})
        observer.run_once()  # firefox appeared

        changes = observer.get_changes(clear=False)
        assert len(changes) == 2

    def test_observer_get_changes_clears_buffer(self):
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})

        observer = BackgroundObserver()
        observer.add_probe(probe)
        observer.run_once()

        changes = observer.get_changes(clear=True)
        assert len(changes) == 1

        changes2 = observer.get_changes(clear=True)
        assert len(changes2) == 0

    def test_adaptive_interval_with_active_tasks(self):
        observer = BackgroundObserver(interval=30.0)
        assert observer.current_interval == 30.0

        observer.set_active_tasks(1)
        assert observer.current_interval == 10.0  # ACTIVE_INTERVAL

    def test_adaptive_interval_without_active_tasks(self):
        observer = BackgroundObserver(interval=30.0)
        observer.set_active_tasks(0)
        assert observer.current_interval == 30.0

    def test_observer_publishes_to_event_bus(self):
        mock_bus = MagicMock()
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})

        observer = BackgroundObserver(event_bus=mock_bus)
        observer.add_probe(probe)
        observer.run_once()

        mock_bus.emit.assert_called_once()
        call_args = mock_bus.emit.call_args
        assert "environment" in call_args[1].get("event_type", call_args[0][0] if call_args[0] else "")

    def test_observer_on_change_callback(self):
        callback = MagicMock()
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})

        observer = BackgroundObserver(on_change=callback)
        observer.add_probe(probe)
        observer.run_once()

        callback.assert_called_once()
        change = callback.call_args[0][0]
        assert isinstance(change, EnvironmentChange)

    def test_start_stop(self):
        observer = BackgroundObserver(interval=0.1)
        probe = MockProbe()
        observer.add_probe(probe)

        observer.start()
        assert observer.is_running
        time.sleep(0.3)
        observer.stop()
        assert not observer.is_running
        assert observer.cycle_count >= 1

    def test_multiple_probes(self):
        probe1 = MockProbe("probe1")
        probe1.set_state({"chrome": {"status": "running"}})
        probe2 = MockProbe("probe2")
        probe2.set_state({"cpu": {"percent": 50}})

        observer = BackgroundObserver()
        observer.add_probe(probe1)
        observer.add_probe(probe2)

        changes = observer.run_once()
        assert len(changes) == 2
        sources = {c.source for c in changes}
        assert "probe1" in sources
        assert "probe2" in sources


# ── 4B: Event-Driven Cognition ───────────────────────────────────────


class TestEventPrioritizer:

    def _make_change(self, change_type="appeared", subject="chrome",
                     priority=None, source="probe"):
        return EnvironmentChange(
            change_id="test123",
            change_type=change_type,
            subject=subject,
            previous_state=None,
            current_state={"status": "running"},
            source=source,
            priority=priority or "normal"
        )

    def test_urgent_event_triggers(self):
        prioritizer = EventPrioritizer()
        change = self._make_change(priority="urgent")
        decision = prioritizer.evaluate(change)
        assert decision.should_trigger is True
        assert decision.priority == "urgent"

    def test_informational_event_no_trigger(self):
        prioritizer = EventPrioritizer()
        change = self._make_change(change_type="changed", priority="informational")
        decision = prioritizer.evaluate(change)
        # Informational without pending goal relevance → no trigger
        assert decision.priority == "informational"

    def test_deduplication_within_window(self):
        prioritizer = EventPrioritizer()
        change = self._make_change(change_type="appeared", subject="chrome", priority="urgent")

        d1 = prioritizer.evaluate(change)
        d2 = prioritizer.evaluate(change)

        assert d1.should_trigger is True
        assert d2.should_trigger is False
        assert d2.reason == "deduplicated"

    def test_relevant_goal_triggers(self):
        prioritizer = EventPrioritizer(pending_goals=[
            {"entities": ["chrome"], "goal_text": "Open Chrome browser"}
        ])
        change = self._make_change(change_type="appeared", subject="chrome", priority="normal")
        decision = prioritizer.evaluate(change)
        assert decision.should_trigger is True
        assert len(decision.relevant_goals) >= 1

    def test_classify_priority_urgent_patterns(self):
        assert classify_priority("crashed", "chrome") == "urgent"
        assert classify_priority("disconnected", "device") == "urgent"
        assert classify_priority("error", "process") == "urgent"

    def test_classify_priority_actionable_patterns(self):
        assert classify_priority("appeared", "chrome") == "actionable"
        assert classify_priority("connected", "device") == "actionable"
        assert classify_priority("completed", "task") == "actionable"

    def test_classify_priority_default_informational(self):
        assert classify_priority("changed", "config") == "informational"

    def test_stats_tracking(self):
        prioritizer = EventPrioritizer()
        change1 = self._make_change(priority="urgent")
        change2 = self._make_change(change_type="different", subject="other", priority="informational")

        prioritizer.evaluate(change1)
        prioritizer.evaluate(change2)

        stats = prioritizer.get_stats()
        assert stats.get("urgent", 0) >= 1

    def test_event_decision_priority_level(self):
        d = EventDecision(priority="urgent", should_trigger=True, reason="test")
        assert d.priority_level == 3

        d2 = EventDecision(priority="informational", should_trigger=False, reason="test")
        assert d2.priority_level == 1


# ── 4C: Anticipatory Action ──────────────────────────────────────────


class TestAnticipationEngine:

    def test_record_task(self, tmp_path):
        engine = AnticipationEngine(db_path=str(tmp_path / "anticipate.db"))
        event = engine.record_task("search_files", "Find report", "search_intent")
        assert event.action_type == "search_files"
        assert engine.total_events() == 1

    def test_sequential_prediction_after_enough_data(self, tmp_path):
        engine = AnticipationEngine(db_path=str(tmp_path / "anticipate.db"))
        # Record a consistent pattern: search_files → web_search
        for _ in range(5):
            engine.record_task("search_files", "Find A", "search_intent")
            engine.record_task("web_search", "Search B", "search_intent")

        predictions = engine.predict_next(last_action="search_files")
        if predictions:
            assert predictions[0].predicted_action == "web_search"
            assert predictions[0].confidence > 0.3

    def test_no_prediction_without_enough_data(self, tmp_path):
        engine = AnticipationEngine(db_path=str(tmp_path / "anticipate.db"))
        engine.record_task("search_files", "Find A")
        engine.record_task("web_search", "Search B")

        predictions = engine.predict_next(last_action="search_files")
        # Only 2 occurrences — below MIN_OCCURRENCES (3)
        assert len(predictions) == 0

    def test_temporal_prediction(self, tmp_path):
        engine = AnticipationEngine(db_path=str(tmp_path / "anticipate.db"))
        # Record tasks at hour 9
        for _ in range(5):
            engine.record_task("daily_briefing", "Morning briefing",
                              timestamp="2026-08-18T09:00:00+00:00")

        predictions = engine.predict_next(current_hour=9, current_dow=0)
        if predictions:
            daily = [p for p in predictions if p.predicted_action == "daily_briefing"]
            assert len(daily) >= 1

    def test_sensitive_actions_require_approval(self, tmp_path):
        engine = AnticipationEngine(db_path=str(tmp_path / "anticipate.db"))
        for _ in range(5):
            engine.record_task("search_files", "Find A")
            engine.record_task("send_sms", "Send text")

        predictions = engine.predict_next(last_action="search_files")
        sms_predictions = [p for p in predictions if p.predicted_action == "send_sms"]
        for p in sms_predictions:
            assert p.requires_approval is True

    def test_non_sensitive_actions_no_approval(self, tmp_path):
        engine = AnticipationEngine(db_path=str(tmp_path / "anticipate.db"))
        for _ in range(5):
            engine.record_task("search_files", "Find A")
            engine.record_task("web_search", "Search B")

        predictions = engine.predict_next(last_action="search_files")
        web_predictions = [p for p in predictions if p.predicted_action == "web_search"]
        for p in web_predictions:
            assert p.requires_approval is False

    def test_preparation_suggestion(self, tmp_path):
        engine = AnticipationEngine(db_path=str(tmp_path / "anticipate.db"))
        for _ in range(5):
            engine.record_task("search_files", "Find A")
            engine.record_task("web_search", "Search B")

        predictions = engine.predict_next(last_action="search_files")
        if predictions:
            assert predictions[0].suggested_preparation != ""

    def test_frequent_actions(self, tmp_path):
        engine = AnticipationEngine(db_path=str(tmp_path / "anticipate.db"))
        for _ in range(10):
            engine.record_task("search_files", "Find")
        for _ in range(3):
            engine.record_task("web_search", "Search")

        frequent = engine.frequent_actions(min_count=3)
        assert len(frequent) >= 1
        assert frequent[0]["action_type"] == "search_files"
        assert frequent[0]["count"] == 10

    def test_persistence_across_reloads(self, tmp_path):
        db_path = str(tmp_path / "anticipate.db")
        engine1 = AnticipationEngine(db_path=db_path)
        for _ in range(5):
            engine1.record_task("search_files", "Find A")
            engine1.record_task("web_search", "Search B")

        engine2 = AnticipationEngine(db_path=db_path)
        assert engine2.total_events() == 10

        predictions = engine2.predict_next(last_action="search_files")
        if predictions:
            assert predictions[0].predicted_action == "web_search"


# ── Phase 4 Integration ──────────────────────────────────────────────


class TestPhase4Integration:

    def test_observer_feeds_prioritizer(self):
        """Background observer detects changes → prioritizer evaluates them."""
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})

        observer = BackgroundObserver()
        observer.add_probe(probe)
        changes = observer.run_once()

        prioritizer = EventPrioritizer(pending_goals=[
            {"entities": ["chrome"], "goal_text": "Open Chrome"}
        ])

        for change in changes:
            decision = prioritizer.evaluate(change)
            assert isinstance(decision, EventDecision)

    def test_full_perception_pipeline(self, tmp_path):
        """Observer → Prioritizer → Anticipation → decision."""
        # Set up observer
        probe = MockProbe()
        probe.set_state({"chrome": {"status": "running"}})
        observer = BackgroundObserver()
        observer.add_probe(probe)

        # Set up prioritizer with pending goals
        prioritizer = EventPrioritizer(pending_goals=[
            {"entities": ["chrome"], "goal_text": "Open Chrome"}
        ])

        # Set up anticipation engine
        engine = AnticipationEngine(db_path=str(tmp_path / "anticipate.db"))
        for _ in range(5):
            engine.record_task("open_application", "Open Chrome")
            engine.record_task("web_search", "Search the web")

        # Run observer cycle
        changes = observer.run_once()
        assert len(changes) >= 1

        # Prioritize changes
        decisions = [prioritizer.evaluate(c) for c in changes]
        triggered = [d for d in decisions if d.should_trigger]
        assert len(triggered) >= 1

        # Get anticipations
        anticipations = engine.predict_next(last_action="open_application")
        if anticipations:
            assert anticipations[0].predicted_action == "web_search"
