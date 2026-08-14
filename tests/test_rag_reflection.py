import pytest
from app.database import db
from app.memory.semantic_rag import SemanticRAGEngine
from app.memory.reflection_engine import ReflectionEngine
from app.memory.decision_constitution import DecisionConstitution

def test_semantic_rag_search():
    # Save test memory
    db.create_memory({
        "content": "RAG Test Fact: User prefers dark mode interface and fast responses.",
        "category": "preference",
        "source": "unit_test",
        "confidence": 1.0
    })

    results = SemanticRAGEngine.search_memories("dark mode interface", limit=3)
    assert len(results) > 0
    assert any("dark mode" in m["content"] for m in results)

    context_str = SemanticRAGEngine.build_rag_context("dark mode interface")
    assert "RELEVANT PAST MEMORIES" in context_str

def test_decision_constitution():
    summary = DecisionConstitution.get_constitution_summary()
    assert "Frugality" in summary
    assert "Safety First" in summary

    res = DecisionConstitution.evaluate_decision("send email to external user", "context")
    assert res["compliant"] is False
    assert len(res["violations"]) > 0

def test_reflection_engine():
    res = ReflectionEngine.reflect_on_task_execution(
        task_title="Build RAG Engine",
        task_goal="Index SQLite memories for prompt context",
        outcome_summary="RAG engine built and tested.",
        user_feedback="Works great!"
    )
    assert res["success"] is True
    assert res["memory_id"] is not None
