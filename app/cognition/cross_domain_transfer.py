"""
Phase 15: Cross-Domain Transfer Learning

Enables the agent to:
1. Identify analogies between different domains
2. Transfer knowledge from familiar to unfamiliar domains
3. Apply learned skills to new contexts
4. Build abstract representations that generalize across domains
5. Leverage past experience to solve novel problems

This is a critical capability for AGI - the ability to learn once and apply everywhere.
"""

import sqlite3
import json
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class DomainType(Enum):
    """Types of knowledge domains."""
    TECHNICAL = "technical"  # Programming, engineering, math
    CREATIVE = "creative"  # Art, music, writing
    SOCIAL = "social"  # Communication, leadership, psychology
    PHYSICAL = "physical"  # Sports, crafts, manual skills
    ANALYTICAL = "analytical"  # Data analysis, research, logic
    BUSINESS = "business"  # Management, finance, marketing
    SCIENTIFIC = "scientific"  # Physics, chemistry, biology
    PERSONAL = "personal"  # Self-improvement, health, relationships


class TransferType(Enum):
    """Types of knowledge transfer."""
    DIRECT = "direct"  # Direct application (e.g., Python → JavaScript)
    ANALOGICAL = "analogical"  # Analogical reasoning (e.g., chess → business strategy)
    ABSTRACT = "abstract"  # Abstract principles (e.g., recursion → fractals)
    STRUCTURAL = "structural"  # Structural patterns (e.g., tree data structure → org charts)
    PROCEDURAL = "procedural"  # Procedures (e.g., debugging code → debugging processes)


class TransferStrength(Enum):
    """Strength of transfer relationship."""
    STRONG = "strong"  # High similarity, direct application
    MODERATE = "moderate"  # Moderate similarity, some adaptation needed
    WEAK = "weak"  # Low similarity, significant adaptation needed
    SPECULATIVE = "speculative"  # Theoretical connection, untested


@dataclass
class DomainKnowledge:
    """Knowledge in a specific domain."""
    domain_id: str = field(default_factory=lambda: f"domain_{uuid.uuid4().hex[:8]}")
    name: str = ""
    domain_type: DomainType = DomainType.TECHNICAL
    description: str = ""
    concepts: List[str] = field(default_factory=list)  # Key concepts in this domain
    skills: List[str] = field(default_factory=list)  # Skills in this domain
    principles: List[str] = field(default_factory=list)  # Fundamental principles
    patterns: List[str] = field(default_factory=list)  # Common patterns
    examples: List[Dict[str, Any]] = field(default_factory=list)  # Example applications
    embedding: Optional[List[float]] = None  # Vector embedding for similarity
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'domain_id': self.domain_id,
            'name': self.name,
            'domain_type': self.domain_type.value,
            'description': self.description,
            'concepts': self.concepts,
            'skills': self.skills,
            'principles': self.principles,
            'patterns': self.patterns,
            'examples': self.examples,
            'embedding': self.embedding,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DomainKnowledge':
        """Create from dictionary."""
        return cls(
            domain_id=data['domain_id'],
            name=data['name'],
            domain_type=DomainType(data['domain_type']),
            description=data.get('description', ''),
            concepts=data.get('concepts', []),
            skills=data.get('skills', []),
            principles=data.get('principles', []),
            patterns=data.get('patterns', []),
            examples=data.get('examples', []),
            embedding=data.get('embedding'),
            created_at=data.get('created_at', _now()),
            updated_at=data.get('updated_at', _now())
        )


@dataclass
class TransferRelationship:
    """A relationship between two domains for knowledge transfer."""
    relationship_id: str = field(default_factory=lambda: f"transfer_{uuid.uuid4().hex[:8]}")
    source_domain_id: str = ""
    target_domain_id: str = ""
    transfer_type: TransferType = TransferType.ANALOGICAL
    strength: TransferStrength = TransferStrength.MODERATE
    similarity_score: float = 0.0  # 0.0 to 1.0
    shared_concepts: List[str] = field(default_factory=list)
    shared_patterns: List[str] = field(default_factory=list)
    transfer_examples: List[Dict[str, Any]] = field(default_factory=list)
    success_rate: float = 0.0  # How often transfers succeed
    created_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'relationship_id': self.relationship_id,
            'source_domain_id': self.source_domain_id,
            'target_domain_id': self.target_domain_id,
            'transfer_type': self.transfer_type.value,
            'strength': self.strength.value,
            'similarity_score': self.similarity_score,
            'shared_concepts': self.shared_concepts,
            'shared_patterns': self.shared_patterns,
            'transfer_examples': self.transfer_examples,
            'success_rate': self.success_rate,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransferRelationship':
        """Create from dictionary."""
        return cls(
            relationship_id=data['relationship_id'],
            source_domain_id=data['source_domain_id'],
            target_domain_id=data['target_domain_id'],
            transfer_type=TransferType(data['transfer_type']),
            strength=TransferStrength(data['strength']),
            similarity_score=data.get('similarity_score', 0.0),
            shared_concepts=data.get('shared_concepts', []),
            shared_patterns=data.get('shared_patterns', []),
            transfer_examples=data.get('transfer_examples', []),
            success_rate=data.get('success_rate', 0.0),
            created_at=data.get('created_at', _now())
        )


@dataclass
class TransferResult:
    """Result of a knowledge transfer attempt."""
    result_id: str = field(default_factory=lambda: f"result_{uuid.uuid4().hex[:8]}")
    relationship_id: str = ""
    source_problem: str = ""
    target_problem: str = ""
    transferred_knowledge: List[str] = field(default_factory=list)
    adaptations: List[str] = field(default_factory=list)  # How knowledge was adapted
    success: bool = False  # verified application outcome only
    predicted_success: bool = False
    verified: bool = False
    evaluation_mode: str = "predicted_similarity"
    effectiveness_score: float = 0.0  # predicted until verified=True
    verification_evidence: List[str] = field(default_factory=list)
    lessons_learned: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'result_id': self.result_id,
            'relationship_id': self.relationship_id,
            'source_problem': self.source_problem,
            'target_problem': self.target_problem,
            'transferred_knowledge': self.transferred_knowledge,
            'adaptations': self.adaptations,
            'success': self.success,
            'predicted_success': self.predicted_success,
            'verified': self.verified,
            'evaluation_mode': self.evaluation_mode,
            'effectiveness_score': self.effectiveness_score,
            'verification_evidence': self.verification_evidence,
            'lessons_learned': self.lessons_learned,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransferResult':
        """Create from dictionary."""
        return cls(
            result_id=data['result_id'],
            relationship_id=data['relationship_id'],
            source_problem=data.get('source_problem', ''),
            target_problem=data.get('target_problem', ''),
            transferred_knowledge=data.get('transferred_knowledge', []),
            adaptations=data.get('adaptations', []),
            success=data.get('success', False),
            predicted_success=data.get('predicted_success', False),
            verified=data.get('verified', False),
            evaluation_mode=data.get('evaluation_mode', 'predicted_similarity'),
            effectiveness_score=data.get('effectiveness_score', 0.0),
            verification_evidence=data.get('verification_evidence', []),
            lessons_learned=data.get('lessons_learned', []),
            created_at=data.get('created_at', _now())
        )


class CrossDomainTransferEngine:
    """
    Engine for cross-domain knowledge transfer.
    
    Enables the agent to:
    - Build domain knowledge representations
    - Identify analogies between domains
    - Transfer knowledge from familiar to unfamiliar domains
    - Learn from transfer successes and failures
    """
    
    def __init__(self, db_path: str = "data/cross_domain_transfer.db"):
        """Initialize the cross-domain transfer engine."""
        self.db_path = db_path
        self.vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
        self._ensure_db()
        app_logger.info(f"Cross-Domain Transfer Engine initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS domain_knowledge (
                    domain_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    domain_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transfer_relationships (
                    relationship_id TEXT PRIMARY KEY,
                    source_domain_id TEXT NOT NULL,
                    target_domain_id TEXT NOT NULL,
                    relationship_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (source_domain_id) REFERENCES domain_knowledge(domain_id),
                    FOREIGN KEY (target_domain_id) REFERENCES domain_knowledge(domain_id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transfer_results (
                    result_id TEXT PRIMARY KEY,
                    relationship_id TEXT NOT NULL,
                    result_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (relationship_id) REFERENCES transfer_relationships(relationship_id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_source
                ON transfer_relationships(source_domain_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_target
                ON transfer_relationships(target_domain_id)
            """)
            
            conn.commit()
    
    def add_domain_knowledge(
        self,
        name: str,
        domain_type: DomainType,
        description: str,
        concepts: List[str],
        skills: List[str],
        principles: List[str],
        patterns: List[str],
        examples: List[Dict[str, Any]] = None
    ) -> DomainKnowledge:
        """
        Add knowledge for a domain.
        
        Args:
            name: Domain name
            domain_type: Type of domain
            description: Domain description
            concepts: Key concepts
            skills: Skills in this domain
            principles: Fundamental principles
            patterns: Common patterns
            examples: Example applications
        
        Returns:
            Created DomainKnowledge
        """
        domain = DomainKnowledge(
            name=name,
            domain_type=domain_type,
            description=description,
            concepts=concepts,
            skills=skills,
            principles=principles,
            patterns=patterns,
            examples=examples or []
        )
        
        # Generate embedding
        domain.embedding = self._generate_embedding(domain)
        
        # Save to database
        self._save_domain(domain)
        
        app_logger.info(f"Added domain knowledge: {name} (type: {domain_type.value})")
        
        return domain
    
    def _generate_embedding(self, domain: DomainKnowledge) -> List[float]:
        """Generate vector embedding for a domain."""
        # Combine all text
        text = " ".join([
            domain.name,
            domain.description,
            " ".join(domain.concepts),
            " ".join(domain.skills),
            " ".join(domain.principles),
            " ".join(domain.patterns)
        ])
        
        # Store the text for later embedding computation
        # We'll compute embeddings on-demand when comparing domains
        return []  # Return empty for now, will compute on-demand
    
    def discover_transfer_relationships(
        self,
        source_domain_id: str,
        min_similarity: float = 0.3
    ) -> List[TransferRelationship]:
        """
        Discover potential transfer relationships from a source domain to all other domains.
        
        Args:
            source_domain_id: Source domain ID
            min_similarity: Minimum similarity score to consider
        
        Returns:
            List of discovered TransferRelationships
        """
        source_domain = self.get_domain(source_domain_id)
        if not source_domain:
            app_logger.error(f"Source domain {source_domain_id} not found")
            return []
        
        all_domains = self.list_domains()
        relationships = []
        
        for target_domain in all_domains:
            if target_domain.domain_id == source_domain_id:
                continue  # Skip self
            
            # Calculate similarity
            similarity = self._calculate_similarity(source_domain, target_domain)
            
            if similarity >= min_similarity:
                # Identify shared concepts and patterns
                shared_concepts = list(set(source_domain.concepts) & set(target_domain.concepts))
                shared_patterns = list(set(source_domain.patterns) & set(target_domain.patterns))
                
                # Determine transfer type and strength
                transfer_type = self._infer_transfer_type(
                    source_domain, target_domain, shared_concepts, shared_patterns
                )
                strength = self._infer_strength(similarity)
                
                # Create relationship
                relationship = TransferRelationship(
                    source_domain_id=source_domain_id,
                    target_domain_id=target_domain.domain_id,
                    transfer_type=transfer_type,
                    strength=strength,
                    similarity_score=similarity,
                    shared_concepts=shared_concepts,
                    shared_patterns=shared_patterns
                )
                
                # Save relationship
                self._save_relationship(relationship)
                relationships.append(relationship)
        
        app_logger.info(
            f"Discovered {len(relationships)} transfer relationships from {source_domain.name}"
        )
        
        return relationships
    
    def _calculate_similarity(
        self,
        domain1: DomainKnowledge,
        domain2: DomainKnowledge
    ) -> float:
        """Calculate similarity between two domains."""
        # Generate text representations
        text1 = " ".join([
            domain1.name,
            domain1.description,
            " ".join(domain1.concepts),
            " ".join(domain1.skills),
            " ".join(domain1.principles),
            " ".join(domain1.patterns)
        ])
        
        text2 = " ".join([
            domain2.name,
            domain2.description,
            " ".join(domain2.concepts),
            " ".join(domain2.skills),
            " ".join(domain2.principles),
            " ".join(domain2.patterns)
        ])
        
        try:
            # Fit vectorizer on both texts together to ensure same vocabulary
            self.vectorizer.fit([text1, text2])
            
            # Transform both texts
            vec1 = self.vectorizer.transform([text1]).toarray()[0]
            vec2 = self.vectorizer.transform([text2]).toarray()[0]
            
            # Use cosine similarity
            similarity = cosine_similarity([vec1], [vec2])[0][0]
            return float(similarity)
        except Exception as e:
            app_logger.error(f"Error calculating similarity: {e}")
            return 0.0
    
    def _infer_transfer_type(
        self,
        source: DomainKnowledge,
        target: DomainKnowledge,
        shared_concepts: List[str],
        shared_patterns: List[str]
    ) -> TransferType:
        """Infer the type of transfer relationship."""
        # If same domain type, likely direct transfer
        if source.domain_type == target.domain_type:
            return TransferType.DIRECT
        
        # If many shared patterns, likely structural transfer
        if len(shared_patterns) > 3:
            return TransferType.STRUCTURAL
        
        # If many shared concepts, likely analogical transfer
        if len(shared_concepts) > 5:
            return TransferType.ANALOGICAL
        
        # Otherwise, abstract transfer
        return TransferType.ABSTRACT
    
    def _infer_strength(self, similarity: float) -> TransferStrength:
        """Infer transfer strength from similarity score."""
        if similarity >= 0.8:
            return TransferStrength.STRONG
        elif similarity >= 0.6:
            return TransferStrength.MODERATE
        elif similarity >= 0.4:
            return TransferStrength.WEAK
        else:
            return TransferStrength.SPECULATIVE
    
    def transfer_knowledge(
        self,
        relationship_id: str,
        source_problem: str,
        target_problem: str
    ) -> TransferResult:
        """
        Attempt to transfer knowledge from source to target domain.
        
        Args:
            relationship_id: Transfer relationship ID
            source_problem: Problem in source domain
            target_problem: Problem in target domain
        
        Returns:
            TransferResult with outcome
        """
        relationship = self.get_relationship(relationship_id)
        if not relationship:
            app_logger.error(f"Relationship {relationship_id} not found")
            return None
        
        source_domain = self.get_domain(relationship.source_domain_id)
        target_domain = self.get_domain(relationship.target_domain_id)
        
        # Generate transfer
        transferred_knowledge = self._generate_transfer(
            source_domain, target_domain, relationship, source_problem, target_problem
        )
        
        # Generate adaptations
        adaptations = self._generate_adaptations(
            source_domain, target_domain, transferred_knowledge
        )
        
        # Similarity predicts whether transfer may help; it is not evidence that
        # the target task actually succeeded.
        predicted_success = relationship.similarity_score > 0.5
        effectiveness = relationship.similarity_score * (
            1.0 if predicted_success else 0.5
        )

        # These are proposed adaptations, not learned success lessons.
        lessons = self._generate_lessons(
            source_domain, target_domain, predicted_success, effectiveness
        )
        
        # Create result
        result = TransferResult(
            relationship_id=relationship_id,
            source_problem=source_problem,
            target_problem=target_problem,
            transferred_knowledge=transferred_knowledge,
            adaptations=adaptations,
            success=False,
            predicted_success=predicted_success,
            verified=False,
            evaluation_mode="predicted_similarity",
            effectiveness_score=effectiveness,
            lessons_learned=lessons
        )
        
        # Save result
        self._save_result(result)
        
        # Do not update historical success rate from a similarity prediction.
        app_logger.info(
            f"Transfer proposal: {source_domain.name} → {target_domain.name} "
            f"(predicted_success: {predicted_success}, predicted_effectiveness: {effectiveness:.2f})"
        )
        
        return result

    def record_verified_transfer_result(
        self,
        result_id: str,
        *,
        success: bool,
        effectiveness_score: float,
        evidence: List[str],
    ) -> Optional[TransferResult]:
        """Record an externally verified application outcome for a transfer."""
        result = next((item for item in self.list_results() if item.result_id == result_id), None)
        if result is None or not evidence:
            return None
        result.success = bool(success)
        result.verified = True
        result.evaluation_mode = "verified_application"
        result.effectiveness_score = max(0.0, min(1.0, float(effectiveness_score)))
        result.verification_evidence = [str(item) for item in evidence]
        self._save_result(result)
        self._update_relationship_success_rate(result.relationship_id, result.success)
        return result
    
    def _generate_transfer(
        self,
        source: DomainKnowledge,
        target: DomainKnowledge,
        relationship: TransferRelationship,
        source_problem: str,
        target_problem: str
    ) -> List[str]:
        """Generate knowledge to transfer."""
        transferred = []
        
        # Transfer relevant principles
        for principle in source.principles:
            if any(word in principle.lower() for word in target_problem.lower().split()):
                transferred.append(f"Principle: {principle}")
        
        # Transfer relevant patterns
        for pattern in source.patterns:
            if pattern in relationship.shared_patterns:
                transferred.append(f"Pattern: {pattern}")
        
        # Transfer relevant skills
        for skill in source.skills:
            if any(word in skill.lower() for word in target_problem.lower().split()):
                transferred.append(f"Skill: {skill}")
        
        # If nothing specific, transfer general principles
        if not transferred:
            transferred = [f"Principle: {p}" for p in source.principles[:3]]
        
        return transferred
    
    def _generate_adaptations(
        self,
        source: DomainKnowledge,
        target: DomainKnowledge,
        transferred: List[str]
    ) -> List[str]:
        """Generate adaptations needed for target domain."""
        adaptations = []
        
        # Add domain-specific adaptations
        if source.domain_type != target.domain_type:
            adaptations.append(
                f"Adapt terminology from {source.domain_type.value} to {target.domain_type.value}"
            )
        
        # Add context adaptations
        adaptations.append("Adapt to target domain context and constraints")
        
        # Add validation adaptations
        adaptations.append("Validate assumptions in target domain")
        
        return adaptations
    
    def _generate_lessons(
        self,
        source: DomainKnowledge,
        target: DomainKnowledge,
        success: bool,
        effectiveness: float
    ) -> List[str]:
        """Generate lessons learned from transfer attempt."""
        lessons = []
        
        if success:
            lessons.append(
                f"Transfer from {source.name} to {target.name} was successful "
                f"(effectiveness: {effectiveness:.2f})"
            )
            if effectiveness > 0.8:
                lessons.append("High similarity domains enable direct knowledge transfer")
            else:
                lessons.append("Moderate adaptation was needed despite successful transfer")
        else:
            lessons.append(
                f"Transfer from {source.name} to {target.name} was unsuccessful"
            )
            lessons.append("Domains may be too dissimilar for effective transfer")
            lessons.append("Consider breaking down knowledge into more abstract principles")
        
        return lessons
    
    def _update_relationship_success_rate(
        self,
        relationship_id: str,
        success: bool
    ) -> None:
        """Update relationship success rate based on new result."""
        relationship = self.get_relationship(relationship_id)
        if not relationship:
            return
        
        # Get all results for this relationship
        results = [
            result for result in self.list_results(relationship_id=relationship_id)
            if result.verified
        ]

        if results:
            success_count = sum(1 for r in results if r.success)
            relationship.success_rate = success_count / len(results)
            self._save_relationship(relationship)
    
    def get_domain(self, domain_id: str) -> Optional[DomainKnowledge]:
        """Get domain knowledge by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT domain_data FROM domain_knowledge WHERE domain_id = ?",
                (domain_id,)
            )
            row = cursor.fetchone()
            
            if row:
                domain_data = json.loads(row[0])
                return DomainKnowledge.from_dict(domain_data)
            
            return None
    
    def list_domains(self, domain_type: Optional[DomainType] = None) -> List[DomainKnowledge]:
        """List all domains, optionally filtered by type."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT domain_data FROM domain_knowledge"
            params = []
            
            if domain_type:
                query += " WHERE json_extract(domain_data, '$.domain_type') = ?"
                params.append(domain_type.value)
            
            cursor = conn.execute(query, params)
            
            domains = []
            for row in cursor.fetchall():
                domain_data = json.loads(row[0])
                domains.append(DomainKnowledge.from_dict(domain_data))
            
            return domains
    
    def get_relationship(self, relationship_id: str) -> Optional[TransferRelationship]:
        """Get transfer relationship by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT relationship_data FROM transfer_relationships WHERE relationship_id = ?",
                (relationship_id,)
            )
            row = cursor.fetchone()
            
            if row:
                relationship_data = json.loads(row[0])
                return TransferRelationship.from_dict(relationship_data)
            
            return None
    
    def list_relationships(
        self,
        source_domain_id: Optional[str] = None,
        target_domain_id: Optional[str] = None
    ) -> List[TransferRelationship]:
        """List transfer relationships with optional filters."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT relationship_data FROM transfer_relationships WHERE 1=1"
            params = []
            
            if source_domain_id:
                query += " AND source_domain_id = ?"
                params.append(source_domain_id)
            
            if target_domain_id:
                query += " AND target_domain_id = ?"
                params.append(target_domain_id)
            
            cursor = conn.execute(query, params)
            
            relationships = []
            for row in cursor.fetchall():
                relationship_data = json.loads(row[0])
                relationships.append(TransferRelationship.from_dict(relationship_data))
            
            return relationships
    
    def list_results(
        self,
        relationship_id: Optional[str] = None,
        success: Optional[bool] = None
    ) -> List[TransferResult]:
        """List transfer results with optional filters."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT result_data FROM transfer_results WHERE 1=1"
            params = []
            
            if relationship_id:
                query += " AND json_extract(result_data, '$.relationship_id') = ?"
                params.append(relationship_id)
            
            if success is not None:
                query += " AND json_extract(result_data, '$.success') = ?"
                params.append(1 if success else 0)
            
            cursor = conn.execute(query, params)
            
            results = []
            for row in cursor.fetchall():
                result_data = json.loads(row[0])
                results.append(TransferResult.from_dict(result_data))
            
            return results
    
    def _save_domain(self, domain: DomainKnowledge) -> None:
        """Save domain knowledge to database."""
        domain_data = json.dumps(domain.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO domain_knowledge
                (domain_id, name, domain_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                domain.domain_id,
                domain.name,
                domain_data,
                domain.created_at,
                domain.updated_at
            ))
            conn.commit()
    
    def _save_relationship(self, relationship: TransferRelationship) -> None:
        """Save transfer relationship to database."""
        relationship_data = json.dumps(relationship.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO transfer_relationships
                (relationship_id, source_domain_id, target_domain_id, relationship_data, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                relationship.relationship_id,
                relationship.source_domain_id,
                relationship.target_domain_id,
                relationship_data,
                relationship.created_at
            ))
            conn.commit()
    
    def _save_result(self, result: TransferResult) -> None:
        """Save transfer result to database."""
        result_data = json.dumps(result.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO transfer_results
                (result_id, relationship_id, result_data, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                result.result_id,
                result.relationship_id,
                result_data,
                result.created_at
            ))
            conn.commit()
    
    def get_transfer_summary(self) -> Dict[str, Any]:
        """Get summary of transfer learning activity."""
        domains = self.list_domains()
        relationships = self.list_relationships()
        results = self.list_results()
        
        successful_results = [r for r in results if r.success]
        
        return {
            'total_domains': len(domains),
            'total_relationships': len(relationships),
            'total_transfers': len(results),
            'successful_transfers': len(successful_results),
            'success_rate': len(successful_results) / len(results) if results else 0.0,
            'average_effectiveness': (
                sum(r.effectiveness_score for r in results) / len(results)
                if results else 0.0
            ),
            'domains_by_type': {
                dt.value: len([d for d in domains if d.domain_type == dt])
                for dt in DomainType
            }
        }
