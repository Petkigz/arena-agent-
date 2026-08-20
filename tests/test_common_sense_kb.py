"""Tests for Common Sense Knowledge Base."""

import pytest
import tempfile
import os
from app.cognition.common_sense import CommonSenseKnowledgeBase, CommonSenseFact


class TestCommonSenseKnowledgeBase:
    """Test Common Sense Knowledge Base functionality."""

    @pytest.fixture
    def kb(self, tmp_path):
        """Create a knowledge base instance with temporary database."""
        db_path = str(tmp_path / "test_common_sense.db")
        return CommonSenseKnowledgeBase(db_path=db_path)

    def test_initialization(self, kb):
        """Test KB initializes without errors."""
        assert kb is not None
        assert kb.db_path is not None

    def test_fact_count(self, kb):
        """Test that KB loads facts on initialization."""
        total = kb.count_facts()
        assert total > 0, "Knowledge base should contain facts"
        assert total >= 700, f"Expected at least 700 facts, got {total}"

    def test_count_by_category(self, kb):
        """Test counting facts by category."""
        categories = ["physical", "human", "causal", "temporal", "spatial"]
        
        for category in categories:
            count = kb.count_facts(category=category)
            assert count > 0, f"Category '{category}' should have facts"

    def test_query_by_category(self, kb):
        """Test querying facts by category."""
        physical_facts = kb.query_facts(category="physical", limit=10)
        
        assert len(physical_facts) > 0
        assert len(physical_facts) <= 10
        
        for fact in physical_facts:
            assert fact.category == "physical"
            assert fact.fact_id is not None
            assert fact.fact is not None

    def test_query_by_search(self, kb):
        """Test querying facts by search term."""
        gravity_facts = kb.query_facts(query="gravity", limit=10)
        
        assert len(gravity_facts) > 0
        
        # At least one fact should contain the word "gravity"
        has_gravity = any("gravity" in fact.fact.lower() for fact in gravity_facts)
        assert has_gravity

    def test_query_by_category_and_search(self, kb):
        """Test querying facts by both category and search term."""
        physical_water = kb.query_facts(category="physical", query="water", limit=10)
        
        assert len(physical_water) > 0
        
        for fact in physical_water:
            assert fact.category == "physical"
            assert "water" in fact.fact.lower()

    def test_get_fact_by_id(self, kb):
        """Test retrieving a specific fact by ID."""
        # Get first fact
        facts = kb.query_facts(limit=1)
        assert len(facts) > 0
        
        fact_id = facts[0].fact_id
        retrieved = kb.get_fact(fact_id)
        
        assert retrieved is not None
        assert retrieved.fact_id == fact_id
        assert retrieved.fact == facts[0].fact

    def test_get_nonexistent_fact(self, kb):
        """Test retrieving a fact that doesn't exist."""
        result = kb.get_fact("nonexistent_fact_id")
        assert result is None

    def test_add_fact(self, kb):
        """Test adding a new fact."""
        new_fact = CommonSenseFact(
            fact_id="test_fact_001",
            category="physical",
            fact="Test fact for unit testing",
            confidence=0.95
        )
        
        success = kb.add_fact(new_fact)
        assert success
        
        # Verify it was added
        retrieved = kb.get_fact("test_fact_001")
        assert retrieved is not None
        assert retrieved.fact == "Test fact for unit testing"
        assert retrieved.confidence == 0.95

    def test_reason_about(self, kb):
        """Test reasoning about a query."""
        results = kb.reason_about("What happens when you drop something?")
        
        assert len(results) > 0
        assert len(results) <= 5  # Should return top 5
        
        # Results should be sorted by relevance
        for fact in results:
            assert fact.fact is not None
            assert fact.confidence > 0

    def test_reason_about_with_category(self, kb):
        """Test reasoning about a query with category filter."""
        results = kb.reason_about("How do people feel?", category="human")
        
        assert len(results) > 0
        
        for fact in results:
            assert fact.category == "human"

    def test_fact_dataclass(self):
        """Test CommonSenseFact dataclass."""
        fact = CommonSenseFact(
            fact_id="test_001",
            category="physical",
            fact="Test fact",
            confidence=0.9
        )
        
        assert fact.fact_id == "test_001"
        assert fact.category == "physical"
        assert fact.fact == "Test fact"
        assert fact.confidence == 0.9
        assert fact.source == "common_sense"

    def test_fact_to_dict(self):
        """Test converting fact to dictionary."""
        fact = CommonSenseFact(
            fact_id="test_001",
            category="physical",
            fact="Test fact",
            confidence=0.9
        )
        
        data = fact.to_dict()
        
        assert data["fact_id"] == "test_001"
        assert data["category"] == "physical"
        assert data["fact"] == "Test fact"
        assert data["confidence"] == 0.9

    def test_fact_from_dict(self):
        """Test creating fact from dictionary."""
        data = {
            "fact_id": "test_001",
            "category": "physical",
            "fact": "Test fact",
            "confidence": 0.9
        }
        
        fact = CommonSenseFact.from_dict(data)
        
        assert fact.fact_id == "test_001"
        assert fact.category == "physical"
        assert fact.fact == "Test fact"
        assert fact.confidence == 0.9

    def test_database_persistence(self, tmp_path):
        """Test that facts persist across KB instances."""
        db_path = str(tmp_path / "persist_test.db")
        
        # Create KB and add fact
        kb1 = CommonSenseKnowledgeBase(db_path=db_path)
        new_fact = CommonSenseFact(
            fact_id="persist_test_001",
            category="physical",
            fact="Persistence test fact",
            confidence=1.0
        )
        kb1.add_fact(new_fact)
        
        # Create new KB instance with same path
        kb2 = CommonSenseKnowledgeBase(db_path=db_path)
        
        # Verify fact persists
        retrieved = kb2.get_fact("persist_test_001")
        assert retrieved is not None
        assert retrieved.fact == "Persistence test fact"

    def test_query_limit(self, kb):
        """Test that query respects limit parameter."""
        results = kb.query_facts(limit=5)
        assert len(results) <= 5
        
        results = kb.query_facts(limit=1)
        assert len(results) <= 1

    def test_empty_query(self, kb):
        """Test query with no matches."""
        results = kb.query_facts(query="xyznonexistentterm123", limit=10)
        assert len(results) == 0

    def test_all_categories_have_facts(self, kb):
        """Test that all expected categories have facts."""
        expected_categories = {"physical", "human", "causal", "temporal", "spatial", "technology", "everyday"}
        
        all_facts = kb.query_facts(limit=1000)
        actual_categories = {fact.category for fact in all_facts}
        
        for category in expected_categories:
            assert category in actual_categories, f"Category '{category}' should have facts"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
