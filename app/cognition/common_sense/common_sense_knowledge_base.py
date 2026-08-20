"""
Common Sense Knowledge Base for AGI

A comprehensive knowledge base containing 10,000+ facts about:
- Physical world (gravity, object permanence, physics)
- Human behavior (social norms, psychology, emotions)
- Causal relationships (cause and effect)
- Temporal relationships (before, after, during)
- Spatial relationships (left, right, above, below)
- Common sense reasoning (everyday knowledge)

This is the foundation for AGI - without common sense, AI cannot understand the world.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
import sqlite3
from pathlib import Path


@dataclass
class CommonSenseFact:
    """A single common sense fact."""
    fact_id: str
    category: str  # physical, human, causal, temporal, spatial
    fact: str
    confidence: float = 1.0
    source: str = "common_sense"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "fact_id": self.fact_id,
            "category": self.category,
            "fact": self.fact,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommonSenseFact':
        """Create from dictionary."""
        return cls(
            fact_id=data["fact_id"],
            category=data["category"],
            fact=data["fact"],
            confidence=data.get("confidence", 1.0),
            source=data.get("source", "common_sense"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )


class CommonSenseKnowledgeBase:
    """
    Common Sense Knowledge Base for AGI
    
    Stores and retrieves common sense facts about the world.
    This is the foundation for AGI - without common sense, AI cannot understand the world.
    """
    
    def __init__(self, db_path: str = "data/common_sense.db"):
        """Initialize the common sense knowledge base."""
        self.db_path = db_path
        self._ensure_db()
        self._load_initial_knowledge()
    
    def _ensure_db(self):
        """Ensure the database exists and has the right schema."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS common_sense_facts (
                    fact_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'common_sense',
                    created_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category ON common_sense_facts(category)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fact ON common_sense_facts(fact)
            """)
            
            conn.commit()
    
    def _load_initial_knowledge(self):
        """Load initial common sense knowledge."""
        # Check if we already have knowledge
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM common_sense_facts")
            count = cursor.fetchone()[0]
            
            if count == 0:
                # Load initial knowledge
                self._load_physical_world_knowledge()
                self._load_human_behavior_knowledge()
                self._load_causal_knowledge()
                self._load_temporal_knowledge()
                self._load_spatial_knowledge()
                self._load_technology_knowledge()
                self._load_everyday_knowledge()
    
    def _load_physical_world_knowledge(self):
        """Load physical world knowledge."""
        from .physical_world import PHYSICAL_WORLD_FACTS
        
        for fact_data in PHYSICAL_WORLD_FACTS:
            self.add_fact(CommonSenseFact.from_dict(fact_data))
    
    def _load_human_behavior_knowledge(self):
        """Load human behavior knowledge."""
        from .human_behavior import HUMAN_BEHAVIOR_FACTS
        
        for fact_data in HUMAN_BEHAVIOR_FACTS:
            self.add_fact(CommonSenseFact.from_dict(fact_data))
    
    def _load_causal_knowledge(self):
        """Load causal knowledge."""
        from .causal_knowledge import CAUSAL_KNOWLEDGE_FACTS
        
        for fact_data in CAUSAL_KNOWLEDGE_FACTS:
            self.add_fact(CommonSenseFact.from_dict(fact_data))
    
    def _load_temporal_knowledge(self):
        """Load temporal knowledge."""
        from .temporal_knowledge import TEMPORAL_KNOWLEDGE_FACTS
        
        for fact_data in TEMPORAL_KNOWLEDGE_FACTS:
            self.add_fact(CommonSenseFact.from_dict(fact_data))
    
    def _load_spatial_knowledge(self):
        """Load spatial knowledge."""
        from .spatial_knowledge import SPATIAL_KNOWLEDGE_FACTS
        
        for fact_data in SPATIAL_KNOWLEDGE_FACTS:
            self.add_fact(CommonSenseFact.from_dict(fact_data))
    
    def add_fact(self, fact: CommonSenseFact) -> bool:
        """Add a fact to the knowledge base."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO common_sense_facts 
                    (fact_id, category, fact, confidence, source, created_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    fact.fact_id,
                    fact.category,
                    fact.fact,
                    fact.confidence,
                    fact.source,
                    fact.created_at,
                    json.dumps(fact.metadata)
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"Error adding fact: {e}")
            return False
    
    def get_fact(self, fact_id: str) -> Optional[CommonSenseFact]:
        """Get a fact by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT fact_id, category, fact, confidence, source, created_at, metadata
                FROM common_sense_facts
                WHERE fact_id = ?
            """, (fact_id,))
            
            row = cursor.fetchone()
            if row:
                return CommonSenseFact(
                    fact_id=row[0],
                    category=row[1],
                    fact=row[2],
                    confidence=row[3],
                    source=row[4],
                    created_at=row[5],
                    metadata=json.loads(row[6])
                )
            return None
    
    def query_facts(
        self,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 100
    ) -> List[CommonSenseFact]:
        """Query facts by category or search query."""
        with sqlite3.connect(self.db_path) as conn:
            if category and query:
                cursor = conn.execute("""
                    SELECT fact_id, category, fact, confidence, source, created_at, metadata
                    FROM common_sense_facts
                    WHERE category = ? AND fact LIKE ?
                    ORDER BY confidence DESC
                    LIMIT ?
                """, (category, f"%{query}%", limit))
            elif category:
                cursor = conn.execute("""
                    SELECT fact_id, category, fact, confidence, source, created_at, metadata
                    FROM common_sense_facts
                    WHERE category = ?
                    ORDER BY confidence DESC
                    LIMIT ?
                """, (category, limit))
            elif query:
                cursor = conn.execute("""
                    SELECT fact_id, category, fact, confidence, source, created_at, metadata
                    FROM common_sense_facts
                    WHERE fact LIKE ?
                    ORDER BY confidence DESC
                    LIMIT ?
                """, (f"%{query}%", limit))
            else:
                cursor = conn.execute("""
                    SELECT fact_id, category, fact, confidence, source, created_at, metadata
                    FROM common_sense_facts
                    ORDER BY confidence DESC
                    LIMIT ?
                """, (limit,))
            
            facts = []
            for row in cursor.fetchall():
                facts.append(CommonSenseFact(
                    fact_id=row[0],
                    category=row[1],
                    fact=row[2],
                    confidence=row[3],
                    source=row[4],
                    created_at=row[5],
                    metadata=json.loads(row[6])
                ))
            
            return facts
    
    def count_facts(self, category: Optional[str] = None) -> int:
        """Count facts, optionally by category."""
        with sqlite3.connect(self.db_path) as conn:
            if category:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM common_sense_facts WHERE category = ?
                """, (category,))
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM common_sense_facts")
            
            return cursor.fetchone()[0]
    
    def _load_technology_knowledge(self):
        """Load technology and computing knowledge."""
        from .technology_knowledge import TECHNOLOGY_KNOWLEDGE_FACTS
        for fact_data in TECHNOLOGY_KNOWLEDGE_FACTS:
            self.add_fact(CommonSenseFact.from_dict(fact_data))

    def _load_everyday_knowledge(self):
        """Load everyday life and practical knowledge."""
        from .everyday_knowledge import EVERYDAY_KNOWLEDGE_FACTS
        for fact_data in EVERYDAY_KNOWLEDGE_FACTS:
            self.add_fact(CommonSenseFact.from_dict(fact_data))

    def reason_about(self, query: str, category: Optional[str] = None) -> List[CommonSenseFact]:
        """Reason about a query using common sense knowledge.
        
        Extracts keywords from the query and searches for facts containing those keywords.
        Returns the most relevant facts sorted by relevance score.
        """
        import re
        
        # Extract meaningful keywords from the query (remove common stop words)
        stop_words = {
            "what", "when", "where", "why", "how", "who", "which", "that", "this",
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "do", "does", "did", "will", "would", "could", "should", "may", "might",
            "can", "shall", "have", "has", "had", "having", "if", "then", "than",
            "you", "your", "it", "its", "i", "me", "my", "we", "our", "they", "them",
            "he", "she", "him", "her", "and", "or", "but", "not", "no", "nor", "so",
            "of", "in", "on", "at", "to", "for", "with", "about", "from", "by", "up",
            "out", "off", "over", "under", "again", "further", "once", "here", "there",
            "all", "each", "every", "both", "few", "more", "most", "other", "some",
            "such", "only", "own", "same", "just", "also", "very", "something",
            "anything", "happens", "happen", "make", "makes", "people", "get", "gets",
        }
        
        # Split and clean words (remove punctuation, lowercase)
        raw_words = re.findall(r'\b\w+\b', query.lower())
        query_words = [w for w in raw_words if w not in stop_words and len(w) > 2]
        
        if not query_words:
            # Fallback: use all words longer than 2 chars
            query_words = [w for w in raw_words if len(w) > 2]
        
        if not query_words:
            return []
        
        # Search for each keyword and collect all matching facts
        all_facts: Dict[str, CommonSenseFact] = {}
        
        for keyword in query_words:
            matches = self.query_facts(category=category, query=keyword, limit=20)
            for fact in matches:
                all_facts[fact.fact_id] = fact
        
        facts = list(all_facts.values())
        
        if not facts:
            return []
        
        # Sort by relevance (keyword overlap * confidence)
        query_word_set = set(query_words)
        
        def relevance_score(fact: CommonSenseFact) -> float:
            fact_words = set(fact.fact.lower().split())
            overlap = len(query_word_set & fact_words)
            return overlap * fact.confidence
        
        facts.sort(key=relevance_score, reverse=True)
        
        return facts[:5]  # Return top 5 most relevant facts
