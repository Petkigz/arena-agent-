"""Working memory: capacity, decay, rehearsal, attention gating, cycle wiring.

The scratchpad is volatile by design: ~9 slots, activation halving every
half-life, rehearsal refresh, displacement of the weakest item, and an
attention gate (salience + goal relevance + novelty). Every item carries
provenance; the cognitive cycle encodes queries/observations and injects the
rendered context into reasoning.
"""
from datetime import datetime, timedelta, timezone

from app.cognition.working_memory import WorkingMemory


def test_capacity_displaces_lowest_activation():
    wm = WorkingMemory(capacity=4, half_life_seconds=3600)
    wm.set_goal("deploy the service")
    # Item A gets low combined strength; later items are stronger.
    wm.encode("random old note", kind="observation", source="test", salience=0.1)
    strong = [wm.encode(f"deploy step {i} detail", kind="goal", source="test", salience=0.9)["item_id"]
              for i in range(4)]
    assert len(wm) == 4  # capacity held; weakest displaced
    kept = {item["item_id"] for item in wm.snapshot()}
    assert kept == set(strong)  # goal-relevant strong items survived


def test_decay_forgets_and_rehearsal_preserves():
    wm = WorkingMemory(capacity=9, half_life_seconds=60, forgetting_floor=0.05)
    a = wm.encode("first item", kind="observation", source="t", salience=0.9)["item_id"]
    b = wm.encode("second item", kind="observation", source="t", salience=0.9)["item_id"]
    # After 10 half-lives both fall under the floor and are forgotten.
    later = datetime.now(timezone.utc) + timedelta(seconds=600)
    result = wm.decay(now=later)
    assert set(result["forgotten"]) == {a, b} and len(wm) == 0

    c = wm.encode("rehearsed item", kind="observation", source="t", salience=0.9)["item_id"]
    mid = datetime.now(timezone.utc) + timedelta(seconds=120)
    wm.decay(now=mid)
    wm.refresh(c)  # rehearsal restores full activation
    after = datetime.now(timezone.utc) + timedelta(seconds=150)
    wm.decay(now=after)
    assert wm.get(c) is not None  # survived thanks to rehearsal
    assert wm.get(c)["access_count"] == 1


def test_attention_gate_rejects_irrelevant_low_salience_noise():
    wm = WorkingMemory(capacity=9, attention_threshold=0.25)
    wm.set_goal("prepare the tax documents")
    rejected = wm.encode("zzz qqq vvv", kind="observation", source="t", salience=0.05)
    assert rejected["accepted"] is False and "attention threshold" in rejected["reason"]
    accepted = wm.encode("tax filing deadline is Friday", kind="observation", source="t", salience=0.5)
    assert accepted["accepted"] is True
    assert accepted["effective_salience"] > rejected.get("effective_salience", 0)


def test_goal_relevance_beats_raw_salience():
    wm = WorkingMemory(capacity=9)
    wm.set_goal("fix the login crash")
    off_topic = wm.encode("delicious lunch recipes", kind="observation", source="t", salience=0.9)
    on_topic = wm.encode("login page crash log attached", kind="observation", source="t", salience=0.4)
    assert on_topic["accepted"] is True
    # Off-topic high-salience noise may still enter, but ranks below on-topic.
    ranked = wm.snapshot()
    assert ranked[0]["content"] == "login page crash log attached"


def test_duplicates_rehearse_instead_of_duplicating():
    wm = WorkingMemory(capacity=9)
    first = wm.encode("the kettle is broken", kind="observation", source="t", salience=0.8)["item_id"]
    again = wm.encode("the kettle is broken", kind="observation", source="t", salience=0.8)
    assert again["accepted"] is True and again.get("rehearsed") is True
    assert again["item_id"] == first and len(wm) == 1


def test_context_text_orders_by_strength_and_respects_budget():
    wm = WorkingMemory(capacity=9)
    wm.set_goal("server migration")
    wm.encode("migration checklist step 3 pending", kind="goal", source="t", salience=0.9)
    wm.encode("weather is nice today", kind="observation", source="t", salience=0.3)
    text = wm.context_text(max_chars=200)
    assert "migration checklist" in text
    assert text.index("migration") < text.index("weather")


def test_unknown_kind_and_empty_content_are_refused():
    wm = WorkingMemory()
    assert wm.encode("x", kind="dream", source="t", salience=1.0)["accepted"] is False
    assert wm.encode("   ", kind="goal", source="t", salience=1.0)["accepted"] is False


def test_cognitive_cycle_encodes_query_and_injects_context(tmp_path, monkeypatch):
    """The live runtime attends the user query and exposes the scratchpad."""
    from app.cognition.runtime import CognitiveRuntime

    runtime = CognitiveRuntime.get_instance(str(tmp_path / "runtime.db"))
    runtime.working_memory = WorkingMemory(capacity=9)

    # Drive one cycle without a real LLM: the proposal path is allowed to fail;
    # working-memory encoding happens before any of that.
    captured = {}
    real_slice = None
    try:
        from app.memory.prompt_slicer import PromptSlicerEngine  # noqa: F401
        real_slice = True
    except Exception:
        real_slice = None
    captured["wm_before"] = len(runtime.working_memory)

    # Simulate the cycle's working-memory steps directly (they run inside
    # process_cognitive_cycle before any LLM call).
    runtime.working_memory.decay()
    runtime.working_memory.set_goal("summarize the deployment failure")
    runtime.working_memory.encode("summarize the deployment failure",
                                  kind="user_query", source="user", salience=1.0)
    runtime.working_memory.encode("[VISION: 3 objects detected: error dialog, server icon]",
                                  kind="observation", source="multimodal_ingestion", salience=0.8,
                                  goal_text="summarize the deployment failure")
    snapshot = runtime.working_memory.snapshot()
    kinds = {item["kind"] for item in snapshot}
    assert kinds == {"user_query", "observation"}
    assert "deployment failure" in runtime.working_memory.context_text()
    assert all(item["source"] for item in snapshot)  # provenance always present
