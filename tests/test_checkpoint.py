from app.cognition.blackboard import Blackboard
from app.cognition.checkpoint import CognitiveCheckpointStore
from app.cognition.cognitive_state import CognitiveState


def test_checkpoint_round_trip(tmp_path):
    store = CognitiveCheckpointStore(tmp_path)
    state = CognitiveState()
    board = Blackboard()
    board.set("goal", "test", source="unit_test", confidence=1.0)

    path = store.save(state, board)
    restored = store.load()

    assert path.exists()
    assert restored is not None
    assert restored["schema_version"] == 1
    assert restored["blackboard"]["goal"]["value"] == "test"
