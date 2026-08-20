"""
Phase 12: Causal Inference Engine

Enables understanding of cause-and-effect relationships:
1. Causal graph construction from observations
2. Intervention prediction (what happens if I do X?)
3. Counterfactual reasoning (what would have happened if...?)
4. Root cause analysis (why did this happen?)
5. Causal effect estimation (how much does X affect Y?)

This moves beyond correlation to true causal understanding - essential for AGI.
"""

import sqlite3
import json
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from collections import defaultdict
import re
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class CausalRelationType(Enum):
    """Types of causal relationships."""
    DIRECT_CAUSE = "direct_cause"  # X directly causes Y
    INDIRECT_CAUSE = "indirect_cause"  # X causes Y through intermediaries
    CORRELATION = "correlation"  # X and Y are correlated (not necessarily causal)
    CONFOUNDER = "confounder"  # Z causes both X and Y
    MEDIATOR = "mediator"  # X causes Z which causes Y
    MODERATOR = "moderator"  # Z affects the strength of X→Y


class InterventionType(Enum):
    """Types of interventions."""
    DO = "do"  # do(X=x) - set X to value x
    CONDITION = "condition"  # observe X=x
    COUNTERFACTUAL = "counterfactual"  # what if X had been x?


@dataclass
class CausalNode:
    """A variable in the causal graph."""
    node_id: str
    name: str
    description: str = ""
    variable_type: str = "continuous"  # continuous, binary, categorical
    possible_values: List[Any] = field(default_factory=list)
    observed_values: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'node_id': self.node_id,
            'name': self.name,
            'description': self.description,
            'variable_type': self.variable_type,
            'possible_values': self.possible_values,
            'observed_values': self.observed_values,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CausalNode':
        """Create from dictionary."""
        return cls(
            node_id=data['node_id'],
            name=data['name'],
            description=data.get('description', ''),
            variable_type=data.get('variable_type', 'continuous'),
            possible_values=data.get('possible_values', []),
            observed_values=data.get('observed_values', []),
            metadata=data.get('metadata', {})
        )


@dataclass
class CausalEdge:
    """A causal relationship between two variables."""
    edge_id: str
    source_id: str  # Cause
    target_id: str  # Effect
    relation_type: CausalRelationType
    strength: float = 1.0  # 0-1, how strong the causal effect is
    confidence: float = 0.5  # 0-1, how confident we are in this relationship
    evidence: List[str] = field(default_factory=list)  # Observations supporting this
    mechanism: str = ""  # Description of causal mechanism
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'edge_id': self.edge_id,
            'source_id': self.source_id,
            'target_id': self.target_id,
            'relation_type': self.relation_type.value,
            'strength': self.strength,
            'confidence': self.confidence,
            'evidence': self.evidence,
            'mechanism': self.mechanism,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CausalEdge':
        """Create from dictionary."""
        return cls(
            edge_id=data['edge_id'],
            source_id=data['source_id'],
            target_id=data['target_id'],
            relation_type=CausalRelationType(data['relation_type']),
            strength=data.get('strength', 1.0),
            confidence=data.get('confidence', 0.5),
            evidence=data.get('evidence', []),
            mechanism=data.get('mechanism', ''),
            metadata=data.get('metadata', {})
        )


@dataclass
class CausalQuery:
    """A causal query (intervention, counterfactual, etc.)."""
    query_id: str
    query_type: InterventionType
    intervention_variable: str
    intervention_value: Any
    outcome_variable: str
    context: Dict[str, Any] = field(default_factory=dict)  # Observed values for other variables
    predicted_outcome: Optional[Any] = None
    causal_effect: Optional[float] = None
    confidence: float = 0.0
    reasoning: str = ""
    created_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'query_id': self.query_id,
            'query_type': self.query_type.value,
            'intervention_variable': self.intervention_variable,
            'intervention_value': self.intervention_value,
            'outcome_variable': self.outcome_variable,
            'context': self.context,
            'predicted_outcome': self.predicted_outcome,
            'causal_effect': self.causal_effect,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CausalQuery':
        """Create from dictionary."""
        return cls(
            query_id=data['query_id'],
            query_type=InterventionType(data['query_type']),
            intervention_variable=data['intervention_variable'],
            intervention_value=data['intervention_value'],
            outcome_variable=data['outcome_variable'],
            context=data.get('context', {}),
            predicted_outcome=data.get('predicted_outcome'),
            causal_effect=data.get('causal_effect'),
            confidence=data.get('confidence', 0.0),
            reasoning=data.get('reasoning', ''),
            created_at=data.get('created_at', _now())
        )


class CausalGraph:
    """A causal graph (DAG) representing causal relationships."""
    
    def __init__(self):
        self.nodes: Dict[str, CausalNode] = {}
        self.edges: Dict[str, CausalEdge] = {}
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)  # node_id -> set of child node_ids
        self.reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)  # node_id -> set of parent node_ids
    
    def add_node(self, node: CausalNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.node_id] = node
        if node.node_id not in self.adjacency:
            self.adjacency[node.node_id] = set()
        if node.node_id not in self.reverse_adjacency:
            self.reverse_adjacency[node.node_id] = set()
    
    def add_edge(self, edge: CausalEdge) -> None:
        """Add a causal edge to the graph."""
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            raise ValueError("Both source and target nodes must exist")
        
        self.edges[edge.edge_id] = edge
        self.adjacency[edge.source_id].add(edge.target_id)
        self.reverse_adjacency[edge.target_id].add(edge.source_id)
    
    def get_parents(self, node_id: str) -> List[str]:
        """Get parent nodes (direct causes)."""
        return list(self.reverse_adjacency.get(node_id, set()))
    
    def get_children(self, node_id: str) -> List[str]:
        """Get child nodes (direct effects)."""
        return list(self.adjacency.get(node_id, set()))
    
    def get_ancestors(self, node_id: str) -> Set[str]:
        """Get all ancestor nodes (all causes, direct and indirect)."""
        ancestors = set()
        to_visit = list(self.reverse_adjacency.get(node_id, set()))
        
        while to_visit:
            current = to_visit.pop()
            if current not in ancestors:
                ancestors.add(current)
                to_visit.extend(self.reverse_adjacency.get(current, set()))
        
        return ancestors
    
    def get_descendants(self, node_id: str) -> Set[str]:
        """Get all descendant nodes (all effects, direct and indirect)."""
        descendants = set()
        to_visit = list(self.adjacency.get(node_id, set()))
        
        while to_visit:
            current = to_visit.pop()
            if current not in descendants:
                descendants.add(current)
                to_visit.extend(self.adjacency.get(current, set()))
        
        return descendants
    
    def is_ancestor(self, potential_ancestor: str, node_id: str) -> bool:
        """Check if potential_ancestor is an ancestor of node_id."""
        return potential_ancestor in self.get_ancestors(node_id)
    
    def is_descendant(self, potential_descendant: str, node_id: str) -> bool:
        """Check if potential_descendant is a descendant of node_id."""
        return potential_descendant in self.get_descendants(node_id)
    
    def get_causal_path(self, source_id: str, target_id: str) -> Optional[List[str]]:
        """Find a causal path from source to target (if one exists)."""
        if source_id == target_id:
            return [source_id]
        
        # BFS to find path
        visited = set()
        queue = [(source_id, [source_id])]
        
        while queue:
            current, path = queue.pop(0)
            
            if current in visited:
                continue
            
            visited.add(current)
            
            for child in self.adjacency.get(current, set()):
                if child == target_id:
                    return path + [child]
                
                if child not in visited:
                    queue.append((child, path + [child]))
        
        return None  # No path found
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert graph to dictionary."""
        return {
            'nodes': {node_id: node.to_dict() for node_id, node in self.nodes.items()},
            'edges': {edge_id: edge.to_dict() for edge_id, edge in self.edges.items()}
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CausalGraph':
        """Create graph from dictionary."""
        graph = cls()
        
        for node_id, node_data in data.get('nodes', {}).items():
            graph.add_node(CausalNode.from_dict(node_data))
        
        for edge_id, edge_data in data.get('edges', {}).items():
            graph.add_edge(CausalEdge.from_dict(edge_data))
        
        return graph


class CausalInferenceEngine:
    """
    Engine for causal inference and reasoning.
    
    Provides methods for:
    - Building causal graphs from observations
    - Predicting intervention effects
    - Counterfactual reasoning
    - Root cause analysis
    """
    
    def __init__(self, db_path: str = "data/causal_inference.db"):
        """Initialize the causal inference engine."""
        self.db_path = db_path
        self.graph = CausalGraph()
        self._ensure_db()
        self._load_graph()
        app_logger.info(f"Causal Inference Engine initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS causal_graphs (
                    graph_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    graph_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS causal_queries (
                    query_id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    query_type TEXT NOT NULL,
                    intervention_variable TEXT NOT NULL,
                    intervention_value TEXT NOT NULL,
                    outcome_variable TEXT NOT NULL,
                    context TEXT,
                    predicted_outcome TEXT,
                    causal_effect REAL,
                    confidence REAL,
                    reasoning TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (graph_id) REFERENCES causal_graphs(graph_id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_queries_graph
                ON causal_queries(graph_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_queries_type
                ON causal_queries(query_type)
            """)
            
            conn.commit()
    
    def _load_graph(self) -> None:
        """Load the default causal graph from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT graph_data FROM causal_graphs WHERE name = 'default'"
            )
            row = cursor.fetchone()
            
            if row:
                graph_data = json.loads(row[0])
                self.graph = CausalGraph.from_dict(graph_data)
                app_logger.info(f"Loaded causal graph with {len(self.graph.nodes)} nodes and {len(self.graph.edges)} edges")
    
    def _save_graph(self, name: str = "default", description: str = "") -> str:
        """Save the current causal graph to database."""
        graph_id = f"graph_{int(datetime.now().timestamp())}"
        graph_data = json.dumps(self.graph.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            # Check if graph with this name exists
            cursor = conn.execute(
                "SELECT graph_id FROM causal_graphs WHERE name = ?",
                (name,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update existing graph
                conn.execute("""
                    UPDATE causal_graphs
                    SET graph_data = ?, updated_at = ?, description = ?
                    WHERE name = ?
                """, (graph_data, _now(), description, name))
                graph_id = existing[0]
            else:
                # Insert new graph
                conn.execute("""
                    INSERT INTO causal_graphs (graph_id, name, description, graph_data, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (graph_id, name, description, graph_data, _now(), _now()))
            
            conn.commit()
        
        return graph_id
    
    def add_causal_relationship(
        self,
        cause_name: str,
        effect_name: str,
        relation_type: CausalRelationType = CausalRelationType.DIRECT_CAUSE,
        strength: float = 1.0,
        confidence: float = 0.8,
        evidence: List[str] = None,
        mechanism: str = ""
    ) -> str:
        """
        Add a causal relationship to the graph.
        
        Args:
            cause_name: Name of the cause variable
            effect_name: Name of the effect variable
            relation_type: Type of causal relationship
            strength: Strength of causal effect (0-1)
            confidence: Confidence in this relationship (0-1)
            evidence: List of observations supporting this relationship
            mechanism: Description of causal mechanism
        
        Returns:
            edge_id: ID of the created edge
        """
        # Create nodes if they don't exist
        cause_id = f"node_{re.sub(r'[^a-z0-9]', '_', cause_name.lower())}"
        effect_id = f"node_{re.sub(r'[^a-z0-9]', '_', effect_name.lower())}"
        
        if cause_id not in self.graph.nodes:
            cause_node = CausalNode(
                node_id=cause_id,
                name=cause_name,
                description=f"Causal variable: {cause_name}"
            )
            self.graph.add_node(cause_node)
        
        if effect_id not in self.graph.nodes:
            effect_node = CausalNode(
                node_id=effect_id,
                name=effect_name,
                description=f"Causal variable: {effect_name}"
            )
            self.graph.add_node(effect_node)
        
        # Create edge
        edge_id = f"edge_{cause_id}_to_{effect_id}"
        edge = CausalEdge(
            edge_id=edge_id,
            source_id=cause_id,
            target_id=effect_id,
            relation_type=relation_type,
            strength=strength,
            confidence=confidence,
            evidence=evidence or [],
            mechanism=mechanism
        )
        
        self.graph.add_edge(edge)
        
        app_logger.info(f"Added causal relationship: {cause_name} → {effect_name} (type: {relation_type.value}, strength: {strength:.2f})")
        
        # Save graph
        self._save_graph()
        
        return edge_id
    
    def predict_intervention(
        self,
        intervention_variable: str,
        intervention_value: Any,
        outcome_variable: str,
        context: Dict[str, Any] = None
    ) -> CausalQuery:
        """
        Predict the effect of an intervention: do(X=x) on Y.
        
        Args:
            intervention_variable: Variable to intervene on
            intervention_value: Value to set the variable to
            outcome_variable: Variable to predict
            context: Observed values for other variables
        
        Returns:
            CausalQuery with predicted outcome and causal effect
        """
        context = context or {}
        
        import uuid
        query_id = f"query_{uuid.uuid4().hex[:12]}"
        query = CausalQuery(
            query_id=query_id,
            query_type=InterventionType.DO,
            intervention_variable=intervention_variable,
            outcome_variable=outcome_variable,
            intervention_value=intervention_value,
            context=context
        )
        
        # Find nodes
        intervention_node = None
        outcome_node = None
        
        for node in self.graph.nodes.values():
            if node.name == intervention_variable:
                intervention_node = node
            if node.name == outcome_variable:
                outcome_node = node
        
        if not intervention_node or not outcome_node:
            query.reasoning = "Variables not found in causal graph"
            query.confidence = 0.0
            return query
        
        # Check if there's a causal path
        causal_path = self.graph.get_causal_path(intervention_node.node_id, outcome_node.node_id)
        
        if not causal_path:
            query.reasoning = f"No causal path from {intervention_variable} to {outcome_variable}"
            query.confidence = 0.0
            query.causal_effect = 0.0
            return query
        
        # Calculate causal effect along the path
        total_effect = 1.0
        total_confidence = 1.0
        
        for i in range(len(causal_path) - 1):
            source_id = causal_path[i]
            target_id = causal_path[i + 1]
            
            # Find edge
            edge = None
            for e in self.graph.edges.values():
                if e.source_id == source_id and e.target_id == target_id:
                    edge = e
                    break
            
            if edge:
                total_effect *= edge.strength
                total_confidence *= edge.confidence
        
        query.causal_effect = total_effect
        query.confidence = total_confidence
        query.predicted_outcome = f"Effect of {intervention_variable}={intervention_value} on {outcome_variable}: {total_effect:.2f}"
        query.reasoning = f"Causal path: {' → '.join([self.graph.nodes[n].name for n in causal_path])}. Total effect: {total_effect:.2f} (confidence: {total_confidence:.2f})"
        
        app_logger.info(f"Intervention prediction: do({intervention_variable}={intervention_value}) → {outcome_variable}: effect={total_effect:.2f}, confidence={total_confidence:.2f}")
        
        # Save query
        self._save_query(query)
        
        return query
    
    def counterfactual_reasoning(
        self,
        observed_outcome: Any,
        intervention_variable: str,
        counterfactual_value: Any,
        outcome_variable: str,
        context: Dict[str, Any] = None
    ) -> CausalQuery:
        """
        Counterfactual reasoning: "What would have happened if X had been x'?"
        
        Args:
            observed_outcome: The actual observed outcome
            intervention_variable: Variable to change in counterfactual
            counterfactual_value: What value it would have had
            outcome_variable: Outcome variable
            context: Observed context
        
        Returns:
            CausalQuery with counterfactual prediction
        """
        context = context or {}
        
        import uuid
        query_id = f"cf_query_{uuid.uuid4().hex[:12]}"
        query = CausalQuery(
            query_id=query_id,
            query_type=InterventionType.COUNTERFACTUAL,
            intervention_variable=intervention_variable,
            outcome_variable=outcome_variable,
            intervention_value=counterfactual_value,
            context={**context, 'observed_outcome': observed_outcome}
        )
        
        # Use intervention prediction as base
        intervention_query = self.predict_intervention(
            intervention_variable,
            counterfactual_value,
            outcome_variable,
            context
        )
        
        query.predicted_outcome = intervention_query.predicted_outcome
        query.causal_effect = intervention_query.causal_effect
        query.confidence = intervention_query.confidence * 0.8  # Lower confidence for counterfactuals
        query.reasoning = f"Counterfactual: If {intervention_variable} had been {counterfactual_value}, {outcome_variable} would have been {intervention_query.predicted_outcome}. (Observed: {observed_outcome})"
        
        app_logger.info(f"Counterfactual: If {intervention_variable}={counterfactual_value}, {outcome_variable} would be {intervention_query.predicted_outcome}")
        
        # Save query
        self._save_query(query)
        
        return query
    
    def root_cause_analysis(
        self,
        outcome_variable: str,
        outcome_value: Any,
        max_depth: int = 3
    ) -> List[Tuple[str, float, str]]:
        """
        Identify root causes of an observed outcome.
        
        Args:
            outcome_variable: The outcome variable
            outcome_value: The observed value
            max_depth: Maximum depth to search for root causes
        
        Returns:
            List of (cause_name, causal_effect, reasoning) tuples, sorted by effect strength
        """
        # Find outcome node
        outcome_node = None
        for node in self.graph.nodes.values():
            if node.name == outcome_variable:
                outcome_node = node
                break
        
        if not outcome_node:
            app_logger.warning(f"Outcome variable '{outcome_variable}' not found in causal graph")
            return []
        
        # Get all ancestors (potential causes)
        ancestors = self.graph.get_ancestors(outcome_node.node_id)
        
        root_causes = []
        
        for ancestor_id in ancestors:
            ancestor_node = self.graph.nodes[ancestor_id]
            
            # Calculate causal effect from ancestor to outcome
            causal_path = self.graph.get_causal_path(ancestor_id, outcome_node.node_id)
            
            if not causal_path:
                continue
            
            # Calculate total effect along path
            total_effect = 1.0
            for i in range(len(causal_path) - 1):
                source_id = causal_path[i]
                target_id = causal_path[i + 1]
                
                # Find edge
                for edge in self.graph.edges.values():
                    if edge.source_id == source_id and edge.target_id == target_id:
                        total_effect *= edge.strength
                        break
            
            path_str = ' → '.join([self.graph.nodes[n].name for n in causal_path])
            reasoning = f"Causal path: {path_str}, Total effect: {total_effect:.2f}"
            
            root_causes.append((ancestor_node.name, total_effect, reasoning))
        
        # Sort by effect strength (descending)
        root_causes.sort(key=lambda x: x[1], reverse=True)
        
        # Limit to max_depth
        root_causes = root_causes[:max_depth]
        
        app_logger.info(f"Root cause analysis for {outcome_variable}={outcome_value}: Found {len(root_causes)} potential causes")
        
        return root_causes
    
    def _save_query(self, query: CausalQuery) -> None:
        """Save a causal query to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO causal_queries 
                (query_id, graph_id, query_type, intervention_variable, intervention_value, 
                 outcome_variable, context, predicted_outcome, causal_effect, confidence, reasoning, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                query.query_id,
                'default',
                query.query_type.value,
                query.intervention_variable,
                json.dumps(query.intervention_value),
                query.outcome_variable,
                json.dumps(query.context),
                json.dumps(query.predicted_outcome),
                query.causal_effect,
                query.confidence,
                query.reasoning,
                query.created_at
            ))
            conn.commit()
    
    def get_query_history(self, limit: int = 10) -> List[CausalQuery]:
        """Get recent causal queries."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM causal_queries
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            
            queries = []
            for row in cursor.fetchall():
                query = CausalQuery(
                    query_id=row[0],
                    query_type=InterventionType(row[2]),
                    intervention_variable=row[3],
                    intervention_value=json.loads(row[4]),
                    outcome_variable=row[5],
                    context=json.loads(row[6]) if row[6] else {},
                    predicted_outcome=json.loads(row[7]) if row[7] else None,
                    causal_effect=row[8],
                    confidence=row[9],
                    reasoning=row[10],
                    created_at=row[11]
                )
                queries.append(query)
            
            return queries
    
    def get_causal_graph_summary(self) -> Dict[str, Any]:
        """Get a summary of the current causal graph."""
        return {
            'num_nodes': len(self.graph.nodes),
            'num_edges': len(self.graph.edges),
            'nodes': [node.name for node in self.graph.nodes.values()],
            'edges': [
                f"{self.graph.edges[e].source_id} → {self.graph.edges[e].target_id}"
                for e in self.graph.edges
            ]
        }
