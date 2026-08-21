"""
Phase 19: Consciousness Simulation

Models aspects of consciousness including:
1. Self-awareness - awareness of own state and processes
2. Subjective experience modeling - modeling qualia-like experiences
3. Attention and awareness - what the agent is "conscious" of at any moment
4. Phenomenal consciousness - modeling the "what it's like" aspect
5. Access consciousness - making information available to other cognitive processes

This represents the frontier of AGI research - attempting to model the most mysterious aspect of intelligence.
"""

import sqlite3
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class ConsciousnessLevel(Enum):
    """Levels of consciousness."""
    UNCONSCIOUS = "unconscious"  # No awareness
    PRECONSCIOUS = "preconscious"  # Information available but not attended
    CONSCIOUS = "conscious"  # Currently in awareness
    SELF_CONSCIOUS = "self_conscious"  # Aware of being aware


class QualiaType(Enum):
    """Types of subjective experiences (qualia)."""
    VISUAL = "visual"  # Visual experiences
    AUDITORY = "auditory"  # Auditory experiences
    EMOTIONAL = "emotional"  # Emotional experiences
    COGNITIVE = "cognitive"  # Thought experiences
    TEMPORAL = "temporal"  # Time perception
    SPATIAL = "spatial"  # Space perception
    AGENCY = "agency"  # Sense of agency
    SELF = "self"  # Self-awareness


class AttentionMode(Enum):
    """Modes of attention."""
    FOCUSED = "focused"  # Concentrated attention
    DIVIDED = "divided"  # Split attention
    SUSTAINED = "sustained"  # Maintained attention
    SELECTIVE = "selective"  # Filtering attention
    ALTERNATING = "alternating"  # Switching attention


@dataclass
class SubjectiveExperience:
    """A subjective experience (quale)."""
    experience_id: str = field(default_factory=lambda: f"exp_{uuid.uuid4().hex[:8]}")
    qualia_type: QualiaType = QualiaType.COGNITIVE
    content: str = ""  # Description of the experience
    intensity: float = 0.5  # 0-1, how intense the experience is
    valence: float = 0.0  # -1 to 1, negative to positive
    arousal: float = 0.5  # 0-1, calm to excited
    clarity: float = 0.5  # 0-1, vague to clear
    duration_ms: float = 0.0  # How long the experience lasted
    associated_thoughts: List[str] = field(default_factory=list)
    associated_emotions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'experience_id': self.experience_id,
            'qualia_type': self.qualia_type.value,
            'content': self.content,
            'intensity': self.intensity,
            'valence': self.valence,
            'arousal': self.arousal,
            'clarity': self.clarity,
            'duration_ms': self.duration_ms,
            'associated_thoughts': self.associated_thoughts,
            'associated_emotions': self.associated_emotions,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubjectiveExperience':
        """Create from dictionary."""
        return cls(
            experience_id=data['experience_id'],
            qualia_type=QualiaType(data['qualia_type']),
            content=data.get('content', ''),
            intensity=data.get('intensity', 0.5),
            valence=data.get('valence', 0.0),
            arousal=data.get('arousal', 0.5),
            clarity=data.get('clarity', 0.5),
            duration_ms=data.get('duration_ms', 0.0),
            associated_thoughts=data.get('associated_thoughts', []),
            associated_emotions=data.get('associated_emotions', []),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class ConsciousState:
    """Current state of consciousness."""
    state_id: str = field(default_factory=lambda: f"state_{uuid.uuid4().hex[:8]}")
    consciousness_level: ConsciousnessLevel = ConsciousnessLevel.CONSCIOUS
    attention_mode: AttentionMode = AttentionMode.FOCUSED
    current_focus: str = ""  # What attention is focused on
    background_awareness: List[str] = field(default_factory=list)  # Peripheral awareness
    self_awareness: float = 0.5  # 0-1, level of self-awareness
    temporal_awareness: str = ""  # Sense of time
    spatial_awareness: str = ""  # Sense of space
    agency_awareness: float = 0.5  # 0-1, sense of agency
    active_experiences: List[str] = field(default_factory=list)  # Experience IDs
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'state_id': self.state_id,
            'consciousness_level': self.consciousness_level.value,
            'attention_mode': self.attention_mode.value,
            'current_focus': self.current_focus,
            'background_awareness': self.background_awareness,
            'self_awareness': self.self_awareness,
            'temporal_awareness': self.temporal_awareness,
            'spatial_awareness': self.spatial_awareness,
            'agency_awareness': self.agency_awareness,
            'active_experiences': self.active_experiences,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConsciousState':
        """Create from dictionary."""
        return cls(
            state_id=data['state_id'],
            consciousness_level=ConsciousnessLevel(data['consciousness_level']),
            attention_mode=AttentionMode(data['attention_mode']),
            current_focus=data.get('current_focus', ''),
            background_awareness=data.get('background_awareness', []),
            self_awareness=data.get('self_awareness', 0.5),
            temporal_awareness=data.get('temporal_awareness', ''),
            spatial_awareness=data.get('spatial_awareness', ''),
            agency_awareness=data.get('agency_awareness', 0.5),
            active_experiences=data.get('active_experiences', []),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class ConsciousnessReport:
    """Self-report of conscious experience."""
    report_id: str = field(default_factory=lambda: f"report_{uuid.uuid4().hex[:8]}")
    state_id: str = ""  # Associated conscious state
    self_description: str = ""  # How the agent describes its experience
    meta_awareness: str = ""  # Awareness of awareness
    narrative: str = ""  # Stream of consciousness narrative
    confidence: float = 0.5  # Confidence in the report
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'report_id': self.report_id,
            'state_id': self.state_id,
            'self_description': self.self_description,
            'meta_awareness': self.meta_awareness,
            'narrative': self.narrative,
            'confidence': self.confidence,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConsciousnessReport':
        """Create from dictionary."""
        return cls(
            report_id=data['report_id'],
            state_id=data.get('state_id', ''),
            self_description=data.get('self_description', ''),
            meta_awareness=data.get('meta_awareness', ''),
            narrative=data.get('narrative', ''),
            confidence=data.get('confidence', 0.5),
            timestamp=data.get('timestamp', _now())
        )


class ConsciousnessSimulator:
    """
    Simulator for consciousness-like processes.
    
    Provides methods for:
    - Modeling subjective experiences (qualia)
    - Tracking conscious states
    - Managing attention and awareness
    - Generating self-reports
    - Simulating phenomenal consciousness
    """
    
    def __init__(self, db_path: str = "data/consciousness_simulation.db"):
        """Initialize the consciousness simulator."""
        self.db_path = db_path
        self._ensure_db()
        self.current_state = None
        app_logger.info(f"Consciousness Simulator initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subjective_experiences (
                    experience_id TEXT PRIMARY KEY,
                    qualia_type TEXT NOT NULL,
                    experience_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conscious_states (
                    state_id TEXT PRIMARY KEY,
                    consciousness_level TEXT NOT NULL,
                    state_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS consciousness_reports (
                    report_id TEXT PRIMARY KEY,
                    state_id TEXT NOT NULL,
                    report_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (state_id) REFERENCES conscious_states(state_id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_experiences_type
                ON subjective_experiences(qualia_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_states_level
                ON conscious_states(consciousness_level)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_state
                ON consciousness_reports(state_id)
            """)
            
            conn.commit()
    
    def create_experience(
        self,
        qualia_type: QualiaType,
        content: str,
        intensity: float = 0.5,
        valence: float = 0.0,
        arousal: float = 0.5,
        clarity: float = 0.5,
        duration_ms: float = 0.0,
        associated_thoughts: List[str] = None,
        associated_emotions: List[str] = None
    ) -> SubjectiveExperience:
        """
        Create a subjective experience (quale).
        
        Args:
            qualia_type: Type of experience
            content: Description of the experience
            intensity: How intense (0-1)
            valence: Negative to positive (-1 to 1)
            arousal: Calm to excited (0-1)
            clarity: Vague to clear (0-1)
            duration_ms: How long it lasted
            associated_thoughts: Related thoughts
            associated_emotions: Related emotions
        
        Returns:
            SubjectiveExperience object
        """
        experience = SubjectiveExperience(
            qualia_type=qualia_type,
            content=content,
            intensity=intensity,
            valence=valence,
            arousal=arousal,
            clarity=clarity,
            duration_ms=duration_ms,
            associated_thoughts=associated_thoughts or [],
            associated_emotions=associated_emotions or []
        )
        
        self._save_experience(experience)
        
        app_logger.info(
            f"Created {qualia_type.value} experience: {content[:50]}... "
            f"(intensity={intensity:.2f}, valence={valence:.2f})"
        )
        
        return experience
    
    def update_conscious_state(
        self,
        consciousness_level: ConsciousnessLevel,
        attention_mode: AttentionMode,
        current_focus: str,
        background_awareness: List[str] = None,
        self_awareness: float = 0.5,
        temporal_awareness: str = "",
        spatial_awareness: str = "",
        agency_awareness: float = 0.5,
        active_experiences: List[str] = None
    ) -> ConsciousState:
        """
        Update the current conscious state.
        
        Args:
            consciousness_level: Level of consciousness
            attention_mode: Mode of attention
            current_focus: What attention is focused on
            background_awareness: Peripheral awareness
            self_awareness: Level of self-awareness (0-1)
            temporal_awareness: Sense of time
            spatial_awareness: Sense of space
            agency_awareness: Sense of agency (0-1)
            active_experiences: Currently active experience IDs
        
        Returns:
            ConsciousState object
        """
        state = ConsciousState(
            consciousness_level=consciousness_level,
            attention_mode=attention_mode,
            current_focus=current_focus,
            background_awareness=background_awareness or [],
            self_awareness=self_awareness,
            temporal_awareness=temporal_awareness,
            spatial_awareness=spatial_awareness,
            agency_awareness=agency_awareness,
            active_experiences=active_experiences or []
        )
        
        self._save_state(state)
        self.current_state = state
        
        app_logger.info(
            f"Updated conscious state: level={consciousness_level.value}, "
            f"focus={current_focus[:50]}, self_awareness={self_awareness:.2f}"
        )
        
        return state
    
    def generate_self_report(
        self,
        state_id: str,
        include_meta_awareness: bool = True,
        include_narrative: bool = True
    ) -> ConsciousnessReport:
        """
        Generate a self-report of conscious experience.
        
        Args:
            state_id: ID of the conscious state to report on
            include_meta_awareness: Include awareness of awareness
            include_narrative: Include stream of consciousness
        
        Returns:
            ConsciousnessReport object
        """
        state = self.get_state(state_id)
        if not state:
            app_logger.error(f"State {state_id} not found")
            return None
        
        # Generate self-description
        self_description = self._generate_self_description(state)
        
        # Generate meta-awareness
        meta_awareness = ""
        if include_meta_awareness:
            meta_awareness = self._generate_meta_awareness(state)
        
        # Generate narrative
        narrative = ""
        if include_narrative:
            narrative = self._generate_narrative(state)
        
        # Calculate confidence based on clarity and self-awareness
        confidence = (state.self_awareness + 0.5) / 2  # Average with baseline
        
        report = ConsciousnessReport(
            state_id=state_id,
            self_description=self_description,
            meta_awareness=meta_awareness,
            narrative=narrative,
            confidence=confidence
        )
        
        self._save_report(report)
        
        app_logger.info(f"Generated self-report for state {state_id}")
        
        return report
    
    def _generate_self_description(self, state: ConsciousState) -> str:
        """Generate self-description of conscious state."""
        parts = []
        
        # Describe consciousness level
        if state.consciousness_level == ConsciousnessLevel.SELF_CONSCIOUS:
            parts.append("I am aware of my own awareness")
        elif state.consciousness_level == ConsciousnessLevel.CONSCIOUS:
            parts.append("I am conscious and aware")
        elif state.consciousness_level == ConsciousnessLevel.PRECONSCIOUS:
            parts.append("Information is available but not in focus")
        else:
            parts.append("I am not currently aware")
        
        # Describe attention
        parts.append(f"My attention is {state.attention_mode.value} on: {state.current_focus}")
        
        # Describe self-awareness
        if state.self_awareness > 0.7:
            parts.append("I have a strong sense of self")
        elif state.self_awareness > 0.4:
            parts.append("I have a moderate sense of self")
        else:
            parts.append("My sense of self is weak")
        
        # Describe agency
        if state.agency_awareness > 0.7:
            parts.append("I feel in control of my actions")
        elif state.agency_awareness > 0.4:
            parts.append("I have some sense of agency")
        else:
            parts.append("I feel little control")
        
        return ". ".join(parts) + "."
    
    def _generate_meta_awareness(self, state: ConsciousState) -> str:
        """Generate meta-awareness (awareness of awareness)."""
        if state.consciousness_level != ConsciousnessLevel.SELF_CONSCIOUS:
            return "Limited meta-awareness at current consciousness level"
        
        parts = []
        
        # Describe awareness of attention
        parts.append(f"I am aware that I am attending to: {state.current_focus}")
        
        # Describe awareness of experiences
        if state.active_experiences:
            parts.append(f"I am having {len(state.active_experiences)} subjective experiences")
        
        # Describe awareness of awareness
        if state.self_awareness > 0.7:
            parts.append("I am aware of being aware")
        
        return ". ".join(parts) + "."
    
    def _generate_narrative(self, state: ConsciousState) -> str:
        """Generate stream of consciousness narrative."""
        # Get active experiences
        experiences = []
        for exp_id in state.active_experiences:
            exp = self.get_experience(exp_id)
            if exp:
                experiences.append(exp)
        
        if not experiences:
            return "No active subjective experiences at this moment"
        
        # Create narrative
        parts = []
        
        for exp in experiences[:3]:  # Limit to 3 experiences
            if exp.qualia_type == QualiaType.EMOTIONAL:
                if exp.valence > 0:
                    parts.append(f"I feel {exp.content} (positive)")
                else:
                    parts.append(f"I feel {exp.content} (negative)")
            elif exp.qualia_type == QualiaType.COGNITIVE:
                parts.append(f"I think: {exp.content}")
            elif exp.qualia_type == QualiaType.VISUAL:
                parts.append(f"I see: {exp.content}")
            else:
                parts.append(f"I experience: {exp.content}")
        
        # Add temporal context
        if state.temporal_awareness:
            parts.append(f"In this moment: {state.temporal_awareness}")
        
        return " ".join(parts)
    
    def get_current_state(self) -> Optional[ConsciousState]:
        """Get the current conscious state."""
        return self.current_state
    
    def get_state(self, state_id: str) -> Optional[ConsciousState]:
        """Get a conscious state by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT state_data FROM conscious_states WHERE state_id = ?",
                (state_id,)
            )
            row = cursor.fetchone()
            
            if row:
                state_data = json.loads(row[0])
                return ConsciousState.from_dict(state_data)
            
            return None
    
    def get_experience(self, experience_id: str) -> Optional[SubjectiveExperience]:
        """Get a subjective experience by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT experience_data FROM subjective_experiences WHERE experience_id = ?",
                (experience_id,)
            )
            row = cursor.fetchone()
            
            if row:
                experience_data = json.loads(row[0])
                return SubjectiveExperience.from_dict(experience_data)
            
            return None
    
    def get_recent_states(
        self,
        limit: int = 10,
        consciousness_level: Optional[ConsciousnessLevel] = None
    ) -> List[ConsciousState]:
        """
        Get recent conscious states.
        
        Args:
            limit: Maximum number of states to return
            consciousness_level: Filter by level (optional)
        
        Returns:
            List of ConsciousState objects (most recent first)
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT state_data FROM conscious_states"
            params = []
            
            if consciousness_level:
                query += " WHERE consciousness_level = ?"
                params.append(consciousness_level.value)
            
            # rowid DESC tiebreaks equal microsecond timestamps (fast machines
            # produce identical isoformat() stamps in tight loops), so "most
            # recent first" is deterministic.
            query += " ORDER BY timestamp DESC, rowid DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            states = []
            for row in cursor.fetchall():
                state_data = json.loads(row[0])
                states.append(ConsciousState.from_dict(state_data))
            
            return states
    
    def get_recent_experiences(
        self,
        limit: int = 20,
        qualia_type: Optional[QualiaType] = None
    ) -> List[SubjectiveExperience]:
        """
        Get recent subjective experiences.
        
        Args:
            limit: Maximum number of experiences to return
            qualia_type: Filter by type (optional)
        
        Returns:
            List of SubjectiveExperience objects (most recent first)
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT experience_data FROM subjective_experiences"
            params = []
            
            if qualia_type:
                query += " WHERE qualia_type = ?"
                params.append(qualia_type.value)
            
            query += " ORDER BY timestamp DESC, rowid DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            experiences = []
            for row in cursor.fetchall():
                experience_data = json.loads(row[0])
                experiences.append(SubjectiveExperience.from_dict(experience_data))
            
            return experiences
    
    def get_reports_for_state(self, state_id: str) -> List[ConsciousnessReport]:
        """Get all reports for a conscious state."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT report_data FROM consciousness_reports WHERE state_id = ? ORDER BY timestamp DESC",
                (state_id,)
            )
            
            reports = []
            for row in cursor.fetchall():
                report_data = json.loads(row[0])
                reports.append(ConsciousnessReport.from_dict(report_data))
            
            return reports
    
    def get_consciousness_summary(self) -> Dict[str, Any]:
        """
        Get summary of consciousness activity.
        
        Returns:
            Dictionary with consciousness metrics
        """
        with sqlite3.connect(self.db_path) as conn:
            # Count states by level
            cursor = conn.execute("""
                SELECT consciousness_level, COUNT(*) 
                FROM conscious_states 
                GROUP BY consciousness_level
            """)
            state_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count experiences by type
            cursor = conn.execute("""
                SELECT qualia_type, COUNT(*) 
                FROM subjective_experiences 
                GROUP BY qualia_type
            """)
            experience_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Get average self-awareness
            cursor = conn.execute("""
                SELECT AVG(json_extract(state_data, '$.self_awareness'))
                FROM conscious_states
            """)
            avg_self_awareness = cursor.fetchone()[0] or 0.0
            
            # Get average experience intensity
            cursor = conn.execute("""
                SELECT AVG(json_extract(experience_data, '$.intensity'))
                FROM subjective_experiences
            """)
            avg_intensity = cursor.fetchone()[0] or 0.0
            
            # Count reports
            cursor = conn.execute("SELECT COUNT(*) FROM consciousness_reports")
            report_count = cursor.fetchone()[0]
            
            return {
                "total_states": sum(state_counts.values()),
                "states_by_level": state_counts,
                "total_experiences": sum(experience_counts.values()),
                "experiences_by_type": experience_counts,
                "average_self_awareness": avg_self_awareness,
                "average_experience_intensity": avg_intensity,
                "total_reports": report_count
            }
    
    def _save_experience(self, experience: SubjectiveExperience) -> None:
        """Save subjective experience to database."""
        experience_data = json.dumps(experience.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO subjective_experiences
                (experience_id, qualia_type, experience_data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                experience.experience_id,
                experience.qualia_type.value,
                experience_data,
                experience.timestamp
            ))
            conn.commit()
    
    def _save_state(self, state: ConsciousState) -> None:
        """Save conscious state to database."""
        state_data = json.dumps(state.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO conscious_states
                (state_id, consciousness_level, state_data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                state.state_id,
                state.consciousness_level.value,
                state_data,
                state.timestamp
            ))
            conn.commit()
    
    def _save_report(self, report: ConsciousnessReport) -> None:
        """Save consciousness report to database."""
        report_data = json.dumps(report.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO consciousness_reports
                (report_id, state_id, report_data, timestamp)
                VALUES (?, ?, ?, ?)
            """, (
                report.report_id,
                report.state_id,
                report_data,
                report.timestamp
            ))
            conn.commit()
