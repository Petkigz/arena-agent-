"""
Phase 16: Creative Generation Engine

Enables the agent to:
1. Generate novel solutions to problems
2. Think divergently and explore solution spaces
3. Combine existing ideas in new ways (combinatorial creativity)
4. Evaluate creative outputs for novelty and usefulness
5. Learn from creative successes and failures

This is a hallmark of human-level intelligence - the ability to create truly original ideas.
"""

import sqlite3
import json
import random
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class CreativeTechnique(Enum):
    """Techniques for generating creative ideas."""
    COMBINATION = "combination"  # Combine existing ideas in new ways
    ANALOGY = "analogy"  # Apply solution from one domain to another
    REVERSAL = "reversal"  # Reverse assumptions or processes
    EXAGGERATION = "exaggeration"  # Exaggerate or minimize aspects
    SUBSTITUTION = "substitution"  # Replace components with alternatives
    ADAPTATION = "adaptation"  # Adapt solution from similar problem
    ELIMINATION = "elimination"  # Remove unnecessary components
    REARRANGEMENT = "rearrangement"  # Reorder or reorganize components


class IdeaQuality(Enum):
    """Quality assessment of creative ideas."""
    BREAKTHROUGH = "breakthrough"  # Highly novel and useful
    INNOVATIVE = "innovative"  # Novel and useful
    IMPROVEMENT = "improvement"  # Incremental improvement
    CONVENTIONAL = "conventional"  # Standard solution
    IMPRACTICAL = "impractical"  # Novel but not useful
    DERIVATIVE = "derivative"  # Not novel


@dataclass
class CreativeIdea:
    """A creative idea or solution."""
    idea_id: str = field(default_factory=lambda: f"idea_{uuid.uuid4().hex[:8]}")
    problem: str = ""
    description: str = ""
    technique: CreativeTechnique = CreativeTechnique.COMBINATION
    source_ideas: List[str] = field(default_factory=list)  # Ideas that inspired this
    novelty_score: float = 0.0  # 0.0 to 1.0
    usefulness_score: float = 0.0  # 0.0 to 1.0
    creativity_score: float = 0.0  # Combined novelty and usefulness
    quality: IdeaQuality = IdeaQuality.CONVENTIONAL
    implementation_steps: List[str] = field(default_factory=list)
    potential_challenges: List[str] = field(default_factory=list)
    evaluation_feedback: List[str] = field(default_factory=list)
    success: Optional[bool] = None  # None = not tested, True/False = tested
    created_at: str = field(default_factory=_now)
    tested_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'idea_id': self.idea_id,
            'problem': self.problem,
            'description': self.description,
            'technique': self.technique.value,
            'source_ideas': self.source_ideas,
            'novelty_score': self.novelty_score,
            'usefulness_score': self.usefulness_score,
            'creativity_score': self.creativity_score,
            'quality': self.quality.value,
            'implementation_steps': self.implementation_steps,
            'potential_challenges': self.potential_challenges,
            'evaluation_feedback': self.evaluation_feedback,
            'success': self.success,
            'created_at': self.created_at,
            'tested_at': self.tested_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CreativeIdea':
        """Create from dictionary."""
        return cls(
            idea_id=data['idea_id'],
            problem=data.get('problem', ''),
            description=data['description'],
            technique=CreativeTechnique(data['technique']),
            source_ideas=data.get('source_ideas', []),
            novelty_score=data.get('novelty_score', 0.0),
            usefulness_score=data.get('usefulness_score', 0.0),
            creativity_score=data.get('creativity_score', 0.0),
            quality=IdeaQuality(data.get('quality', 'conventional')),
            implementation_steps=data.get('implementation_steps', []),
            potential_challenges=data.get('potential_challenges', []),
            evaluation_feedback=data.get('evaluation_feedback', []),
            success=data.get('success'),
            created_at=data.get('created_at', _now()),
            tested_at=data.get('tested_at')
        )


@dataclass
class CreativeSession:
    """A creative problem-solving session."""
    session_id: str = field(default_factory=lambda: f"session_{uuid.uuid4().hex[:8]}")
    problem: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    ideas_generated: List[str] = field(default_factory=list)  # Idea IDs
    techniques_used: List[CreativeTechnique] = field(default_factory=list)
    best_idea_id: Optional[str] = None
    session_duration_seconds: float = 0.0
    created_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'session_id': self.session_id,
            'problem': self.problem,
            'context': self.context,
            'constraints': self.constraints,
            'goals': self.goals,
            'ideas_generated': self.ideas_generated,
            'techniques_used': [t.value for t in self.techniques_used],
            'best_idea_id': self.best_idea_id,
            'session_duration_seconds': self.session_duration_seconds,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CreativeSession':
        """Create from dictionary."""
        return cls(
            session_id=data['session_id'],
            problem=data.get('problem', ''),
            context=data.get('context', {}),
            constraints=data.get('constraints', []),
            goals=data.get('goals', []),
            ideas_generated=data.get('ideas_generated', []),
            techniques_used=[CreativeTechnique(t) for t in data.get('techniques_used', [])],
            best_idea_id=data.get('best_idea_id'),
            session_duration_seconds=data.get('session_duration_seconds', 0.0),
            created_at=data.get('created_at', _now())
        )


class CreativeGenerationEngine:
    """
    Engine for creative idea generation and evaluation.
    
    Provides methods for:
    - Generating novel solutions using various techniques
    - Evaluating ideas for novelty and usefulness
    - Combining existing ideas in new ways
    - Learning from creative successes and failures
    """
    
    def __init__(self, db_path: str = "data/creative_generation.db"):
        """Initialize the creative generation engine."""
        self.db_path = db_path
        self._ensure_db()
        app_logger.info(f"Creative Generation Engine initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS creative_ideas (
                    idea_id TEXT PRIMARY KEY,
                    problem TEXT NOT NULL,
                    idea_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    tested_at TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS creative_sessions (
                    session_id TEXT PRIMARY KEY,
                    problem TEXT NOT NULL,
                    session_data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ideas_problem
                ON creative_ideas(problem)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ideas_quality
                ON creative_ideas(json_extract(idea_data, '$.quality'))
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ideas_creativity
                ON creative_ideas(json_extract(idea_data, '$.creativity_score'))
            """)
            
            conn.commit()
    
    def generate_ideas(
        self,
        problem: str,
        context: Dict[str, Any] = None,
        constraints: List[str] = None,
        num_ideas: int = 5,
        techniques: List[CreativeTechnique] = None
    ) -> List[CreativeIdea]:
        """
        Generate creative ideas for a problem.
        
        Args:
            problem: Problem statement
            context: Additional context
            constraints: Constraints to consider
            num_ideas: Number of ideas to generate
            techniques: Specific techniques to use (None = all)
        
        Returns:
            List of generated CreativeIdea objects
        """
        context = context or {}
        constraints = constraints or []
        techniques = techniques or list(CreativeTechnique)
        
        ideas = []
        
        for i in range(num_ideas):
            # Select a technique (cycle through or random)
            technique = techniques[i % len(techniques)] if len(techniques) > 0 else CreativeTechnique.COMBINATION
            
            # Generate idea using the technique
            idea = self._generate_idea_with_technique(
                problem=problem,
                technique=technique,
                context=context,
                constraints=constraints
            )
            
            if idea:
                # Evaluate the idea
                self._evaluate_idea(idea)
                
                # Save the idea
                self._save_idea(idea)
                ideas.append(idea)
        
        app_logger.info(f"Generated {len(ideas)} creative ideas for problem: {problem[:50]}...")
        
        return ideas
    
    def _generate_idea_with_technique(
        self,
        problem: str,
        technique: CreativeTechnique,
        context: Dict[str, Any],
        constraints: List[str]
    ) -> Optional[CreativeIdea]:
        """Generate a single idea using a specific technique."""
        idea = CreativeIdea(
            problem=problem,
            technique=technique
        )
        
        # Generate description based on technique
        if technique == CreativeTechnique.COMBINATION:
            idea.description = self._generate_combination_idea(problem, context)
        elif technique == CreativeTechnique.ANALOGY:
            idea.description = self._generate_analogy_idea(problem, context)
        elif technique == CreativeTechnique.REVERSAL:
            idea.description = self._generate_reversal_idea(problem, context)
        elif technique == CreativeTechnique.EXAGGERATION:
            idea.description = self._generate_exaggeration_idea(problem, context)
        elif technique == CreativeTechnique.SUBSTITUTION:
            idea.description = self._generate_substitution_idea(problem, context)
        elif technique == CreativeTechnique.ADAPTATION:
            idea.description = self._generate_adaptation_idea(problem, context)
        elif technique == CreativeTechnique.ELIMINATION:
            idea.description = self._generate_elimination_idea(problem, context)
        elif technique == CreativeTechnique.REARRANGEMENT:
            idea.description = self._generate_rearrangement_idea(problem, context)
        
        # Generate implementation steps
        idea.implementation_steps = self._generate_implementation_steps(idea.description)
        
        # Identify potential challenges
        idea.potential_challenges = self._identify_challenges(idea.description, constraints)
        
        return idea
    
    def _generate_combination_idea(self, problem: str, context: Dict[str, Any]) -> str:
        """Generate idea by combining existing concepts."""
        # In production, this would use a knowledge graph or LLM
        # For now, generate a template-based combination
        return f"Combine approach A with approach B to solve: {problem}. This creates a hybrid solution that leverages strengths of both."
    
    def _generate_analogy_idea(self, problem: str, context: Dict[str, Any]) -> str:
        """Generate idea using analogy from another domain."""
        return f"Apply solution from analogous domain to: {problem}. Adapt the core principle to fit this context."
    
    def _generate_reversal_idea(self, problem: str, context: Dict[str, Any]) -> str:
        """Generate idea by reversing assumptions."""
        return f"Reverse the typical approach to: {problem}. Instead of doing X, do the opposite to achieve unexpected results."
    
    def _generate_exaggeration_idea(self, problem: str, context: Dict[str, Any]) -> str:
        """Generate idea by exaggerating aspects."""
        return f"Exaggerate a key aspect of: {problem}. Take one element to the extreme to discover new possibilities."
    
    def _generate_substitution_idea(self, problem: str, context: Dict[str, Any]) -> str:
        """Generate idea by substituting components."""
        return f"Substitute a key component in: {problem}. Replace traditional element with alternative to improve solution."
    
    def _generate_adaptation_idea(self, problem: str, context: Dict[str, Any]) -> str:
        """Generate idea by adapting existing solution."""
        return f"Adapt existing solution from similar problem to: {problem}. Modify to fit specific requirements."
    
    def _generate_elimination_idea(self, problem: str, context: Dict[str, Any]) -> str:
        """Generate idea by eliminating components."""
        return f"Eliminate unnecessary components from: {problem}. Simplify by removing non-essential elements."
    
    def _generate_rearrangement_idea(self, problem: str, context: Dict[str, Any]) -> str:
        """Generate idea by rearranging components."""
        return f"Rearrange components in: {problem}. Reorder or reorganize to discover new relationships."
    
    def _generate_implementation_steps(self, description: str) -> List[str]:
        """Generate implementation steps for an idea."""
        # In production, this would use LLM or planning system
        return [
            "Define requirements and constraints",
            "Design solution architecture",
            "Implement core functionality",
            "Test and validate",
            "Iterate and refine"
        ]
    
    def _identify_challenges(self, description: str, constraints: List[str]) -> List[str]:
        """Identify potential challenges for an idea."""
        challenges = [
            "Technical complexity",
            "Resource requirements",
            "Integration with existing systems"
        ]
        
        if constraints:
            challenges.append(f"Meeting constraints: {', '.join(constraints[:2])}")
        
        return challenges
    
    def _evaluate_idea(self, idea: CreativeIdea) -> None:
        """Evaluate an idea for novelty and usefulness."""
        # In production, this would use ML models or LLM evaluation
        # For now, use heuristics
        
        # Novelty score (0-1)
        # Higher for less common techniques
        novelty_scores = {
            CreativeTechnique.COMBINATION: 0.6,
            CreativeTechnique.ANALOGY: 0.7,
            CreativeTechnique.REVERSAL: 0.8,
            CreativeTechnique.EXAGGERATION: 0.7,
            CreativeTechnique.SUBSTITUTION: 0.5,
            CreativeTechnique.ADAPTATION: 0.4,
            CreativeTechnique.ELIMINATION: 0.6,
            CreativeTechnique.REARRANGEMENT: 0.5
        }
        idea.novelty_score = novelty_scores.get(idea.technique, 0.5)
        
        # Usefulness score (0-1)
        # Based on implementation feasibility and challenge count
        base_usefulness = 0.7
        challenge_penalty = len(idea.potential_challenges) * 0.05
        idea.usefulness_score = max(0.0, min(1.0, base_usefulness - challenge_penalty))
        
        # Creativity score (weighted average)
        idea.creativity_score = (idea.novelty_score * 0.6 + idea.usefulness_score * 0.4)
        
        # Determine quality
        if idea.creativity_score >= 0.8:
            idea.quality = IdeaQuality.BREAKTHROUGH
        elif idea.creativity_score >= 0.65:
            idea.quality = IdeaQuality.INNOVATIVE
        elif idea.creativity_score >= 0.5:
            idea.quality = IdeaQuality.IMPROVEMENT
        elif idea.creativity_score >= 0.35:
            idea.quality = IdeaQuality.CONVENTIONAL
        elif idea.novelty_score > idea.usefulness_score:
            idea.quality = IdeaQuality.IMRACTICAL
        else:
            idea.quality = IdeaQuality.DERIVATIVE
    
    def evaluate_idea_with_feedback(
        self,
        idea_id: str,
        novelty_score: float,
        usefulness_score: float,
        feedback: List[str]
    ) -> Optional[CreativeIdea]:
        """
        Update idea evaluation with human feedback.
        
        Args:
            idea_id: Idea ID
            novelty_score: Human-evaluated novelty (0-1)
            usefulness_score: Human-evaluated usefulness (0-1)
            feedback: List of feedback comments
        
        Returns:
            Updated CreativeIdea or None if not found
        """
        idea = self.get_idea(idea_id)
        if not idea:
            app_logger.error(f"Idea {idea_id} not found")
            return None
        
        # Update scores
        idea.novelty_score = novelty_score
        idea.usefulness_score = usefulness_score
        idea.creativity_score = (novelty_score * 0.6 + usefulness_score * 0.4)
        
        # Update quality
        if idea.creativity_score >= 0.8:
            idea.quality = IdeaQuality.BREAKTHROUGH
        elif idea.creativity_score >= 0.65:
            idea.quality = IdeaQuality.INNOVATIVE
        elif idea.creativity_score >= 0.5:
            idea.quality = IdeaQuality.IMPROVEMENT
        elif idea.creativity_score >= 0.35:
            idea.quality = IdeaQuality.CONVENTIONAL
        elif idea.novelty_score > idea.usefulness_score:
            idea.quality = IdeaQuality.IMRACTICAL
        else:
            idea.quality = IdeaQuality.DERIVATIVE
        
        # Add feedback
        idea.evaluation_feedback.extend(feedback)
        
        # Save updated idea
        self._save_idea(idea)
        
        app_logger.info(f"Updated idea {idea_id} with human feedback (creativity: {idea.creativity_score:.2f})")
        
        return idea
    
    def test_idea(self, idea_id: str, success: bool, lessons_learned: List[str] = None) -> Optional[CreativeIdea]:
        """
        Record the result of testing an idea.
        
        Args:
            idea_id: Idea ID
            success: Whether the idea was successful
            lessons_learned: Lessons learned from testing
        
        Returns:
            Updated CreativeIdea or None if not found
        """
        idea = self.get_idea(idea_id)
        if not idea:
            app_logger.error(f"Idea {idea_id} not found")
            return None
        
        idea.success = success
        idea.tested_at = _now()
        
        if lessons_learned:
            idea.evaluation_feedback.extend([f"Lesson: {lesson}" for lesson in lessons_learned])
        
        # Save updated idea
        self._save_idea(idea)
        
        app_logger.info(f"Tested idea {idea_id}: {'Success' if success else 'Failed'}")
        
        return idea
    
    def get_best_ideas(
        self,
        problem: Optional[str] = None,
        min_creativity_score: float = 0.5,
        limit: int = 10
    ) -> List[CreativeIdea]:
        """
        Get the best ideas, optionally filtered by problem.
        
        Args:
            problem: Filter by problem (None = all problems)
            min_creativity_score: Minimum creativity score
            limit: Maximum number of ideas to return
        
        Returns:
            List of CreativeIdea objects sorted by creativity score
        """
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT idea_data FROM creative_ideas
                WHERE json_extract(idea_data, '$.creativity_score') >= ?
            """
            params = [min_creativity_score]
            
            if problem:
                query += " AND problem = ?"
                params.append(problem)
            
            query += " ORDER BY json_extract(idea_data, '$.creativity_score') DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            ideas = []
            for row in cursor.fetchall():
                idea_data = json.loads(row[0])
                ideas.append(CreativeIdea.from_dict(idea_data))
            
            return ideas
    
    def get_idea(self, idea_id: str) -> Optional[CreativeIdea]:
        """Get idea by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT idea_data FROM creative_ideas WHERE idea_id = ?",
                (idea_id,)
            )
            row = cursor.fetchone()
            
            if row:
                idea_data = json.loads(row[0])
                return CreativeIdea.from_dict(idea_data)
            
            return None
    
    def list_ideas(
        self,
        problem: Optional[str] = None,
        technique: Optional[CreativeTechnique] = None,
        quality: Optional[IdeaQuality] = None,
        limit: int = 100
    ) -> List[CreativeIdea]:
        """List ideas with optional filters."""
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT idea_data FROM creative_ideas WHERE 1=1"
            params = []
            
            if problem:
                query += " AND problem = ?"
                params.append(problem)
            
            if technique:
                query += " AND json_extract(idea_data, '$.technique') = ?"
                params.append(technique.value)
            
            if quality:
                query += " AND json_extract(idea_data, '$.quality') = ?"
                params.append(quality.value)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            ideas = []
            for row in cursor.fetchall():
                idea_data = json.loads(row[0])
                ideas.append(CreativeIdea.from_dict(idea_data))
            
            return ideas
    
    def _save_idea(self, idea: CreativeIdea) -> None:
        """Save idea to database."""
        idea_data = json.dumps(idea.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO creative_ideas
                (idea_id, problem, idea_data, created_at, tested_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                idea.idea_id,
                idea.problem,
                idea_data,
                idea.created_at,
                idea.tested_at
            ))
            conn.commit()
    
    def get_creativity_summary(self) -> Dict[str, Any]:
        """Get summary of creative generation activity."""
        ideas = self.list_ideas(limit=10000)
        
        if not ideas:
            return {
                'total_ideas': 0,
                'average_creativity': 0.0,
                'breakthrough_ideas': 0,
                'innovative_ideas': 0,
                'tested_ideas': 0,
                'successful_ideas': 0,
                'success_rate': 0.0
            }
        
        breakthrough_count = sum(1 for i in ideas if i.quality == IdeaQuality.BREAKTHROUGH)
        innovative_count = sum(1 for i in ideas if i.quality == IdeaQuality.INNOVATIVE)
        tested_count = sum(1 for i in ideas if i.success is not None)
        successful_count = sum(1 for i in ideas if i.success is True)
        
        return {
            'total_ideas': len(ideas),
            'average_creativity': sum(i.creativity_score for i in ideas) / len(ideas),
            'breakthrough_ideas': breakthrough_count,
            'innovative_ideas': innovative_count,
            'tested_ideas': tested_count,
            'successful_ideas': successful_count,
            'success_rate': successful_count / tested_count if tested_count > 0 else 0.0
        }
