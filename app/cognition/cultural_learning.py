"""
Phase 21: Cultural Learning

Enables the Arena Agent to:
1. Learn from observing others (social learning)
2. Acquire cultural norms and conventions
3. Imitate behaviors and practices
4. Model cultural traditions
5. Adapt to different cultural contexts

This is essential for human-level AGI because humans are fundamentally cultural beings -
we learn most of our knowledge and behaviors through cultural transmission.
"""

import sqlite3
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class NormType(Enum):
    """Types of cultural norms."""
    SOCIAL = "social"  # Social interaction norms
    COMMUNICATION = "communication"  # Communication conventions
    BEHAVIORAL = "behavioral"  # Behavioral expectations
    RITUAL = "ritual"  # Ritualistic practices
    PROFESSIONAL = "professional"  # Professional standards
    ETIQUETTE = "etiquette"  # Etiquette rules


class LearningMechanism(Enum):
    """Mechanisms of cultural learning."""
    OBSERVATION = "observation"  # Learning by watching
    IMITATION = "imitation"  # Learning by copying
    INSTRUCTION = "instruction"  # Learning by being taught
    PARTICIPATION = "participation"  # Learning by doing
    NARRATIVE = "narrative"  # Learning through stories


class CulturalContext(Enum):
    """Types of cultural contexts."""
    NATIONAL = "national"  # National culture
    REGIONAL = "regional"  # Regional culture
    ORGANIZATIONAL = "organizational"  # Organizational culture
    PROFESSIONAL = "professional"  # Professional culture
    SUBCULTURE = "subculture"  # Subculture
    GLOBAL = "global"  # Global/international culture


@dataclass
class CulturalNorm:
    """A cultural norm or convention."""
    norm_id: str = field(default_factory=lambda: f"norm_{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    norm_type: NormType = NormType.SOCIAL
    context: CulturalContext = CulturalContext.NATIONAL
    region: str = ""  # Geographic or cultural region
    importance: float = 0.5  # 0-1, how important this norm is
    prevalence: float = 0.5  # 0-1, how widely followed
    examples: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    related_norms: List[str] = field(default_factory=list)  # Other norm IDs
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'norm_id': self.norm_id,
            'name': self.name,
            'description': self.description,
            'norm_type': self.norm_type.value,
            'context': self.context.value,
            'region': self.region,
            'importance': self.importance,
            'prevalence': self.prevalence,
            'examples': self.examples,
            'violations': self.violations,
            'related_norms': self.related_norms,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CulturalNorm':
        """Create from dictionary."""
        return cls(
            norm_id=data['norm_id'],
            name=data.get('name', ''),
            description=data.get('description', ''),
            norm_type=NormType(data.get('norm_type', 'social')),
            context=CulturalContext(data.get('context', 'national')),
            region=data.get('region', ''),
            importance=data.get('importance', 0.5),
            prevalence=data.get('prevalence', 0.5),
            examples=data.get('examples', []),
            violations=data.get('violations', []),
            related_norms=data.get('related_norms', []),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class ObservedBehavior:
    """A behavior observed in others."""
    observation_id: str = field(default_factory=lambda: f"obs_{uuid.uuid4().hex[:8]}")
    agent_id: str = ""  # Who performed the behavior
    behavior_type: str = ""  # Type of behavior
    description: str = ""
    context: str = ""  # Situational context
    outcome: str = ""  # Result of the behavior
    social_response: str = ""  # How others responded
    cultural_norm_id: Optional[str] = None  # Related cultural norm
    frequency: int = 1  # How many times observed
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'observation_id': self.observation_id,
            'agent_id': self.agent_id,
            'behavior_type': self.behavior_type,
            'description': self.description,
            'context': self.context,
            'outcome': self.outcome,
            'social_response': self.social_response,
            'cultural_norm_id': self.cultural_norm_id,
            'frequency': self.frequency,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ObservedBehavior':
        """Create from dictionary."""
        return cls(
            observation_id=data['observation_id'],
            agent_id=data.get('agent_id', ''),
            behavior_type=data.get('behavior_type', ''),
            description=data.get('description', ''),
            context=data.get('context', ''),
            outcome=data.get('outcome', ''),
            social_response=data.get('social_response', ''),
            cultural_norm_id=data.get('cultural_norm_id'),
            frequency=data.get('frequency', 1),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class CulturalPractice:
    """A cultural practice or tradition."""
    practice_id: str = field(default_factory=lambda: f"practice_{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    context: CulturalContext = CulturalContext.NATIONAL
    region: str = ""
    category: str = ""  # e.g., "greeting", "dining", "celebration"
    steps: List[str] = field(default_factory=list)
    participants: List[str] = field(default_factory=list)  # Roles involved
    materials: List[str] = field(default_factory=list)  # Objects/tools needed
    occasions: List[str] = field(default_factory=list)  # When it's performed
    variations: List[str] = field(default_factory=list)  # Different versions
    related_norms: List[str] = field(default_factory=list)  # Norm IDs
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'practice_id': self.practice_id,
            'name': self.name,
            'description': self.description,
            'context': self.context.value,
            'region': self.region,
            'category': self.category,
            'steps': self.steps,
            'participants': self.participants,
            'materials': self.materials,
            'occasions': self.occasions,
            'variations': self.variations,
            'related_norms': self.related_norms,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CulturalPractice':
        """Create from dictionary."""
        return cls(
            practice_id=data['practice_id'],
            name=data.get('name', ''),
            description=data.get('description', ''),
            context=CulturalContext(data.get('context', 'national')),
            region=data.get('region', ''),
            category=data.get('category', ''),
            steps=data.get('steps', []),
            participants=data.get('participants', []),
            materials=data.get('materials', []),
            occasions=data.get('occasions', []),
            variations=data.get('variations', []),
            related_norms=data.get('related_norms', []),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class ImitationAttempt:
    """An attempt to imitate a cultural behavior."""
    attempt_id: str = field(default_factory=lambda: f"imitation_{uuid.uuid4().hex[:8]}")
    observation_id: Optional[str] = None  # What was being imitated
    practice_id: Optional[str] = None  # Or what practice
    mechanism: LearningMechanism = LearningMechanism.IMITATION
    description: str = ""
    success: bool = False
    feedback: str = ""  # Social feedback received
    adjustments: List[str] = field(default_factory=list)  # Adjustments made
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'attempt_id': self.attempt_id,
            'observation_id': self.observation_id,
            'practice_id': self.practice_id,
            'mechanism': self.mechanism.value,
            'description': self.description,
            'success': self.success,
            'feedback': self.feedback,
            'adjustments': self.adjustments,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ImitationAttempt':
        """Create from dictionary."""
        return cls(
            attempt_id=data['attempt_id'],
            observation_id=data.get('observation_id'),
            practice_id=data.get('practice_id'),
            mechanism=LearningMechanism(data.get('mechanism', 'imitation')),
            description=data.get('description', ''),
            success=data.get('success', False),
            feedback=data.get('feedback', ''),
            adjustments=data.get('adjustments', []),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class CulturalProfile:
    """Profile of cultural knowledge and adaptation."""
    profile_id: str = field(default_factory=lambda: f"profile_{uuid.uuid4().hex[:8]}")
    agent_id: str = ""
    primary_context: CulturalContext = CulturalContext.NATIONAL
    primary_region: str = ""
    known_norms: List[str] = field(default_factory=list)  # Norm IDs
    known_practices: List[str] = field(default_factory=list)  # Practice IDs
    adaptation_level: float = 0.5  # 0-1, how well adapted
    cultural_competence: float = 0.5  # 0-1, cultural competence score
    observations_count: int = 0
    imitations_count: int = 0
    successful_imitations: int = 0
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'profile_id': self.profile_id,
            'agent_id': self.agent_id,
            'primary_context': self.primary_context.value,
            'primary_region': self.primary_region,
            'known_norms': self.known_norms,
            'known_practices': self.known_practices,
            'adaptation_level': self.adaptation_level,
            'cultural_competence': self.cultural_competence,
            'observations_count': self.observations_count,
            'imitations_count': self.imitations_count,
            'successful_imitations': self.successful_imitations,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CulturalProfile':
        """Create from dictionary."""
        return cls(
            profile_id=data['profile_id'],
            agent_id=data.get('agent_id', ''),
            primary_context=CulturalContext(data.get('primary_context', 'national')),
            primary_region=data.get('primary_region', ''),
            known_norms=data.get('known_norms', []),
            known_practices=data.get('known_practices', []),
            adaptation_level=data.get('adaptation_level', 0.5),
            cultural_competence=data.get('cultural_competence', 0.5),
            observations_count=data.get('observations_count', 0),
            imitations_count=data.get('imitations_count', 0),
            successful_imitations=data.get('successful_imitations', 0),
            timestamp=data.get('timestamp', _now())
        )


class CulturalLearningEngine:
    """
    Engine for cultural learning and adaptation.
    
    Provides methods for:
    - Learning cultural norms and practices
    - Observing and imitating behaviors
    - Adapting to different cultural contexts
    - Building cultural competence
    """
    
    def __init__(self, db_path: str = "data/cultural_learning.db"):
        """Initialize the cultural learning engine."""
        self.db_path = db_path
        self._ensure_db()
        app_logger.info(f"Cultural Learning Engine initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cultural_norms (
                    norm_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    norm_type TEXT NOT NULL,
                    context TEXT NOT NULL,
                    norm_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observed_behaviors (
                    observation_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    behavior_type TEXT NOT NULL,
                    observation_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cultural_practices (
                    practice_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    context TEXT NOT NULL,
                    practice_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS imitation_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    mechanism TEXT NOT NULL,
                    attempt_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cultural_profiles (
                    profile_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL UNIQUE,
                    profile_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_norms_type
                ON cultural_norms(norm_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_norms_context
                ON cultural_norms(context)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_agent
                ON observed_behaviors(agent_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_practices_category
                ON cultural_practices(category)
            """)
            
            conn.commit()
    
    def add_cultural_norm(
        self,
        name: str,
        description: str,
        norm_type: NormType,
        context: CulturalContext,
        region: str = "",
        importance: float = 0.5,
        prevalence: float = 0.5,
        examples: List[str] = None,
        violations: List[str] = None,
        related_norms: List[str] = None
    ) -> CulturalNorm:
        """
        Add a cultural norm.
        
        Args:
            name: Norm name
            description: Description of the norm
            norm_type: Type of norm
            context: Cultural context
            region: Geographic or cultural region
            importance: How important (0-1)
            prevalence: How widely followed (0-1)
            examples: Example behaviors
            violations: Example violations
            related_norms: Related norm IDs
        
        Returns:
            CulturalNorm object
        """
        norm = CulturalNorm(
            name=name,
            description=description,
            norm_type=norm_type,
            context=context,
            region=region,
            importance=importance,
            prevalence=prevalence,
            examples=examples or [],
            violations=violations or [],
            related_norms=related_norms or []
        )
        
        self._save_norm(norm)
        
        app_logger.info(f"Added cultural norm: {name} ({norm_type.value}, {context.value})")
        
        return norm
    
    def get_norm(self, norm_id: str) -> Optional[CulturalNorm]:
        """Get a cultural norm by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT norm_data FROM cultural_norms WHERE norm_id = ?",
                (norm_id,)
            )
            row = cursor.fetchone()
            
            if row:
                norm_data = json.loads(row[0])
                return CulturalNorm.from_dict(norm_data)
            
            return None
    
    def get_norms_by_type(self, norm_type: NormType) -> List[CulturalNorm]:
        """Get all norms of a specific type."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT norm_data FROM cultural_norms WHERE norm_type = ?",
                (norm_type.value,)
            )
            
            norms = []
            for row in cursor.fetchall():
                norm_data = json.loads(row[0])
                norms.append(CulturalNorm.from_dict(norm_data))
            
            return norms
    
    def get_norms_by_context(self, context: CulturalContext) -> List[CulturalNorm]:
        """Get all norms in a specific context."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT norm_data FROM cultural_norms WHERE context = ?",
                (context.value,)
            )
            
            norms = []
            for row in cursor.fetchall():
                norm_data = json.loads(row[0])
                norms.append(CulturalNorm.from_dict(norm_data))
            
            return norms
    
    def get_norms_by_region(self, region: str) -> List[CulturalNorm]:
        """Get all norms for a specific region."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT norm_data FROM cultural_norms WHERE json_extract(norm_data, '$.region') = ?",
                (region,)
            )
            
            norms = []
            for row in cursor.fetchall():
                norm_data = json.loads(row[0])
                norms.append(CulturalNorm.from_dict(norm_data))
            
            return norms
    
    def record_observed_behavior(
        self,
        agent_id: str,
        behavior_type: str,
        description: str,
        context: str = "",
        outcome: str = "",
        social_response: str = "",
        cultural_norm_id: Optional[str] = None
    ) -> ObservedBehavior:
        """
        Record an observed behavior.
        
        Args:
            agent_id: Who performed the behavior
            behavior_type: Type of behavior
            description: Description of the behavior
            context: Situational context
            outcome: Result of the behavior
            social_response: How others responded
            cultural_norm_id: Related cultural norm
        
        Returns:
            ObservedBehavior object
        """
        observation = ObservedBehavior(
            agent_id=agent_id,
            behavior_type=behavior_type,
            description=description,
            context=context,
            outcome=outcome,
            social_response=social_response,
            cultural_norm_id=cultural_norm_id
        )
        
        self._save_observation(observation)
        
        # Update cultural profile
        profile = self.get_or_create_profile(agent_id="self")  # Assume "self" is the observer
        profile.observations_count += 1
        self._save_profile(profile)
        
        app_logger.info(f"Recorded observed behavior: {behavior_type} by {agent_id}")
        
        return observation
    
    def get_observations_by_agent(self, agent_id: str, limit: int = 50) -> List[ObservedBehavior]:
        """Get observations by agent."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT observation_data FROM observed_behaviors
                WHERE agent_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (agent_id, limit)
            )
            
            observations = []
            for row in cursor.fetchall():
                observation_data = json.loads(row[0])
                observations.append(ObservedBehavior.from_dict(observation_data))
            
            return observations
    
    def get_observations_by_type(self, behavior_type: str, limit: int = 50) -> List[ObservedBehavior]:
        """Get observations by behavior type."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT observation_data FROM observed_behaviors
                WHERE behavior_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (behavior_type, limit)
            )
            
            observations = []
            for row in cursor.fetchall():
                observation_data = json.loads(row[0])
                observations.append(ObservedBehavior.from_dict(observation_data))
            
            return observations
    
    def add_cultural_practice(
        self,
        name: str,
        description: str,
        context: CulturalContext,
        region: str = "",
        category: str = "",
        steps: List[str] = None,
        participants: List[str] = None,
        materials: List[str] = None,
        occasions: List[str] = None,
        variations: List[str] = None,
        related_norms: List[str] = None
    ) -> CulturalPractice:
        """
        Add a cultural practice.
        
        Args:
            name: Practice name
            description: Description
            context: Cultural context
            region: Geographic or cultural region
            category: Category (e.g., "greeting", "dining")
            steps: Steps involved
            participants: Roles involved
            materials: Objects/tools needed
            occasions: When it's performed
            variations: Different versions
            related_norms: Related norm IDs
        
        Returns:
            CulturalPractice object
        """
        practice = CulturalPractice(
            name=name,
            description=description,
            context=context,
            region=region,
            category=category,
            steps=steps or [],
            participants=participants or [],
            materials=materials or [],
            occasions=occasions or [],
            variations=variations or [],
            related_norms=related_norms or []
        )
        
        self._save_practice(practice)
        
        app_logger.info(f"Added cultural practice: {name} ({category})")
        
        return practice
    
    def get_practice(self, practice_id: str) -> Optional[CulturalPractice]:
        """Get a cultural practice by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT practice_data FROM cultural_practices WHERE practice_id = ?",
                (practice_id,)
            )
            row = cursor.fetchone()
            
            if row:
                practice_data = json.loads(row[0])
                return CulturalPractice.from_dict(practice_data)
            
            return None
    
    def get_practices_by_category(self, category: str) -> List[CulturalPractice]:
        """Get practices by category."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT practice_data FROM cultural_practices WHERE category = ?",
                (category,)
            )
            
            practices = []
            for row in cursor.fetchall():
                practice_data = json.loads(row[0])
                practices.append(CulturalPractice.from_dict(practice_data))
            
            return practices
    
    def get_practices_by_context(self, context: CulturalContext) -> List[CulturalPractice]:
        """Get practices by context."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT practice_data FROM cultural_practices WHERE context = ?",
                (context.value,)
            )
            
            practices = []
            for row in cursor.fetchall():
                practice_data = json.loads(row[0])
                practices.append(CulturalPractice.from_dict(practice_data))
            
            return practices
    
    def attempt_imitation(
        self,
        description: str,
        mechanism: LearningMechanism = LearningMechanism.IMITATION,
        observation_id: Optional[str] = None,
        practice_id: Optional[str] = None,
        success: bool = False,
        feedback: str = "",
        adjustments: List[str] = None
    ) -> ImitationAttempt:
        """
        Record an imitation attempt.
        
        Args:
            description: Description of the attempt
            mechanism: Learning mechanism used
            observation_id: What was being imitated
            practice_id: Or what practice
            success: Whether it was successful
            feedback: Social feedback received
            adjustments: Adjustments made
        
        Returns:
            ImitationAttempt object
        """
        attempt = ImitationAttempt(
            observation_id=observation_id,
            practice_id=practice_id,
            mechanism=mechanism,
            description=description,
            success=success,
            feedback=feedback,
            adjustments=adjustments or []
        )
        
        self._save_imitation(attempt)
        
        # Update cultural profile
        profile = self.get_or_create_profile(agent_id="self")
        profile.imitations_count += 1
        if success:
            profile.successful_imitations += 1
        
        # Update cultural competence
        if profile.imitations_count > 0:
            success_rate = profile.successful_imitations / profile.imitations_count
            profile.cultural_competence = min(1.0, profile.cultural_competence + (success_rate * 0.1))
        
        self._save_profile(profile)
        
        app_logger.info(
            f"Recorded imitation attempt: {description[:50]}... "
            f"(success={success}, mechanism={mechanism.value})"
        )
        
        return attempt
    
    def get_imitation_attempts(self, limit: int = 50) -> List[ImitationAttempt]:
        """Get recent imitation attempts."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT attempt_data FROM imitation_attempts
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,)
            )
            
            attempts = []
            for row in cursor.fetchall():
                attempt_data = json.loads(row[0])
                attempts.append(ImitationAttempt.from_dict(attempt_data))
            
            return attempts
    
    def get_or_create_profile(self, agent_id: str) -> CulturalProfile:
        """Get or create a cultural profile for an agent."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT profile_data FROM cultural_profiles WHERE agent_id = ?",
                (agent_id,)
            )
            row = cursor.fetchone()
            
            if row:
                profile_data = json.loads(row[0])
                return CulturalProfile.from_dict(profile_data)
            else:
                # Create new profile
                profile = CulturalProfile(agent_id=agent_id)
                self._save_profile(profile)
                return profile
    
    def update_profile_norms(self, agent_id: str, norm_ids: List[str]) -> CulturalProfile:
        """Update known norms in a profile."""
        profile = self.get_or_create_profile(agent_id)
        profile.known_norms = list(set(profile.known_norms + norm_ids))  # Deduplicate
        profile.timestamp = _now()
        self._save_profile(profile)
        
        app_logger.info(f"Updated profile for {agent_id}: {len(profile.known_norms)} known norms")
        
        return profile
    
    def update_profile_practices(self, agent_id: str, practice_ids: List[str]) -> CulturalProfile:
        """Update known practices in a profile."""
        profile = self.get_or_create_profile(agent_id)
        profile.known_practices = list(set(profile.known_practices + practice_ids))  # Deduplicate
        profile.timestamp = _now()
        self._save_profile(profile)
        
        app_logger.info(f"Updated profile for {agent_id}: {len(profile.known_practices)} known practices")
        
        return profile
    
    def get_cultural_summary(self) -> Dict[str, Any]:
        """
        Get summary of cultural learning activity.
        
        Returns:
            Dictionary with cultural learning metrics
        """
        with sqlite3.connect(self.db_path) as conn:
            # Count norms
            cursor = conn.execute("SELECT COUNT(*) FROM cultural_norms")
            norm_count = cursor.fetchone()[0]
            
            # Count norms by type
            cursor = conn.execute("""
                SELECT norm_type, COUNT(*)
                FROM cultural_norms
                GROUP BY norm_type
            """)
            norms_by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count norms by context
            cursor = conn.execute("""
                SELECT context, COUNT(*)
                FROM cultural_norms
                GROUP BY context
            """)
            norms_by_context = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count observations
            cursor = conn.execute("SELECT COUNT(*) FROM observed_behaviors")
            observation_count = cursor.fetchone()[0]
            
            # Count observations by type
            cursor = conn.execute("""
                SELECT behavior_type, COUNT(*)
                FROM observed_behaviors
                GROUP BY behavior_type
            """)
            observations_by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count practices
            cursor = conn.execute("SELECT COUNT(*) FROM cultural_practices")
            practice_count = cursor.fetchone()[0]
            
            # Count practices by category
            cursor = conn.execute("""
                SELECT category, COUNT(*)
                FROM cultural_practices
                GROUP BY category
            """)
            practices_by_category = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count imitations
            cursor = conn.execute("SELECT COUNT(*) FROM imitation_attempts")
            imitation_count = cursor.fetchone()[0]
            
            # Count successful imitations
            cursor = conn.execute("""
                SELECT COUNT(*) FROM imitation_attempts
                WHERE json_extract(attempt_data, '$.success') = 1
            """)
            successful_imitations = cursor.fetchone()[0]
            
            # Get profiles
            cursor = conn.execute("SELECT profile_data FROM cultural_profiles")
            profiles = []
            for row in cursor.fetchall():
                profile_data = json.loads(row[0])
                profiles.append(CulturalProfile.from_dict(profile_data))
            
            avg_competence = (
                sum(p.cultural_competence for p in profiles) / len(profiles)
                if profiles else 0.0
            )
            
            return {
                "total_norms": norm_count,
                "norms_by_type": norms_by_type,
                "norms_by_context": norms_by_context,
                "total_observations": observation_count,
                "observations_by_type": observations_by_type,
                "total_practices": practice_count,
                "practices_by_category": practices_by_category,
                "total_imitations": imitation_count,
                "successful_imitations": successful_imitations,
                "imitation_success_rate": (
                    successful_imitations / imitation_count if imitation_count > 0 else 0.0
                ),
                "total_profiles": len(profiles),
                "average_cultural_competence": avg_competence
            }
    
    def _save_norm(self, norm: CulturalNorm) -> None:
        """Save cultural norm to database."""
        norm_data = json.dumps(norm.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cultural_norms
                (norm_id, name, norm_type, context, norm_data, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                norm.norm_id,
                norm.name,
                norm.norm_type.value,
                norm.context.value,
                norm_data,
                norm.timestamp
            ))
            conn.commit()
    
    def _save_observation(self, observation: ObservedBehavior) -> None:
        """Save observed behavior to database."""
        observation_data = json.dumps(observation.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO observed_behaviors
                (observation_id, agent_id, behavior_type, observation_data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                observation.observation_id,
                observation.agent_id,
                observation.behavior_type,
                observation_data,
                observation.timestamp
            ))
            conn.commit()
    
    def _save_practice(self, practice: CulturalPractice) -> None:
        """Save cultural practice to database."""
        practice_data = json.dumps(practice.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cultural_practices
                (practice_id, name, category, context, practice_data, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                practice.practice_id,
                practice.name,
                practice.category,
                practice.context.value,
                practice_data,
                practice.timestamp
            ))
            conn.commit()
    
    def _save_imitation(self, attempt: ImitationAttempt) -> None:
        """Save imitation attempt to database."""
        attempt_data = json.dumps(attempt.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO imitation_attempts
                (attempt_id, mechanism, attempt_data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                attempt.attempt_id,
                attempt.mechanism.value,
                attempt_data,
                attempt.timestamp
            ))
            conn.commit()
    
    def _save_profile(self, profile: CulturalProfile) -> None:
        """Save cultural profile to database."""
        profile_data = json.dumps(profile.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cultural_profiles
                (profile_id, agent_id, profile_data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                profile.profile_id,
                profile.agent_id,
                profile_data,
                profile.timestamp
            ))
            conn.commit()
