import unittest

from app.cognition import Blackboard, CognitiveEvent, CognitiveState, EventBus
from app.cognition.cognitive_router import CognitiveRouter
from app.runtime.resource_manager import ResourceManager, ResourceSnapshot


class CognitiveFoundationTests(unittest.TestCase):
    def test_state_round_trip(self):
        state = CognitiveState()
        state.update(goal="test goal", task_id="task-1")
        restored = CognitiveState.from_dict(state.to_dict())
        self.assertEqual(restored.goal, "test goal")
        self.assertEqual(restored.task_id, "task-1")

    def test_blackboard_preserves_metadata(self):
        board = Blackboard()
        board.set("answer", 42, source="test", confidence=0.9)
        self.assertEqual(board.get("answer"), 42)
        self.assertEqual(board.get_entry("answer").source, "test")
        self.assertEqual(board.get_entry("answer").confidence, 0.9)

    def test_event_bus_isolates_handler_failures(self):
        bus = EventBus()
        seen = []
        bus.subscribe("test", lambda event: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.subscribe("test", lambda event: seen.append(event.event_id))
        event = CognitiveEvent("test")
        bus.publish(event)
        self.assertEqual(seen, [event.event_id])

    def test_router_uses_deterministic_path(self):
        decision = CognitiveRouter().route("Open Chrome")
        self.assertEqual(decision.route, "deterministic")
        self.assertFalse(decision.reasoning_required)

    def test_router_uses_cognitive_path_for_complex_request(self):
        decision = CognitiveRouter().route(
            "Investigate why the browser is failing and fix the problem"
        )
        self.assertEqual(decision.route, "cognitive")
        self.assertTrue(decision.reasoning_required)

    def test_resource_policy_changes_under_pressure(self):
        manager = ResourceManager()
        snapshot = ResourceSnapshot(50.0, 92.0, 1000.0)
        policy = manager.execution_policy(snapshot)
        self.assertEqual(policy["mode"], "constrained")
        self.assertFalse(policy["allow_background_learning"])
        self.assertEqual(policy["preferred_model_tier"], "fast")


if __name__ == "__main__":
    unittest.main()
