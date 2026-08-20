"""Tests for Causal Inference Engine (Phase 12)."""

import pytest
import tempfile
from pathlib import Path
from app.cognition.causal_inference import (
    CausalInferenceEngine,
    CausalGraph,
    CausalNode,
    CausalEdge,
    CausalRelationType,
    InterventionType,
    CausalQuery
)


class TestCausalGraph:
    """Test CausalGraph class."""
    
    def test_add_node(self):
        """Test adding nodes to graph."""
        graph = CausalGraph()
        node = CausalNode(node_id="test_node", name="Test Variable")
        graph.add_node(node)
        
        assert "test_node" in graph.nodes
        assert graph.nodes["test_node"].name == "Test Variable"
    
    def test_add_edge(self):
        """Test adding edges to graph."""
        graph = CausalGraph()
        node1 = CausalNode(node_id="node1", name="Cause")
        node2 = CausalNode(node_id="node2", name="Effect")
        graph.add_node(node1)
        graph.add_node(node2)
        
        edge = CausalEdge(
            edge_id="edge1",
            source_id="node1",
            target_id="node2",
            relation_type=CausalRelationType.DIRECT_CAUSE,
            strength=0.8,
            confidence=0.9
        )
        graph.add_edge(edge)
        
        assert "edge1" in graph.edges
        assert "node2" in graph.adjacency["node1"]
        assert "node1" in graph.reverse_adjacency["node2"]
    
    def test_get_parents_children(self):
        """Test getting parent and child nodes."""
        graph = CausalGraph()
        node1 = CausalNode(node_id="node1", name="Cause")
        node2 = CausalNode(node_id="node2", name="Effect")
        graph.add_node(node1)
        graph.add_node(node2)
        
        edge = CausalEdge(
            edge_id="edge1",
            source_id="node1",
            target_id="node2",
            relation_type=CausalRelationType.DIRECT_CAUSE
        )
        graph.add_edge(edge)
        
        assert graph.get_parents("node2") == ["node1"]
        assert graph.get_children("node1") == ["node2"]
    
    def test_get_ancestors_descendants(self):
        """Test getting ancestors and descendants."""
        graph = CausalGraph()
        
        # Create chain: A → B → C
        for i, name in enumerate(["A", "B", "C"]):
            graph.add_node(CausalNode(node_id=f"node{i}", name=name))
        
        graph.add_edge(CausalEdge(
            edge_id="edge1",
            source_id="node0",
            target_id="node1",
            relation_type=CausalRelationType.DIRECT_CAUSE
        ))
        graph.add_edge(CausalEdge(
            edge_id="edge2",
            source_id="node1",
            target_id="node2",
            relation_type=CausalRelationType.DIRECT_CAUSE
        ))
        
        ancestors = graph.get_ancestors("node2")
        assert "node0" in ancestors
        assert "node1" in ancestors
        
        descendants = graph.get_descendants("node0")
        assert "node1" in descendants
        assert "node2" in descendants
    
    def test_get_causal_path(self):
        """Test finding causal paths."""
        graph = CausalGraph()
        
        # Create chain: A → B → C
        for i, name in enumerate(["A", "B", "C"]):
            graph.add_node(CausalNode(node_id=f"node{i}", name=name))
        
        graph.add_edge(CausalEdge(
            edge_id="edge1",
            source_id="node0",
            target_id="node1",
            relation_type=CausalRelationType.DIRECT_CAUSE
        ))
        graph.add_edge(CausalEdge(
            edge_id="edge2",
            source_id="node1",
            target_id="node2",
            relation_type=CausalRelationType.DIRECT_CAUSE
        ))
        
        path = graph.get_causal_path("node0", "node2")
        assert path == ["node0", "node1", "node2"]
        
        # No path case
        graph.add_node(CausalNode(node_id="node3", name="D"))
        no_path = graph.get_causal_path("node0", "node3")
        assert no_path is None
    
    def test_serialization(self):
        """Test graph serialization to/from dict."""
        graph = CausalGraph()
        node = CausalNode(node_id="test", name="Test")
        graph.add_node(node)
        
        data = graph.to_dict()
        restored = CausalGraph.from_dict(data)
        
        assert "test" in restored.nodes
        assert restored.nodes["test"].name == "Test"


class TestCausalInferenceEngine:
    """Test CausalInferenceEngine class."""
    
    @pytest.fixture
    def engine(self, tmp_path):
        """Create a test engine with temporary database."""
        db_path = str(tmp_path / "test_causal.db")
        return CausalInferenceEngine(db_path=db_path)
    
    def test_initialization(self, engine):
        """Test engine initialization."""
        assert engine is not None
        assert engine.graph is not None
    
    def test_add_causal_relationship(self, engine):
        """Test adding causal relationships."""
        edge_id = engine.add_causal_relationship(
            cause_name="Rain",
            effect_name="Wet Ground",
            relation_type=CausalRelationType.DIRECT_CAUSE,
            strength=0.9,
            confidence=0.95,
            evidence=["Observed rain followed by wet ground"],
            mechanism="Rain water makes ground wet"
        )
        
        assert edge_id is not None
        assert len(engine.graph.nodes) == 2
        assert len(engine.graph.edges) == 1
    
    def test_predict_intervention(self, engine):
        """Test intervention prediction."""
        # Build simple causal graph: Rain → Wet Ground
        engine.add_causal_relationship(
            cause_name="Rain",
            effect_name="Wet Ground",
            strength=0.9,
            confidence=0.95
        )
        
        query = engine.predict_intervention(
            intervention_variable="Rain",
            intervention_value="heavy",
            outcome_variable="Wet Ground"
        )
        
        assert query is not None
        assert query.query_type == InterventionType.DO
        assert query.causal_effect > 0
        assert query.confidence > 0
        assert query.predicted_outcome is not None
    
    def test_predict_intervention_no_path(self, engine):
        """Test intervention prediction with no causal path."""
        engine.add_causal_relationship(
            cause_name="A",
            effect_name="B"
        )
        engine.add_causal_relationship(
            cause_name="C",
            effect_name="D"
        )
        
        query = engine.predict_intervention(
            intervention_variable="A",
            intervention_value="x",
            outcome_variable="D"
        )
        
        assert query.causal_effect == 0.0
        assert "No causal path" in query.reasoning
    
    def test_counterfactual_reasoning(self, engine):
        """Test counterfactual reasoning."""
        engine.add_causal_relationship(
            cause_name="Study Hours",
            effect_name="Test Score",
            strength=0.8,
            confidence=0.9
        )
        
        query = engine.counterfactual_reasoning(
            observed_outcome=70,
            intervention_variable="Study Hours",
            counterfactual_value="10 hours",
            outcome_variable="Test Score"
        )
        
        assert query is not None
        assert query.query_type == InterventionType.COUNTERFACTUAL
        assert query.predicted_outcome is not None
        assert "Counterfactual" in query.reasoning
    
    def test_root_cause_analysis(self, engine):
        """Test root cause analysis."""
        # Build chain: A → B → C
        engine.add_causal_relationship(
            cause_name="A",
            effect_name="B",
            strength=0.9
        )
        engine.add_causal_relationship(
            cause_name="B",
            effect_name="C",
            strength=0.8
        )
        
        root_causes = engine.root_cause_analysis(
            outcome_variable="C",
            outcome_value="high"
        )
        
        assert len(root_causes) > 0
        # Should find both A and B as causes
        cause_names = [rc[0] for rc in root_causes]
        assert "A" in cause_names or "B" in cause_names
    
    def test_root_cause_analysis_no_outcome(self, engine):
        """Test root cause analysis with non-existent outcome."""
        root_causes = engine.root_cause_analysis(
            outcome_variable="NonExistent",
            outcome_value="x"
        )
        
        assert root_causes == []
    
    def test_query_history(self, engine):
        """Test query history retrieval."""
        engine.add_causal_relationship(
            cause_name="X",
            effect_name="Y"
        )
        
        # Make some queries
        engine.predict_intervention("X", "a", "Y")
        engine.predict_intervention("X", "b", "Y")
        
        history = engine.get_query_history(limit=10)
        
        assert len(history) == 2
        assert all(isinstance(q, CausalQuery) for q in history)
    
    def test_causal_graph_summary(self, engine):
        """Test graph summary."""
        engine.add_causal_relationship(
            cause_name="A",
            effect_name="B"
        )
        engine.add_causal_relationship(
            cause_name="B",
            effect_name="C"
        )
        
        summary = engine.get_causal_graph_summary()
        
        assert summary['num_nodes'] == 3
        assert summary['num_edges'] == 2
        assert len(summary['nodes']) == 3
        assert len(summary['edges']) == 2
    
    def test_graph_persistence(self, engine):
        """Test that graph persists across engine instances."""
        engine.add_causal_relationship(
            cause_name="Persistent",
            effect_name="Relationship"
        )
        
        # Create new engine with same db
        engine2 = CausalInferenceEngine(db_path=engine.db_path)
        
        assert len(engine2.graph.nodes) == 2
        assert len(engine2.graph.edges) == 1
    
    def test_complex_causal_chain(self, engine):
        """Test complex causal chain with multiple paths."""
        # Build: A → B → D
        #        A → C → D
        engine.add_causal_relationship("A", "B", strength=0.9)
        engine.add_causal_relationship("A", "C", strength=0.8)
        engine.add_causal_relationship("B", "D", strength=0.7)
        engine.add_causal_relationship("C", "D", strength=0.6)
        
        query = engine.predict_intervention("A", "high", "D")
        
        # Should find a path (either A→B→D or A→C→D)
        assert query.causal_effect > 0
        assert query.confidence > 0
    
    def test_indirect_causal_relationship(self, engine):
        """Test indirect causal relationships."""
        engine.add_causal_relationship(
            cause_name="Exercise",
            effect_name="Health",
            relation_type=CausalRelationType.INDIRECT_CAUSE,
            strength=0.7,
            mechanism="Exercise improves cardiovascular health, muscle strength, etc."
        )
        
        assert len(engine.graph.edges) == 1
        edge = list(engine.graph.edges.values())[0]
        assert edge.relation_type == CausalRelationType.INDIRECT_CAUSE


class TestCausalQuery:
    """Test CausalQuery class."""
    
    def test_query_creation(self):
        """Test creating a causal query."""
        query = CausalQuery(
            query_id="test_query",
            query_type=InterventionType.DO,
            intervention_variable="X",
            intervention_value="a",
            outcome_variable="Y"
        )
        
        assert query.query_id == "test_query"
        assert query.query_type == InterventionType.DO
        assert query.confidence == 0.0  # Default
    
    def test_query_serialization(self):
        """Test query serialization to/from dict."""
        query = CausalQuery(
            query_id="test",
            query_type=InterventionType.COUNTERFACTUAL,
            intervention_variable="Treatment",
            intervention_value="drug",
            outcome_variable="Recovery",
            context={"age": 30},
            predicted_outcome="80%",
            causal_effect=0.8,
            confidence=0.9,
            reasoning="Test reasoning"
        )
        
        data = query.to_dict()
        restored = CausalQuery.from_dict(data)
        
        assert restored.query_id == query.query_id
        assert restored.query_type == query.query_type
        assert restored.causal_effect == query.causal_effect
        assert restored.context == query.context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
