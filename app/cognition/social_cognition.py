"""
Phase 17: Social Cognition Module

Enables the Arena Agent to:
1. Model mental states of others (theory of mind)
2. Recognize and respond to emotions (emotional intelligence)
3. Engage in collaborative reasoning
4. Understand and follow social norms
5. Build and maintain social relationships

This is critical for human-level AGI - the ability to understand and interact with other intelligent agents.
"""

import sqlite3
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import uuid
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class Emotion(Enum):
    """Basic emotions based on Ekman's model."""
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    NEUTRAL = "neutral"


class MentalState(Enum):
    """Types of mental states."""
    BELIEF = "belief"  # What someone believes to be true
    DESIRE = "desire"  # What someone wants
    INTENTION = "intention"  # What someone plans to do
    KNOWLEDGE = "knowledge"  # What someone knows
    EMOTION = "emotion"  # What someone feels


class SocialNorm(Enum):
    """Common social norms."""
    RECIPROCITY = "reciprocity"  # Return favors
    HONESTY = "honesty"  # Tell the truth
    RESPECT = "respect"  # Show respect to others
    COOPERATION = "cooperation"  # Work together
    FAIRNESS = "fairness"  # Treat others fairly
    EMPATHY = "empathy"  # Understand others' feelings
    POLITENESS = "politeness"  # Use polite language
    TURN_TAKING = "turn_taking"  # Wait for your turn


class RelationshipType(Enum):
    """Types of social relationships."""
    FRIEND = "friend"
    COLLEAGUE = "colleague"
    MENTOR = "mentor"
    STUDENT = "student"
    FAMILY = "family"
    ACQUAINTANCE = "acquaintance"
    STRANGER = "stranger"


@dataclass
class MentalStateModel:
    """Evidence-linked model of a possible mental state.

    ``agent_id`` is the subject being modelled. ``perspective_agent_id`` and
    ``belief_chain`` make bounded nesting explicit: ``[arena, owner]`` means
    Arena models the owner's state, while ``[arena, owner, teammate]`` is one
    additional level. This is a model with uncertainty, not mind-reading.
    """
    state_id: str = field(default_factory=lambda: f"state_{uuid.uuid4().hex[:8]}")
    agent_id: str = ""  # Who this mental state belongs to
    state_type: MentalState = MentalState.BELIEF
    content: str = ""  # What the mental state is about
    confidence: float = 0.5  # 0-1, evidence-derived only
    evidence: List[str] = field(default_factory=list)  # Why we model this
    perspective_agent_id: str = "arena"
    belief_chain: List[str] = field(default_factory=list)
    nesting_depth: int = 0
    expires_at: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'state_id': self.state_id,
            'agent_id': self.agent_id,
            'state_type': self.state_type.value,
            'content': self.content,
            'confidence': self.confidence,
            'evidence': self.evidence,
            'perspective_agent_id': self.perspective_agent_id,
            'belief_chain': self.belief_chain,
            'nesting_depth': self.nesting_depth,
            'expires_at': self.expires_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MentalStateModel':
        """Create from dictionary, including older records without nesting."""
        chain = [str(item) for item in data.get('belief_chain', []) if str(item).strip()]
        return cls(
            state_id=data['state_id'],
            agent_id=data['agent_id'],
            state_type=MentalState(data['state_type']),
            content=data['content'],
            confidence=data.get('confidence', 0.5),
            evidence=data.get('evidence', []),
            perspective_agent_id=str(data.get('perspective_agent_id', 'arena')),
            belief_chain=chain,
            nesting_depth=int(data.get('nesting_depth', max(0, len(chain) - 1))),
            expires_at=data.get('expires_at'),
            created_at=data.get('created_at', _now()),
            updated_at=data.get('updated_at', _now())
        )


@dataclass
class EmotionalState:
    """Emotional state of an agent."""
    emotion_id: str = field(default_factory=lambda: f"emotion_{uuid.uuid4().hex[:8]}")
    agent_id: str = ""
    primary_emotion: Emotion = Emotion.NEUTRAL
    intensity: float = 0.0  # 0-1
    secondary_emotions: List[Emotion] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)  # What caused this emotion
    observed_at: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'emotion_id': self.emotion_id,
            'agent_id': self.agent_id,
            'primary_emotion': self.primary_emotion.value,
            'intensity': self.intensity,
            'secondary_emotions': [e.value for e in self.secondary_emotions],
            'triggers': self.triggers,
            'observed_at': self.observed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmotionalState':
        """Create from dictionary."""
        return cls(
            emotion_id=data['emotion_id'],
            agent_id=data['agent_id'],
            primary_emotion=Emotion(data['primary_emotion']),
            intensity=data.get('intensity', 0.0),
            secondary_emotions=[Emotion(e) for e in data.get('secondary_emotions', [])],
            triggers=data.get('triggers', []),
            observed_at=data.get('observed_at', _now())
        )


@dataclass
class SocialRelationship:
    """Relationship between two agents."""
    relationship_id: str = field(default_factory=lambda: f"rel_{uuid.uuid4().hex[:8]}")
    agent1_id: str = ""
    agent2_id: str = ""
    relationship_type: RelationshipType = RelationshipType.ACQUAINTANCE
    trust_level: float = 0.5  # 0-1
    interaction_count: int = 0
    positive_interactions: int = 0
    negative_interactions: int = 0
    shared_interests: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    last_interaction: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'relationship_id': self.relationship_id,
            'agent1_id': self.agent1_id,
            'agent2_id': self.agent2_id,
            'relationship_type': self.relationship_type.value,
            'trust_level': self.trust_level,
            'interaction_count': self.interaction_count,
            'positive_interactions': self.positive_interactions,
            'negative_interactions': self.negative_interactions,
            'shared_interests': self.shared_interests,
            'created_at': self.created_at,
            'last_interaction': self.last_interaction
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SocialRelationship':
        """Create from dictionary."""
        return cls(
            relationship_id=data['relationship_id'],
            agent1_id=data['agent1_id'],
            agent2_id=data['agent2_id'],
            relationship_type=RelationshipType(data['relationship_type']),
            trust_level=data.get('trust_level', 0.5),
            interaction_count=data.get('interaction_count', 0),
            positive_interactions=data.get('positive_interactions', 0),
            negative_interactions=data.get('negative_interactions', 0),
            shared_interests=data.get('shared_interests', []),
            created_at=data.get('created_at', _now()),
            last_interaction=data.get('last_interaction', _now())
        )


@dataclass
class SocialInteraction:
    """A social interaction between agents."""
    interaction_id: str = field(default_factory=lambda: f"interaction_{uuid.uuid4().hex[:8]}")
    participants: List[str] = field(default_factory=list)  # Agent IDs
    interaction_type: str = ""  # e.g., "conversation", "collaboration", "conflict"
    context: str = ""
    norms_followed: List[SocialNorm] = field(default_factory=list)
    norms_violated: List[SocialNorm] = field(default_factory=list)
    emotional_outcomes: Dict[str, EmotionalState] = field(default_factory=dict)
    outcome: str = ""  # "positive", "negative", "neutral"
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'interaction_id': self.interaction_id,
            'participants': self.participants,
            'interaction_type': self.interaction_type,
            'context': self.context,
            'norms_followed': [n.value for n in self.norms_followed],
            'norms_violated': [n.value for n in self.norms_violated],
            'emotional_outcomes': {k: v.to_dict() for k, v in self.emotional_outcomes.items()},
            'outcome': self.outcome,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SocialInteraction':
        """Create from dictionary."""
        return cls(
            interaction_id=data['interaction_id'],
            participants=data.get('participants', []),
            interaction_type=data.get('interaction_type', ''),
            context=data.get('context', ''),
            norms_followed=[SocialNorm(n) for n in data.get('norms_followed', [])],
            norms_violated=[SocialNorm(n) for n in data.get('norms_violated', [])],
            emotional_outcomes={k: EmotionalState.from_dict(v) for k, v in data.get('emotional_outcomes', {}).items()},
            outcome=data.get('outcome', ''),
            timestamp=data.get('timestamp', _now())
        )


class SocialCognitionEngine:
    """
    Engine for social cognition and interaction.

    Mental-state nesting is deliberately capped at two levels beyond the
    observing perspective. Expired inferences are excluded from current reads
    but remain in SQLite history for auditability.
    
    Provides methods for:
    - Modeling mental states of others (theory of mind)
    - Recognizing and responding to emotions
    - Understanding social norms
    - Building and maintaining relationships
    - Collaborative problem solving
    """

    MAX_NESTING_DEPTH = 2
    DEFAULT_INFERENCE_TTL_HOURS = 24
    
    def __init__(self, db_path: str = "data/social_cognition.db"):
        """Initialize the social cognition engine."""
        self.db_path = db_path
        self._ensure_db()
        app_logger.info(f"Social Cognition Engine initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mental_states (
                    state_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    state_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emotional_states (
                    emotion_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    emotion_data TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS social_relationships (
                    relationship_id TEXT PRIMARY KEY,
                    agent1_id TEXT NOT NULL,
                    agent2_id TEXT NOT NULL,
                    relationship_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_interaction TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS social_interactions (
                    interaction_id TEXT PRIMARY KEY,
                    interaction_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mental_states_agent
                ON mental_states(agent_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_emotional_states_agent
                ON emotional_states(agent_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_agents
                ON social_relationships(agent1_id, agent2_id)
            """)
            
            conn.commit()
    
    # Theory of Mind Methods

    @staticmethod
    def _validate_confidence(confidence: float) -> float:
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("mental-state confidence must be between 0 and 1")
        return confidence

    @classmethod
    def _validate_belief_chain(
        cls,
        perspective_agent_id: str,
        agent_id: str,
        belief_chain: Optional[List[str]],
    ) -> tuple[List[str], int]:
        chain = [str(item).strip() for item in (belief_chain or []) if str(item).strip()]
        if not chain:
            return [], 0
        if chain[0] != str(perspective_agent_id).strip():
            raise ValueError("belief_chain must start with perspective_agent_id")
        if chain[-1] != str(agent_id).strip():
            raise ValueError("belief_chain must end with agent_id")
        depth = len(chain) - 1
        if depth < 0 or depth > cls.MAX_NESTING_DEPTH:
            raise ValueError(
                f"mental-state nesting depth must be <= {cls.MAX_NESTING_DEPTH}"
            )
        if len(set(chain)) != len(chain):
            raise ValueError("belief_chain cannot contain repeated agents")
        return chain, depth

    @staticmethod
    def _default_expiry(expires_at: Optional[str]) -> Optional[str]:
        if expires_at is not None:
            # Validate caller-provided timestamps before persisting them.
            datetime.fromisoformat(str(expires_at))
            return str(expires_at)
        return (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

    @staticmethod
    def _is_expired(state: MentalStateModel, now: Optional[datetime] = None) -> bool:
        if not state.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(str(state.expires_at))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            current = now or datetime.now(timezone.utc)
            if current.tzinfo is None:
                current = current.replace(tzinfo=timezone.utc)
            return current >= expiry
        except (TypeError, ValueError, OverflowError):
            return True
    
    def infer_mental_state(
        self,
        agent_id: str,
        state_type: MentalState,
        content: str,
        evidence: List[str],
        confidence: float = 0.5,
        *,
        perspective_agent_id: str = "arena",
        belief_chain: Optional[List[str]] = None,
        expires_at: Optional[str] = None,
    ) -> MentalStateModel:
        """
        Infer a mental state for an agent.
        
        Args:
            agent_id: ID of the agent
            state_type: Type of mental state (belief, desire, intention, etc.)
            content: What the mental state is about
            evidence: Evidence for this inference
            confidence: How confident we are (0-1)
            perspective_agent_id: Agent holding the model (normally Arena)
            belief_chain: Bounded observer-to-subject chain for nested states
            expires_at: Optional expiry; inferred states default to 24 hours
        
        Returns:
            MentalStateModel object
        """
        confidence = self._validate_confidence(confidence)
        perspective_agent_id = str(perspective_agent_id or "arena").strip() or "arena"
        agent_id = str(agent_id or "").strip()
        if not agent_id:
            raise ValueError("agent_id is required")
        chain, nesting_depth = self._validate_belief_chain(
            perspective_agent_id, agent_id, belief_chain
        )
        state = MentalStateModel(
            agent_id=agent_id,
            state_type=state_type,
            content=str(content or "")[:2000],
            confidence=confidence,
            evidence=[str(item)[:500] for item in (evidence or [])],
            perspective_agent_id=perspective_agent_id,
            belief_chain=chain,
            nesting_depth=nesting_depth,
            expires_at=self._default_expiry(expires_at),
        )
        
        self._save_mental_state(state)
        
        app_logger.info(
            f"Inferred {state_type.value} for agent {agent_id}: {content} "
            f"(confidence: {confidence:.2f})"
        )
        
        return state

    def infer_nested_mental_state(
        self,
        agent_chain: List[str],
        state_type: MentalState,
        content: str,
        evidence: List[str],
        confidence: float = 0.5,
        expires_at: Optional[str] = None,
    ) -> MentalStateModel:
        """Record a bounded nested model such as Arena → owner → teammate.

        ``agent_chain`` is ordered from the modelling perspective to the
        subject, and its maximum depth is enforced by the same contract used
        by direct inference.
        """
        chain = [str(item).strip() for item in (agent_chain or []) if str(item).strip()]
        if len(chain) < 2:
            raise ValueError("nested mental states require at least observer and subject")
        return self.infer_mental_state(
            agent_id=chain[-1],
            state_type=state_type,
            content=content,
            evidence=evidence,
            confidence=confidence,
            perspective_agent_id=chain[0],
            belief_chain=chain,
            expires_at=expires_at,
        )
    
    def update_mental_state(
        self,
        state_id: str,
        content: Optional[str] = None,
        confidence: Optional[float] = None,
        evidence: Optional[List[str]] = None,
        expires_at: Optional[str] = None,
    ) -> Optional[MentalStateModel]:
        """
        Update an existing mental state.
        
        Args:
            state_id: ID of the mental state
            content: New content (optional)
            confidence: New confidence (optional)
            evidence: Additional evidence (optional)
        
        Returns:
            Updated MentalStateModel or None if not found
        """
        state = self.get_mental_state(state_id)
        if not state:
            app_logger.error(f"Mental state {state_id} not found")
            return None
        
        if content is not None:
            state.content = content
        
        if confidence is not None:
            state.confidence = self._validate_confidence(confidence)
        
        if evidence is not None:
            state.evidence.extend(str(item)[:500] for item in evidence)

        if expires_at is not None:
            state.expires_at = self._default_expiry(expires_at)
        
        state.updated_at = _now()
        
        self._save_mental_state(state)
        
        app_logger.info(f"Updated mental state {state_id}")
        
        return state
    
    def get_agent_mental_states(
        self,
        agent_id: str,
        state_type: Optional[MentalState] = None,
        *,
        include_expired: bool = False,
    ) -> List[MentalStateModel]:
        """
        Get all mental states for an agent.
        
        Args:
            agent_id: ID of the agent
            state_type: Filter by state type (optional)
        
        Returns:
            List of MentalStateModel objects
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT state_data FROM mental_states WHERE agent_id = ?"
            params = [agent_id]
            
            if state_type:
                query += " AND json_extract(state_data, '$.state_type') = ?"
                params.append(state_type.value)
            
            query += " ORDER BY updated_at DESC"
            
            cursor = conn.execute(query, params)
            
            states = []
            for row in cursor.fetchall():
                state_data = json.loads(row[0])
                state = MentalStateModel.from_dict(state_data)
                if include_expired or not self._is_expired(state):
                    states.append(state)
            
            return states
    
    def get_mental_state(
        self,
        state_id: str,
        *,
        include_expired: bool = False,
    ) -> Optional[MentalStateModel]:
        """Get a current mental state; expired inferences remain auditable."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT state_data FROM mental_states WHERE state_id = ?",
                (state_id,)
            )
            row = cursor.fetchone()
            
            if row:
                state = MentalStateModel.from_dict(json.loads(row[0]))
                if include_expired or not self._is_expired(state):
                    return state
            
            return None

    def evaluate_belief_against_observation(
        self,
        state_id: str,
        observed_content: str,
    ) -> Dict[str, Any]:
        """Compare a recorded belief with an observation without rewriting it."""
        state = self.get_mental_state(state_id)
        if state is None:
            return {
                "status": "unknown",
                "reason": "mental state is missing or expired",
                "state_id": state_id,
            }
        belief = " ".join(str(state.content).casefold().split())
        observed = " ".join(str(observed_content or "").casefold().split())
        status = "aligned" if belief == observed else "false_belief"
        return {
            "status": status,
            "state_id": state.state_id,
            "belief_content": state.content,
            "observed_content": observed_content,
            "belief_chain": list(state.belief_chain),
            "nesting_depth": state.nesting_depth,
            "confidence": state.confidence,
            "evidence": list(state.evidence),
        }
    
    # Emotion Recognition Methods
    
    def recognize_emotion(
        self,
        agent_id: str,
        primary_emotion: Emotion,
        intensity: float,
        triggers: List[str],
        secondary_emotions: List[Emotion] = None
    ) -> EmotionalState:
        """
        Recognize and record an emotional state.
        
        Args:
            agent_id: ID of the agent
            primary_emotion: Primary emotion observed
            intensity: Intensity of emotion (0-1)
            triggers: What triggered this emotion
            secondary_emotions: Additional emotions (optional)
        
        Returns:
            EmotionalState object
        """
        emotion = EmotionalState(
            agent_id=agent_id,
            primary_emotion=primary_emotion,
            intensity=intensity,
            secondary_emotions=secondary_emotions or [],
            triggers=triggers
        )
        
        self._save_emotional_state(emotion)
        
        app_logger.info(
            f"Recognized emotion for agent {agent_id}: {primary_emotion.value} "
            f"(intensity: {intensity:.2f})"
        )
        
        return emotion
    
    def get_agent_emotions(
        self,
        agent_id: str,
        limit: int = 10
    ) -> List[EmotionalState]:
        """
        Get recent emotional states for an agent.
        
        Args:
            agent_id: ID of the agent
            limit: Maximum number of emotions to return
        
        Returns:
            List of EmotionalState objects (most recent first)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT emotion_data FROM emotional_states
                WHERE agent_id = ?
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                (agent_id, limit)
            )
            
            emotions = []
            for row in cursor.fetchall():
                emotion_data = json.loads(row[0])
                emotions.append(EmotionalState.from_dict(emotion_data))
            
            return emotions
    
    def respond_to_emotion(
        self,
        agent_id: str,
        emotion: EmotionalState
    ) -> str:
        """
        Generate an appropriate response to an emotion.
        
        Args:
            agent_id: ID of the agent showing emotion
            emotion: The emotional state observed
        
        Returns:
            Appropriate response message
        """
        # Simple rule-based responses (in production, use ML/NLP)
        responses = {
            Emotion.JOY: "That's wonderful! I'm happy for you.",
            Emotion.SADNESS: "I'm sorry to hear that. How can I help?",
            Emotion.ANGER: "I understand you're frustrated. Let's work through this.",
            Emotion.FEAR: "Don't worry, I'm here to help. What's concerning you?",
            Emotion.SURPRISE: "That's interesting! Tell me more.",
            Emotion.DISGUST: "I see that bothers you. Let's find a better approach.",
            Emotion.NEUTRAL: "I'm listening. Please continue."
        }
        
        response = responses.get(emotion.primary_emotion, "I understand.")
        
        app_logger.info(f"Responding to {emotion.primary_emotion.value}: {response}")
        
        return response
    
    # Social Relationship Methods
    
    def create_relationship(
        self,
        agent1_id: str,
        agent2_id: str,
        relationship_type: RelationshipType,
        trust_level: float = 0.5,
        shared_interests: List[str] = None
    ) -> SocialRelationship:
        """
        Create a new social relationship.
        
        Args:
            agent1_id: ID of first agent
            agent2_id: ID of second agent
            relationship_type: Type of relationship
            trust_level: Initial trust level (0-1)
            shared_interests: Common interests (optional)
        
        Returns:
            SocialRelationship object
        """
        relationship = SocialRelationship(
            agent1_id=agent1_id,
            agent2_id=agent2_id,
            relationship_type=relationship_type,
            trust_level=trust_level,
            shared_interests=shared_interests or []
        )
        
        self._save_relationship(relationship)
        
        app_logger.info(
            f"Created {relationship_type.value} relationship between "
            f"{agent1_id} and {agent2_id}"
        )
        
        return relationship
    
    def update_relationship(
        self,
        relationship_id: str,
        positive: bool = True
    ) -> Optional[SocialRelationship]:
        """
        Update relationship after an interaction.
        
        Args:
            relationship_id: ID of the relationship
            positive: Whether the interaction was positive
        
        Returns:
            Updated SocialRelationship or None if not found
        """
        relationship = self.get_relationship_by_id(relationship_id)
        if not relationship:
            app_logger.error(f"Relationship {relationship_id} not found")
            return None
        
        relationship.interaction_count += 1
        
        if positive:
            relationship.positive_interactions += 1
            # Increase trust (with diminishing returns)
            relationship.trust_level = min(1.0, relationship.trust_level + 0.05 * (1 - relationship.trust_level))
        else:
            relationship.negative_interactions += 1
            # Decrease trust
            relationship.trust_level = max(0.0, relationship.trust_level - 0.1)
        
        relationship.last_interaction = _now()
        
        self._save_relationship(relationship)
        
        app_logger.info(
            f"Updated relationship {relationship_id}: "
            f"trust={relationship.trust_level:.2f}, "
            f"interactions={relationship.interaction_count}"
        )
        
        return relationship
    
    def get_relationship(
        self,
        agent1_id: str,
        agent2_id: str
    ) -> Optional[SocialRelationship]:
        """
        Get relationship between two agents.
        
        Args:
            agent1_id: ID of first agent
            agent2_id: ID of second agent
        
        Returns:
            SocialRelationship or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            # Check both orderings (agent1, agent2) and (agent2, agent1)
            cursor = conn.execute(
                """
                SELECT relationship_data FROM social_relationships
                WHERE (agent1_id = ? AND agent2_id = ?)
                   OR (agent1_id = ? AND agent2_id = ?)
                """,
                (agent1_id, agent2_id, agent2_id, agent1_id)
            )
            row = cursor.fetchone()
            
            if row:
                relationship_data = json.loads(row[0])
                return SocialRelationship.from_dict(relationship_data)
            
            return None
    
    def get_relationship_by_id(self, relationship_id: str) -> Optional[SocialRelationship]:
        """Get relationship by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT relationship_data FROM social_relationships WHERE relationship_id = ?",
                (relationship_id,)
            )
            row = cursor.fetchone()
            
            if row:
                relationship_data = json.loads(row[0])
                return SocialRelationship.from_dict(relationship_data)
            
            return None
    
    def get_agent_relationships(self, agent_id: str) -> List[SocialRelationship]:
        """Get all relationships for an agent."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT relationship_data FROM social_relationships
                WHERE agent1_id = ? OR agent2_id = ?
                ORDER BY last_interaction DESC
                """,
                (agent_id, agent_id)
            )
            
            relationships = []
            for row in cursor.fetchall():
                relationship_data = json.loads(row[0])
                relationships.append(SocialRelationship.from_dict(relationship_data))
            
            return relationships
    
    # Social Interaction Methods
    
    def record_interaction(
        self,
        participants: List[str],
        interaction_type: str,
        context: str,
        norms_followed: List[SocialNorm],
        norms_violated: List[SocialNorm],
        emotional_outcomes: Dict[str, EmotionalState],
        outcome: str
    ) -> SocialInteraction:
        """
        Record a social interaction.
        
        Args:
            participants: List of agent IDs involved
            interaction_type: Type of interaction
            context: Context of the interaction
            norms_followed: Social norms that were followed
            norms_violated: Social norms that were violated
            emotional_outcomes: Emotional outcomes for each participant
            outcome: Overall outcome (positive/negative/neutral)
        
        Returns:
            SocialInteraction object
        """
        interaction = SocialInteraction(
            participants=participants,
            interaction_type=interaction_type,
            context=context,
            norms_followed=norms_followed,
            norms_violated=norms_violated,
            emotional_outcomes=emotional_outcomes,
            outcome=outcome
        )
        
        self._save_interaction(interaction)
        
        # Update relationships based on outcome
        positive = outcome == "positive"
        for i, agent1 in enumerate(participants):
            for agent2 in participants[i+1:]:
                relationship = self.get_relationship(agent1, agent2)
                if relationship:
                    self.update_relationship(relationship.relationship_id, positive=positive)
        
        app_logger.info(
            f"Recorded {interaction_type} interaction between {len(participants)} agents "
            f"(outcome: {outcome})"
        )
        
        return interaction
    
    def get_agent_interactions(
        self,
        agent_id: str,
        limit: int = 20
    ) -> List[SocialInteraction]:
        """
        Get recent interactions for an agent.
        
        Args:
            agent_id: ID of the agent
            limit: Maximum number of interactions to return
        
        Returns:
            List of SocialInteraction objects (most recent first)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT interaction_data FROM social_interactions
                WHERE json_extract(interaction_data, '$.participants') LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (f'%{agent_id}%', limit)
            )
            
            interactions = []
            for row in cursor.fetchall():
                interaction_data = json.loads(row[0])
                interactions.append(SocialInteraction.from_dict(interaction_data))
            
            return interactions
    
    # Social Norm Understanding
    
    def check_norm_compliance(
        self,
        interaction: SocialInteraction
    ) -> Dict[SocialNorm, bool]:
        """
        Check which social norms were followed or violated.
        
        Args:
            interaction: The social interaction to check
        
        Returns:
            Dictionary mapping norms to compliance (True=followed, False=violated)
        """
        compliance = {}
        
        for norm in SocialNorm:
            if norm in interaction.norms_followed:
                compliance[norm] = True
            elif norm in interaction.norms_violated:
                compliance[norm] = False
            else:
                compliance[norm] = None  # Not applicable
        
        return compliance
    
    def suggest_norm_adherence(
        self,
        context: str,
        participants: List[str]
    ) -> List[SocialNorm]:
        """
        Suggest which social norms should be followed in a given context.
        
        Args:
            context: Context of the interaction
            participants: Agents involved
        
        Returns:
            List of recommended social norms
        """
        # Simple rule-based suggestions (in production, use ML)
        context_lower = context.lower()
        
        suggestions = [SocialNorm.RESPECT, SocialNorm.POLITENESS]
        
        if "collaborate" in context_lower or "work together" in context_lower:
            suggestions.extend([SocialNorm.COOPERATION, SocialNorm.FAIRNESS])
        
        if "help" in context_lower or "favor" in context_lower:
            suggestions.append(SocialNorm.RECIPROCITY)
        
        if "emotion" in context_lower or "feeling" in context_lower:
            suggestions.append(SocialNorm.EMPATHY)
        
        if "truth" in context_lower or "honest" in context_lower:
            suggestions.append(SocialNorm.HONESTY)
        
        if "conversation" in context_lower or "discussion" in context_lower:
            suggestions.append(SocialNorm.TURN_TAKING)
        
        return suggestions
    
    # Collaborative Problem Solving
    
    def facilitate_collaboration(
        self,
        participants: List[str],
        problem: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Facilitate collaborative problem solving.
        
        Args:
            participants: List of agent IDs
            problem: Problem to solve
            context: Additional context
        
        Returns:
            Collaboration plan with roles and norms
        """
        # Get relationships between participants
        relationships = []
        for i, agent1 in enumerate(participants):
            for agent2 in participants[i+1:]:
                rel = self.get_relationship(agent1, agent2)
                if rel:
                    relationships.append(rel)
        
        # Calculate average trust
        avg_trust = (
            sum(r.trust_level for r in relationships) / len(relationships)
            if relationships else 0.5
        )
        
        # Suggest norms based on trust level
        if avg_trust > 0.7:
            norms = [SocialNorm.COOPERATION, SocialNorm.FAIRNESS, SocialNorm.RECIPROCITY]
        elif avg_trust > 0.4:
            norms = [SocialNorm.COOPERATION, SocialNorm.RESPECT, SocialNorm.TURN_TAKING]
        else:
            norms = [SocialNorm.RESPECT, SocialNorm.POLITENESS, SocialNorm.TURN_TAKING]
        
        # Assign roles based on expertise (simplified)
        roles = {agent_id: "contributor" for agent_id in participants}
        if len(participants) > 0:
            roles[participants[0]] = "facilitator"
        
        plan = {
            "problem": problem,
            "participants": participants,
            "roles": roles,
            "norms": [n.value for n in norms],
            "average_trust": avg_trust,
            "recommendations": [
                "Establish clear communication channels",
                "Define success criteria",
                "Agree on decision-making process"
            ]
        }
        
        app_logger.info(
            f"Facilitated collaboration for {len(participants)} agents "
            f"(avg trust: {avg_trust:.2f})"
        )
        
        return plan
    
    # Database Helper Methods
    
    def _save_mental_state(self, state: MentalStateModel) -> None:
        """Save mental state to database."""
        state_data = json.dumps(state.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO mental_states
                (state_id, agent_id, state_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                state.state_id,
                state.agent_id,
                state_data,
                state.created_at,
                state.updated_at
            ))
            conn.commit()
    
    def _save_emotional_state(self, emotion: EmotionalState) -> None:
        """Save emotional state to database."""
        emotion_data = json.dumps(emotion.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO emotional_states
                (emotion_id, agent_id, emotion_data, observed_at)
                VALUES (?, ?, ?, ?)
            """, (
                emotion.emotion_id,
                emotion.agent_id,
                emotion_data,
                emotion.observed_at
            ))
            conn.commit()
    
    def _save_relationship(self, relationship: SocialRelationship) -> None:
        """Save relationship to database."""
        relationship_data = json.dumps(relationship.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO social_relationships
                (relationship_id, agent1_id, agent2_id, relationship_data, created_at, last_interaction)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                relationship.relationship_id,
                relationship.agent1_id,
                relationship.agent2_id,
                relationship_data,
                relationship.created_at,
                relationship.last_interaction
            ))
            conn.commit()
    
    def _save_interaction(self, interaction: SocialInteraction) -> None:
        """Save interaction to database."""
        interaction_data = json.dumps(interaction.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO social_interactions
                (interaction_id, interaction_data, timestamp)
                VALUES (?, ?, ?)
            """, (
                interaction.interaction_id,
                interaction_data,
                interaction.timestamp
            ))
            conn.commit()
    
    # Summary and Analytics
    
    def get_social_summary(self, agent_id: str) -> Dict[str, Any]:
        """
        Get social cognition summary for an agent.
        
        Args:
            agent_id: ID of the agent
        
        Returns:
            Summary dictionary with social metrics
        """
        relationships = self.get_agent_relationships(agent_id)
        emotions = self.get_agent_emotions(agent_id, limit=100)
        interactions = self.get_agent_interactions(agent_id, limit=100)
        
        avg_trust = (
            sum(r.trust_level for r in relationships) / len(relationships)
            if relationships else 0.0
        )
        
        positive_interactions = sum(
            1 for i in interactions if i.outcome == "positive"
        )
        
        emotion_distribution = {}
        for emotion in emotions:
            emotion_name = emotion.primary_emotion.value
            emotion_distribution[emotion_name] = emotion_distribution.get(emotion_name, 0) + 1
        
        return {
            "total_relationships": len(relationships),
            "average_trust": avg_trust,
            "total_interactions": len(interactions),
            "positive_interactions": positive_interactions,
            "positive_interaction_rate": (
                positive_interactions / len(interactions)
                if interactions else 0.0
            ),
            "emotion_distribution": emotion_distribution,
            "relationship_types": {
                rt.value: sum(1 for r in relationships if r.relationship_type == rt)
                for rt in RelationshipType
            }
        }
