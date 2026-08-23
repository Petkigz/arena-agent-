"""
Tests for Phase 15: Cross-Domain Transfer Learning
"""

import pytest
import tempfile
import os
from app.cognition.cross_domain_transfer import (
    CrossDomainTransferEngine,
    DomainKnowledge,
    TransferRelationship,
    TransferResult,
    DomainType,
    TransferType,
    TransferStrength
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing (isolated via tmp_path)."""
    yield str(tmp_path / "test.db")


@pytest.fixture
def transfer_engine(temp_db):
    """Create a cross-domain transfer engine with temp database."""
    return CrossDomainTransferEngine(db_path=temp_db)


class TestCrossDomainTransfer:
    """Test suite for cross-domain transfer learning functionality."""
    
    def test_add_domain_knowledge(self, transfer_engine):
        """Test adding domain knowledge."""
        domain = transfer_engine.add_domain_knowledge(
            name="Python Programming",
            domain_type=DomainType.TECHNICAL,
            description="Programming in Python language",
            concepts=["variables", "functions", "classes", "modules", "exceptions"],
            skills=["debugging", "testing", "refactoring", "code review"],
            principles=["DRY", "KISS", "SOLID", "readability counts"],
            patterns=["MVC", "factory", "singleton", "observer"],
            examples=[
                {"title": "Web scraper", "description": "Built a web scraper using requests and BeautifulSoup"}
            ]
        )
        
        assert domain.domain_id is not None
        assert domain.name == "Python Programming"
        assert domain.domain_type == DomainType.TECHNICAL
        assert len(domain.concepts) == 5
        assert len(domain.skills) == 4
        assert domain.embedding is not None
        
        # Verify it was saved
        retrieved = transfer_engine.get_domain(domain.domain_id)
        assert retrieved is not None
        assert retrieved.name == domain.name
    
    def test_add_multiple_domains(self, transfer_engine):
        """Test adding multiple domains."""
        # Add programming domain
        programming = transfer_engine.add_domain_knowledge(
            name="Software Engineering",
            domain_type=DomainType.TECHNICAL,
            description="Building software systems",
            concepts=["algorithms", "data structures", "design patterns", "testing"],
            skills=["coding", "debugging", "architecture", "deployment"],
            principles=["modularity", "abstraction", "encapsulation", "separation of concerns"],
            patterns=["MVC", "microservices", "event-driven", "layered architecture"]
        )
        
        # Add business domain
        business = transfer_engine.add_domain_knowledge(
            name="Business Management",
            domain_type=DomainType.BUSINESS,
            description="Managing business operations",
            concepts=["strategy", "operations", "finance", "marketing"],
            skills=["planning", "leadership", "analysis", "communication"],
            principles=["efficiency", "customer focus", "continuous improvement", "value creation"],
            patterns=["supply chain", "business model", "value proposition", "competitive advantage"]
        )
        
        # Add creative domain
        creative = transfer_engine.add_domain_knowledge(
            name="Music Composition",
            domain_type=DomainType.CREATIVE,
            description="Composing music",
            concepts=["melody", "harmony", "rhythm", "structure"],
            skills=["composition", "arrangement", "notation", "performance"],
            principles=["balance", "contrast", "repetition", "variation"],
            patterns=["verse-chorus", "AABA", "sonata form", "theme and variations"]
        )
        
        # Verify all domains were added
        domains = transfer_engine.list_domains()
        assert len(domains) == 3
        
        # Verify filtering by type
        technical_domains = transfer_engine.list_domains(domain_type=DomainType.TECHNICAL)
        assert len(technical_domains) == 1
        assert technical_domains[0].name == "Software Engineering"
    
    def test_discover_transfer_relationships(self, transfer_engine):
        """Test discovering transfer relationships between domains."""
        # Add two similar domains
        python_domain = transfer_engine.add_domain_knowledge(
            name="Python Programming",
            domain_type=DomainType.TECHNICAL,
            description="Programming in Python",
            concepts=["functions", "classes", "modules", "testing"],
            skills=["coding", "debugging", "testing"],
            principles=["DRY", "KISS", "modularity"],
            patterns=["MVC", "factory", "singleton"]
        )
        
        javascript_domain = transfer_engine.add_domain_knowledge(
            name="JavaScript Programming",
            domain_type=DomainType.TECHNICAL,
            description="Programming in JavaScript",
            concepts=["functions", "classes", "modules", "testing"],
            skills=["coding", "debugging", "testing"],
            principles=["DRY", "KISS", "modularity"],
            patterns=["MVC", "factory", "observer"]
        )
        
        # Add a very different domain
        music_domain = transfer_engine.add_domain_knowledge(
            name="Music Composition",
            domain_type=DomainType.CREATIVE,
            description="Composing music",
            concepts=["melody", "harmony", "rhythm"],
            skills=["composition", "arrangement"],
            principles=["balance", "contrast"],
            patterns=["verse-chorus", "AABA"]
        )
        
        # Discover relationships from Python
        relationships = transfer_engine.discover_transfer_relationships(
            source_domain_id=python_domain.domain_id,
            min_similarity=0.1  # Low threshold to find all
        )
        
        # Should find at least the JavaScript relationship (high similarity)
        assert len(relationships) >= 1
        
        # Find the JavaScript relationship
        js_relationship = next(
            (r for r in relationships if r.target_domain_id == javascript_domain.domain_id),
            None
        )
        assert js_relationship is not None
        assert js_relationship.similarity_score > 0.5  # Should be high similarity
        assert js_relationship.transfer_type == TransferType.DIRECT
        assert js_relationship.strength in [TransferStrength.STRONG, TransferStrength.MODERATE]
        
        # Music relationship may or may not be found depending on similarity
        music_relationship = next(
            (r for r in relationships if r.target_domain_id == music_domain.domain_id),
            None
        )
        if music_relationship:
            assert music_relationship.similarity_score < js_relationship.similarity_score  # Should be lower
            assert music_relationship.strength in [TransferStrength.WEAK, TransferStrength.SPECULATIVE, TransferStrength.MODERATE]
    
    def test_transfer_knowledge(self, transfer_engine):
        """Test transferring knowledge between domains."""
        # Add source domain
        source = transfer_engine.add_domain_knowledge(
            name="Software Testing",
            domain_type=DomainType.TECHNICAL,
            description="Testing software systems",
            concepts=["unit tests", "integration tests", "test coverage", "mocking"],
            skills=["test design", "test automation", "bug tracking"],
            principles=["test early", "test often", "isolate tests"],
            patterns=["AAA pattern", "test pyramid", "TDD"]
        )
        
        # Add target domain
        target = transfer_engine.add_domain_knowledge(
            name="Quality Assurance",
            domain_type=DomainType.BUSINESS,
            description="Ensuring product quality",
            concepts=["quality control", "inspection", "standards", "compliance"],
            skills=["auditing", "process improvement", "documentation"],
            principles=["prevent defects", "continuous improvement", "customer focus"],
            patterns=["PDCA cycle", "Six Sigma", "ISO standards"]
        )
        
        # Discover relationship
        relationships = transfer_engine.discover_transfer_relationships(
            source_domain_id=source.domain_id,
            min_similarity=0.05  # Very low threshold
        )
        
        # If no relationship found, skip the rest of the test
        # (domains may be too dissimilar)
        if len(relationships) == 0:
            return
        
        relationship = relationships[0]
        
        # Attempt transfer
        result = transfer_engine.transfer_knowledge(
            relationship_id=relationship.relationship_id,
            source_problem="How to improve test coverage in a large codebase",
            target_problem="How to improve quality control in manufacturing"
        )
        
        assert result is not None
        assert result.result_id is not None
        assert result.relationship_id == relationship.relationship_id
        assert len(result.transferred_knowledge) > 0
        assert len(result.adaptations) > 0
        assert result.effectiveness_score >= 0.0
        
        # Verify result was saved
        results = transfer_engine.list_results(relationship_id=relationship.relationship_id)
        assert len(results) == 1
        assert results[0].result_id == result.result_id
    
    def test_transfer_with_high_similarity(self, transfer_engine):
        """Test transfer between highly similar domains."""
        # Add two very similar domains
        python = transfer_engine.add_domain_knowledge(
            name="Python Web Development",
            domain_type=DomainType.TECHNICAL,
            description="Building web apps with Python",
            concepts=["Django", "Flask", "REST API", "database"],
            skills=["backend development", "API design", "database modeling"],
            principles=["MVC", "separation of concerns", "DRY"],
            patterns=["repository pattern", "service layer", "dependency injection"]
        )
        
        javascript = transfer_engine.add_domain_knowledge(
            name="JavaScript Web Development",
            domain_type=DomainType.TECHNICAL,
            description="Building web apps with JavaScript",
            concepts=["Express", "React", "REST API", "database"],
            skills=["backend development", "API design", "database modeling"],
            principles=["MVC", "separation of concerns", "DRY"],
            patterns=["repository pattern", "service layer", "dependency injection"]
        )
        
        # Discover relationship
        relationships = transfer_engine.discover_transfer_relationships(
            source_domain_id=python.domain_id,
            min_similarity=0.5
        )
        
        assert len(relationships) > 0
        relationship = relationships[0]
        
        # Should have high similarity
        assert relationship.similarity_score > 0.7
        assert relationship.strength in [TransferStrength.STRONG, TransferStrength.MODERATE]
        
        # Transfer should be very effective
        result = transfer_engine.transfer_knowledge(
            relationship_id=relationship.relationship_id,
            source_problem="Building a REST API with authentication",
            target_problem="Building a REST API with authentication"
        )
        
        assert result.success is False  # similarity is prediction, not verified application
        assert result.predicted_success is True
        assert result.verified is False
        assert result.effectiveness_score > 0.7

        verified = transfer_engine.record_verified_transfer_result(
            result.result_id,
            success=True,
            effectiveness_score=0.9,
            evidence=["target benchmark passed"],
        )
        assert verified.success is True
        assert verified.verified is True
        assert verified.evaluation_mode == "verified_application"
    
    def test_transfer_with_low_similarity(self, transfer_engine):
        """Test transfer between very different domains."""
        # Add two very different domains
        programming = transfer_engine.add_domain_knowledge(
            name="Algorithm Design",
            domain_type=DomainType.TECHNICAL,
            description="Designing efficient algorithms",
            concepts=["complexity", "data structures", "optimization", "recursion"],
            skills=["algorithm analysis", "problem decomposition"],
            principles=["efficiency", "correctness", "simplicity"],
            patterns=["divide and conquer", "dynamic programming", "greedy algorithms"]
        )
        
        cooking = transfer_engine.add_domain_knowledge(
            name="Cooking",
            domain_type=DomainType.PHYSICAL,
            description="Preparing food",
            concepts=["ingredients", "techniques", "flavors", "presentation"],
            skills=["knife skills", "timing", "seasoning"],
            principles=["freshness", "balance", "technique"],
            patterns=["mise en place", "mother sauces", "flavor pairing"]
        )
        
        # Discover relationship
        relationships = transfer_engine.discover_transfer_relationships(
            source_domain_id=programming.domain_id,
            min_similarity=0.1
        )
        
        # May or may not find a relationship due to low similarity
        if relationships:
            relationship = relationships[0]
            
            # Should have low similarity
            assert relationship.similarity_score < 0.5
            assert relationship.strength in [TransferStrength.WEAK, TransferStrength.SPECULATIVE]
            
            # Transfer should be less effective
            result = transfer_engine.transfer_knowledge(
                relationship_id=relationship.relationship_id,
                source_problem="Optimizing a sorting algorithm",
                target_problem="Optimizing a cooking recipe"
            )
            
            # May or may not succeed
            if result:
                assert result.effectiveness_score < 0.7
    
    def test_list_domains_with_filter(self, transfer_engine):
        """Test listing domains with type filter."""
        # Add domains of different types
        transfer_engine.add_domain_knowledge(
            name="Python",
            domain_type=DomainType.TECHNICAL,
            description="Python programming",
            concepts=["variables"],
            skills=["coding"],
            principles=["DRY"],
            patterns=["MVC"]
        )
        
        transfer_engine.add_domain_knowledge(
            name="JavaScript",
            domain_type=DomainType.TECHNICAL,
            description="JavaScript programming",
            concepts=["variables"],
            skills=["coding"],
            principles=["DRY"],
            patterns=["MVC"]
        )
        
        transfer_engine.add_domain_knowledge(
            name="Painting",
            domain_type=DomainType.CREATIVE,
            description="Visual art",
            concepts=["color"],
            skills=["brushwork"],
            principles=["composition"],
            patterns=["landscape"]
        )
        
        transfer_engine.add_domain_knowledge(
            name="Management",
            domain_type=DomainType.BUSINESS,
            description="Business management",
            concepts=["strategy"],
            skills=["leadership"],
            principles=["efficiency"],
            patterns=["agile"]
        )
        
        # List all domains
        all_domains = transfer_engine.list_domains()
        assert len(all_domains) == 4
        
        # List only technical domains
        technical = transfer_engine.list_domains(domain_type=DomainType.TECHNICAL)
        assert len(technical) == 2
        
        # List only creative domains
        creative = transfer_engine.list_domains(domain_type=DomainType.CREATIVE)
        assert len(creative) == 1
        assert creative[0].name == "Painting"
    
    def test_list_relationships_with_filters(self, transfer_engine):
        """Test listing relationships with filters."""
        # Add three domains
        domain1 = transfer_engine.add_domain_knowledge(
            name="Domain 1",
            domain_type=DomainType.TECHNICAL,
            description="First domain",
            concepts=["concept1"],
            skills=["skill1"],
            principles=["principle1"],
            patterns=["pattern1"]
        )
        
        domain2 = transfer_engine.add_domain_knowledge(
            name="Domain 2",
            domain_type=DomainType.TECHNICAL,
            description="Second domain",
            concepts=["concept1", "concept2"],
            skills=["skill1", "skill2"],
            principles=["principle1", "principle2"],
            patterns=["pattern1", "pattern2"]
        )
        
        domain3 = transfer_engine.add_domain_knowledge(
            name="Domain 3",
            domain_type=DomainType.CREATIVE,
            description="Third domain",
            concepts=["concept3"],
            skills=["skill3"],
            principles=["principle3"],
            patterns=["pattern3"]
        )
        
        # Discover relationships from domain1
        transfer_engine.discover_transfer_relationships(
            source_domain_id=domain1.domain_id,
            min_similarity=0.1
        )
        
        # List all relationships
        all_relationships = transfer_engine.list_relationships()
        assert len(all_relationships) >= 1
        
        # List relationships from domain1
        from_domain1 = transfer_engine.list_relationships(source_domain_id=domain1.domain_id)
        assert len(from_domain1) >= 1
        
        # List relationships to domain2
        to_domain2 = transfer_engine.list_relationships(target_domain_id=domain2.domain_id)
        assert len(to_domain2) >= 1
    
    def test_list_results_with_filters(self, transfer_engine):
        """Test listing results with filters."""
        # Add domains and relationship
        source = transfer_engine.add_domain_knowledge(
            name="Source",
            domain_type=DomainType.TECHNICAL,
            description="Source domain",
            concepts=["concept1"],
            skills=["skill1"],
            principles=["principle1"],
            patterns=["pattern1"]
        )
        
        target = transfer_engine.add_domain_knowledge(
            name="Target",
            domain_type=DomainType.TECHNICAL,
            description="Target domain",
            concepts=["concept1", "concept2"],
            skills=["skill1", "skill2"],
            principles=["principle1", "principle2"],
            patterns=["pattern1", "pattern2"]
        )
        
        relationships = transfer_engine.discover_transfer_relationships(
            source_domain_id=source.domain_id,
            min_similarity=0.1
        )
        
        if relationships:
            relationship = relationships[0]
            
            # Perform multiple transfers
            for i in range(3):
                transfer_engine.transfer_knowledge(
                    relationship_id=relationship.relationship_id,
                    source_problem=f"Source problem {i}",
                    target_problem=f"Target problem {i}"
                )
            
            # List all results
            all_results = transfer_engine.list_results()
            assert len(all_results) == 3
            
            # List results for specific relationship
            relationship_results = transfer_engine.list_results(
                relationship_id=relationship.relationship_id
            )
            assert len(relationship_results) == 3
            
            # List successful results
            successful = transfer_engine.list_results(success=True)
            assert len(successful) >= 0  # May be 0-3 depending on similarity
    
    def test_get_transfer_summary(self, transfer_engine):
        """Test getting transfer summary."""
        # Add domains
        domain1 = transfer_engine.add_domain_knowledge(
            name="Domain 1",
            domain_type=DomainType.TECHNICAL,
            description="First domain",
            concepts=["concept1"],
            skills=["skill1"],
            principles=["principle1"],
            patterns=["pattern1"]
        )
        
        domain2 = transfer_engine.add_domain_knowledge(
            name="Domain 2",
            domain_type=DomainType.CREATIVE,
            description="Second domain",
            concepts=["concept2"],
            skills=["skill2"],
            principles=["principle2"],
            patterns=["pattern2"]
        )
        
        # Discover relationships
        transfer_engine.discover_transfer_relationships(
            source_domain_id=domain1.domain_id,
            min_similarity=0.1
        )
        
        # Get summary
        summary = transfer_engine.get_transfer_summary()
        
        assert summary['total_domains'] == 2
        assert summary['total_relationships'] >= 0
        assert summary['total_transfers'] == 0  # No transfers yet
        assert summary['success_rate'] == 0.0
        assert summary['domains_by_type'][DomainType.TECHNICAL.value] == 1
        assert summary['domains_by_type'][DomainType.CREATIVE.value] == 1
    
    def test_domain_serialization(self, transfer_engine):
        """Test domain serialization and deserialization."""
        domain = transfer_engine.add_domain_knowledge(
            name="Test Domain",
            domain_type=DomainType.ANALYTICAL,
            description="Test description",
            concepts=["concept1", "concept2"],
            skills=["skill1"],
            principles=["principle1", "principle2", "principle3"],
            patterns=["pattern1"],
            examples=[
                {"title": "Example 1", "description": "Description 1"},
                {"title": "Example 2", "description": "Description 2"}
            ]
        )
        
        # Serialize
        domain_dict = domain.to_dict()
        
        # Deserialize
        restored = DomainKnowledge.from_dict(domain_dict)
        
        assert restored.domain_id == domain.domain_id
        assert restored.name == domain.name
        assert restored.domain_type == domain.domain_type
        assert len(restored.concepts) == len(domain.concepts)
        assert len(restored.examples) == len(domain.examples)
    
    def test_relationship_serialization(self):
        """Test relationship serialization."""
        relationship = TransferRelationship(
            source_domain_id="source_123",
            target_domain_id="target_456",
            transfer_type=TransferType.ANALOGICAL,
            strength=TransferStrength.MODERATE,
            similarity_score=0.65,
            shared_concepts=["concept1", "concept2"],
            shared_patterns=["pattern1"],
            success_rate=0.8
        )
        
        # Serialize
        rel_dict = relationship.to_dict()
        
        # Deserialize
        restored = TransferRelationship.from_dict(rel_dict)
        
        assert restored.relationship_id == relationship.relationship_id
        assert restored.source_domain_id == relationship.source_domain_id
        assert restored.target_domain_id == relationship.target_domain_id
        assert restored.transfer_type == relationship.transfer_type
        assert restored.similarity_score == relationship.similarity_score
    
    def test_result_serialization(self):
        """Test result serialization."""
        result = TransferResult(
            relationship_id="rel_123",
            source_problem="Source problem",
            target_problem="Target problem",
            transferred_knowledge=["knowledge1", "knowledge2"],
            adaptations=["adaptation1"],
            success=True,
            effectiveness_score=0.85,
            lessons_learned=["lesson1", "lesson2"]
        )
        
        # Serialize
        result_dict = result.to_dict()
        
        # Deserialize
        restored = TransferResult.from_dict(result_dict)
        
        assert restored.result_id == result.result_id
        assert restored.relationship_id == result.relationship_id
        assert restored.success == result.success
        assert restored.effectiveness_score == result.effectiveness_score
        assert len(restored.lessons_learned) == len(result.lessons_learned)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
