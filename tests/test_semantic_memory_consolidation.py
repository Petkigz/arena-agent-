"""Evidence-linked semantic consolidation and hybrid local retrieval."""

from types import SimpleNamespace

from app.cognition.goal_lifecycle import GoalLifecycleState
from app.cognition.memory import MemoryStore
from app.cognition.memory_learning import MemoryLearner
from app.cognition.runtime import CognitiveRuntime


def _verification(success=True, state=GoalLifecycleState.ACHIEVED):
    return SimpleNamespace(
        verified_success=success,
        final_state=state,
        met_conditions=["artifact_exists = true"] if success else [],
        failed_conditions=[] if success else ["artifact_exists = false"],
        verification_reason="Direct filesystem probe",
    )


def test_hybrid_retrieval_recovers_conceptual_paraphrase(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    relevant = store.add(
        "episodic",
        "Chrome crashed while opening the dashboard",
        importance=0.7,
        tags=("chrome", "dashboard"),
    )
    store.add("semantic", "The garden needs water every morning", importance=1.0)

    results = store.search("browser failure dashboard", limit=5)

    assert results
    assert results[0].memory_id == relevant.memory_id
    assert all("garden" not in item.content for item in results)


def test_verified_episodes_create_semantics_procedure_and_provenance(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    learner = MemoryLearner(store)
    first = learner.record_verified_episode(
        goal="Find the quarterly report",
        action_type="search_files",
        verification_result=_verification(),
        task_id="task-1",
        task_type="search_intent",
    )
    second = learner.record_verified_episode(
        goal="Find the audit report",
        action_type="search_files",
        verification_result=_verification(),
        task_id="task-2",
        task_type="search_intent",
    )

    created = learner.consolidate_verified_episodes(store.unconsolidated_episodes())

    assert sum(item.kind == "semantic" for item in created) == 2
    assert sum(item.kind == "procedural" for item in created) == 1
    assert store.consolidation_targets(first.memory_id)
    assert store.consolidation_targets(second.memory_id)
    procedure = store.search("search files procedure", kinds={"procedural"}, limit=5)
    assert procedure and "postcondition probes match" in procedure[0].content

    # All source episodes have durable links, so consolidation is idempotent.
    assert store.unconsolidated_episodes() == []
    assert learner.consolidate_verified_episodes(store.unconsolidated_episodes()) == []


def test_verified_failure_becomes_lesson_not_semantic_success(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    learner = MemoryLearner(store)
    failed = learner.record_verified_episode(
        goal="Launch editor",
        action_type="open_application",
        verification_result=_verification(False, GoalLifecycleState.FAILED),
        task_id="task-failed",
        task_type="action_intent",
    )

    created = learner.consolidate_verified_episodes(store.unconsolidated_episodes())

    assert len(created) == 1
    assert created[0].kind == "lesson"
    assert created[0].success is False
    assert store.consolidation_targets(failed.memory_id) == [created[0].memory_id]


def test_unverified_or_self_reported_episode_is_not_promoted_and_does_not_starve_queue(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    learner = MemoryLearner(store)
    store.add(
        "episodic",
        "The user claimed deployment succeeded",
        source="user_input",
        outcome="achieved",
        success=True,
    )
    learner.record_verified_episode(
        goal="Deploy service",
        action_type="run_command",
        verification_result=_verification(False, GoalLifecycleState.WAITING_FOR_EVIDENCE),
        task_id="task-unknown",
        task_type="action_intent",
    )

    created = learner.consolidate_verified_episodes(store.unconsolidated_episodes())

    assert created == []
    assert store.search("deployment succeeded", kinds={"semantic"}, limit=5) == []
    assert store.unconsolidated_episodes() == []


def test_runtime_consolidation_creates_durable_memory_and_is_idempotent(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    learner = MemoryLearner(store)
    for index in range(2):
        learner.record_verified_episode(
            goal=f"Find report {index}",
            action_type="search_files",
            verification_result=_verification(),
            task_id=f"task-{index}",
            task_type="search_intent",
        )

    runtime = object.__new__(CognitiveRuntime)
    runtime.memory = store
    runtime.learning = learner
    runtime.beliefs = SimpleNamespace(maintain=lambda: 0)
    runtime.causal_inference = SimpleNamespace(
        get_causal_graph_summary=lambda: {"num_edges": 0, "num_nodes": 0},
        graph=SimpleNamespace(edges={}),
    )
    runtime.world = SimpleNamespace(recent_observations=lambda limit=100: [])
    runtime.world_ingest = SimpleNamespace(ingest=lambda **kwargs: None)

    first = runtime.consolidate_memory()
    second = runtime.consolidate_memory()

    assert first["semantic_created"] == 2
    assert first["procedures_created"] == 1
    assert first["consolidated"] == 3
    assert second["consolidated"] == 0


def test_explicit_manual_consolidation_api_remains_supported(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    learner = MemoryLearner(store)
    created = learner.consolidate(
        [],
        semantic_facts=["A directly supplied fact"],
        procedures=["A directly supplied procedure"],
    )
    assert {item.kind for item in created} == {"semantic", "procedural"}
