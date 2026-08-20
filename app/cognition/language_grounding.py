"""
Phase 22: Language Grounding

Connects linguistic symbols to perceptual experiences, actions, and embodied meaning.
This is the final piece that enables true understanding rather than symbol manipulation.

Enables the agent to:
1. Ground words/phrases to perceptual experiences
2. Connect language to actions and affordances
3. Understand multimodal meaning (text + vision + sound)
4. Perform pragmatic inference and contextual meaning
5. Achieve embodied language comprehension
"""

import sqlite3
import json
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid
from app.utils.logger import app_logger


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class GroundingType(Enum):
    """Types of language grounding."""
    PERCEPTUAL = "perceptual"  # Grounded to sensory experience
    MOTOR = "motor"  # Grounded to actions
    SPATIAL = "spatial"  # Grounded to spatial relations
    TEMPORAL = "temporal"  # Grounded to time
    SOCIAL = "social"  # Grounded to social context
    EMOTIONAL = "emotional"  # Grounded to emotions
    MULTIMODAL = "multimodal"  # Grounded to multiple modalities


class SymbolType(Enum):
    """Types of linguistic symbols."""
    WORD = "word"  # Single word
    PHRASE = "phrase"  # Multi-word phrase
    SENTENCE = "sentence"  # Complete sentence
    UTTERANCE = "utterance"  # Spoken utterance


@dataclass
class PerceptualGrounding:
    """Grounding a symbol to perceptual experience."""
    grounding_id: str = field(default_factory=lambda: f"ground_{uuid.uuid4().hex[:8]}")
    symbol: str = ""
    symbol_type: SymbolType = SymbolType.WORD
    modality: str = ""  # "vision", "auditory", "tactile", etc.
    perceptual_features: Dict[str, float] = field(default_factory=dict)
    sensory_experience: str = ""
    confidence: float = 0.5
    examples: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'grounding_id': self.grounding_id,
            'symbol': self.symbol,
            'symbol_type': self.symbol_type.value,
            'modality': self.modality,
            'perceptual_features': self.perceptual_features,
            'sensory_experience': self.sensory_experience,
            'confidence': self.confidence,
            'examples': self.examples,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerceptualGrounding':
        """Create from dictionary."""
        return cls(
            grounding_id=data['grounding_id'],
            symbol=data['symbol'],
            symbol_type=SymbolType(data['symbol_type']),
            modality=data.get('modality', ''),
            perceptual_features=data.get('perceptual_features', {}),
            sensory_experience=data.get('sensory_experience', ''),
            confidence=data.get('confidence', 0.5),
            examples=data.get('examples', []),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class ActionGrounding:
    """Grounding a symbol to actions and affordances."""
    grounding_id: str = field(default_factory=lambda: f"action_{uuid.uuid4().hex[:8]}")
    symbol: str = ""
    symbol_type: SymbolType = SymbolType.WORD
    associated_actions: List[str] = field(default_factory=list)
    affordances: List[str] = field(default_factory=list)
    motor_programs: List[Dict[str, Any]] = field(default_factory=list)
    action_outcomes: List[str] = field(default_factory=list)
    confidence: float = 0.5
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'grounding_id': self.grounding_id,
            'symbol': self.symbol,
            'symbol_type': self.symbol_type.value,
            'associated_actions': self.associated_actions,
            'affordances': self.affordances,
            'motor_programs': self.motor_programs,
            'action_outcomes': self.action_outcomes,
            'confidence': self.confidence,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActionGrounding':
        """Create from dictionary."""
        return cls(
            grounding_id=data['grounding_id'],
            symbol=data['symbol'],
            symbol_type=SymbolType(data['symbol_type']),
            associated_actions=data.get('associated_actions', []),
            affordances=data.get('affordances', []),
            motor_programs=data.get('motor_programs', []),
            action_outcomes=data.get('action_outcomes', []),
            confidence=data.get('confidence', 0.5),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class MultimodalGrounding:
    """Grounding a symbol to multiple modalities."""
    grounding_id: str = field(default_factory=lambda: f"multi_{uuid.uuid4().hex[:8]}")
    symbol: str = ""
    symbol_type: SymbolType = SymbolType.WORD
    modalities: List[str] = field(default_factory=list)
    perceptual_groundings: List[str] = field(default_factory=list)  # grounding_ids
    action_groundings: List[str] = field(default_factory=list)  # grounding_ids
    integration_weights: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.5
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'grounding_id': self.grounding_id,
            'symbol': self.symbol,
            'symbol_type': self.symbol_type.value,
            'modalities': self.modalities,
            'perceptual_groundings': self.perceptual_groundings,
            'action_groundings': self.action_groundings,
            'integration_weights': self.integration_weights,
            'confidence': self.confidence,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MultimodalGrounding':
        """Create from dictionary."""
        return cls(
            grounding_id=data['grounding_id'],
            symbol=data['symbol'],
            symbol_type=SymbolType(data['symbol_type']),
            modalities=data.get('modalities', []),
            perceptual_groundings=data.get('perceptual_groundings', []),
            action_groundings=data.get('action_groundings', []),
            integration_weights=data.get('integration_weights', {}),
            confidence=data.get('confidence', 0.5),
            timestamp=data.get('timestamp', _now())
        )


@dataclass
class ContextualMeaning:
    """Contextual meaning of a symbol in a specific context."""
    meaning_id: str = field(default_factory=lambda: f"meaning_{uuid.uuid4().hex[:8]}")
    symbol: str = ""
    context: str = ""
    intended_meaning: str = ""
    pragmatic_inferences: List[str] = field(default_factory=list)
    grounding_ids: List[str] = field(default_factory=list)
    confidence: float = 0.5
    timestamp: str = field(default_factory=_now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'meaning_id': self.meaning_id,
            'symbol': self.symbol,
            'context': self.context,
            'intended_meaning': self.intended_meaning,
            'pragmatic_inferences': self.pragmatic_inferences,
            'grounding_ids': self.grounding_ids,
            'confidence': self.confidence,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContextualMeaning':
        """Create from dictionary."""
        return cls(
            meaning_id=data['meaning_id'],
            symbol=data['symbol'],
            context=data.get('context', ''),
            intended_meaning=data.get('intended_meaning', ''),
            pragmatic_inferences=data.get('pragmatic_inferences', []),
            grounding_ids=data.get('grounding_ids', []),
            confidence=data.get('confidence', 0.5),
            timestamp=data.get('timestamp', _now())
        )


class LanguageGroundingEngine:
    """
    Engine for grounding language in perceptual, motor, and embodied experience.
    
    Provides methods for:
    - Creating perceptual groundings
    - Creating action groundings
    - Creating multimodal groundings
    - Contextual meaning inference
    - Pragmatic understanding
    """
    
    def __init__(self, db_path: str = "data/language_grounding.db"):
        """Initialize the language grounding engine."""
        self.db_path = db_path
        self._ensure_db()
        app_logger.info(f"Language Grounding Engine initialized (db: {db_path})")
    
    def _ensure_db(self) -> None:
        """Ensure database tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS perceptual_groundings (
                    grounding_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    symbol_type TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    grounding_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS action_groundings (
                    grounding_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    symbol_type TEXT NOT NULL,
                    grounding_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS multimodal_groundings (
                    grounding_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    symbol_type TEXT NOT NULL,
                    grounding_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contextual_meanings (
                    meaning_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    context TEXT NOT NULL,
                    meaning_data TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perceptual_symbol
                ON perceptual_groundings(symbol)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perceptual_modality
                ON perceptual_groundings(modality)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_action_symbol
                ON action_groundings(symbol)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_multimodal_symbol
                ON multimodal_groundings(symbol)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_meaning_symbol
                ON contextual_meanings(symbol)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_meaning_context
                ON contextual_meanings(context)
            """)
            
            conn.commit()
    
    def create_perceptual_grounding(
        self,
        symbol: str,
        modality: str,
        perceptual_features: Dict[str, float],
        sensory_experience: str,
        symbol_type: SymbolType = SymbolType.WORD,
        confidence: float = 0.5,
        examples: List[str] = None
    ) -> PerceptualGrounding:
        """
        Create a perceptual grounding for a symbol.
        
        Args:
            symbol: The linguistic symbol (word, phrase, etc.)
            modality: Sensory modality ("vision", "auditory", "tactile", etc.)
            perceptual_features: Features extracted from perception
            sensory_experience: Description of sensory experience
            symbol_type: Type of symbol
            confidence: Confidence in grounding (0-1)
            examples: Example instances
        
        Returns:
            PerceptualGrounding object
        """
        grounding = PerceptualGrounding(
            symbol=symbol,
            symbol_type=symbol_type,
            modality=modality,
            perceptual_features=perceptual_features,
            sensory_experience=sensory_experience,
            confidence=confidence,
            examples=examples or []
        )
        
        self._save_perceptual_grounding(grounding)
        
        app_logger.info(
            f"Created perceptual grounding: '{symbol}' → {modality} "
            f"(confidence: {confidence:.2f})"
        )
        
        return grounding
    
    def create_action_grounding(
        self,
        symbol: str,
        associated_actions: List[str],
        affordances: List[str],
        motor_programs: List[Dict[str, Any]] = None,
        action_outcomes: List[str] = None,
        symbol_type: SymbolType = SymbolType.WORD,
        confidence: float = 0.5
    ) -> ActionGrounding:
        """
        Create an action grounding for a symbol.
        
        Args:
            symbol: The linguistic symbol
            associated_actions: Actions associated with the symbol
            affordances: What the symbol affords/allows
            motor_programs: Motor programs for actions
            action_outcomes: Expected outcomes of actions
            symbol_type: Type of symbol
            confidence: Confidence in grounding (0-1)
        
        Returns:
            ActionGrounding object
        """
        grounding = ActionGrounding(
            symbol=symbol,
            symbol_type=symbol_type,
            associated_actions=associated_actions,
            affordances=affordances,
            motor_programs=motor_programs or [],
            action_outcomes=action_outcomes or [],
            confidence=confidence
        )
        
        self._save_action_grounding(grounding)
        
        app_logger.info(
            f"Created action grounding: '{symbol}' → {len(associated_actions)} actions "
            f"(confidence: {confidence:.2f})"
        )
        
        return grounding
    
    def create_multimodal_grounding(
        self,
        symbol: str,
        modalities: List[str],
        perceptual_groundings: List[str] = None,
        action_groundings: List[str] = None,
        integration_weights: Dict[str, float] = None,
        symbol_type: SymbolType = SymbolType.WORD,
        confidence: float = 0.5
    ) -> MultimodalGrounding:
        """
        Create a multimodal grounding for a symbol.
        
        Args:
            symbol: The linguistic symbol
            modalities: Modalities involved
            perceptual_groundings: IDs of perceptual groundings
            action_groundings: IDs of action groundings
            integration_weights: Weights for integrating modalities
            symbol_type: Type of symbol
            confidence: Confidence in grounding (0-1)
        
        Returns:
            MultimodalGrounding object
        """
        grounding = MultimodalGrounding(
            symbol=symbol,
            symbol_type=symbol_type,
            modalities=modalities,
            perceptual_groundings=perceptual_groundings or [],
            action_groundings=action_groundings or [],
            integration_weights=integration_weights or {},
            confidence=confidence
        )
        
        self._save_multimodal_grounding(grounding)
        
        app_logger.info(
            f"Created multimodal grounding: '{symbol}' → {len(modalities)} modalities "
            f"(confidence: {confidence:.2f})"
        )
        
        return grounding
    
    def infer_contextual_meaning(
        self,
        symbol: str,
        context: str,
        grounding_ids: List[str] = None,
        pragmatic_inferences: List[str] = None,
        confidence: float = 0.5
    ) -> ContextualMeaning:
        """
        Infer contextual meaning of a symbol.
        
        Args:
            symbol: The linguistic symbol
            context: The context in which it appears
            grounding_ids: Relevant grounding IDs
            pragmatic_inferences: Pragmatic inferences made
            confidence: Confidence in meaning (0-1)
        
        Returns:
            ContextualMeaning object
        """
        # Infer intended meaning from context and groundings
        intended_meaning = self._infer_intended_meaning(
            symbol, context, grounding_ids or []
        )
        
        meaning = ContextualMeaning(
            symbol=symbol,
            context=context,
            intended_meaning=intended_meaning,
            pragmatic_inferences=pragmatic_inferences or [],
            grounding_ids=grounding_ids or [],
            confidence=confidence
        )
        
        self._save_contextual_meaning(meaning)
        
        app_logger.info(
            f"Inferred contextual meaning: '{symbol}' in '{context}' → "
            f"'{intended_meaning[:50]}...' (confidence: {confidence:.2f})"
        )
        
        return meaning
    
    def _infer_intended_meaning(
        self,
        symbol: str,
        context: str,
        grounding_ids: List[str]
    ) -> str:
        """Infer intended meaning from context and groundings."""
        # Simple heuristic: combine symbol, context, and grounding information
        meaning_parts = [f"Symbol '{symbol}'"]
        
        if context:
            meaning_parts.append(f"in context '{context}'")
        
        if grounding_ids:
            meaning_parts.append(f"grounded in {len(grounding_ids)} experiences")
        
        return " ".join(meaning_parts)
    
    def get_perceptual_groundings(
        self,
        symbol: Optional[str] = None,
        modality: Optional[str] = None,
        limit: int = 100
    ) -> List[PerceptualGrounding]:
        """
        Get perceptual groundings.
        
        Args:
            symbol: Filter by symbol (optional)
            modality: Filter by modality (optional)
            limit: Maximum number of results
        
        Returns:
            List of PerceptualGrounding objects
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT grounding_data FROM perceptual_groundings WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if modality:
                query += " AND modality = ?"
                params.append(modality)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            groundings = []
            for row in cursor.fetchall():
                grounding_data = json.loads(row[0])
                groundings.append(PerceptualGrounding.from_dict(grounding_data))
            
            return groundings
    
    def get_action_groundings(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[ActionGrounding]:
        """
        Get action groundings.
        
        Args:
            symbol: Filter by symbol (optional)
            limit: Maximum number of results
        
        Returns:
            List of ActionGrounding objects
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT grounding_data FROM action_groundings WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            groundings = []
            for row in cursor.fetchall():
                grounding_data = json.loads(row[0])
                groundings.append(ActionGrounding.from_dict(grounding_data))
            
            return groundings
    
    def get_multimodal_groundings(
        self,
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[MultimodalGrounding]:
        """
        Get multimodal groundings.
        
        Args:
            symbol: Filter by symbol (optional)
            limit: Maximum number of results
        
        Returns:
            List of MultimodalGrounding objects
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT grounding_data FROM multimodal_groundings WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            groundings = []
            for row in cursor.fetchall():
                grounding_data = json.loads(row[0])
                groundings.append(MultimodalGrounding.from_dict(grounding_data))
            
            return groundings
    
    def get_contextual_meanings(
        self,
        symbol: Optional[str] = None,
        context: Optional[str] = None,
        limit: int = 100
    ) -> List[ContextualMeaning]:
        """
        Get contextual meanings.
        
        Args:
            symbol: Filter by symbol (optional)
            context: Filter by context (optional)
            limit: Maximum number of results
        
        Returns:
            List of ContextualMeaning objects
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT meaning_data FROM contextual_meanings WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if context:
                query += " AND context = ?"
                params.append(context)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            
            meanings = []
            for row in cursor.fetchall():
                meaning_data = json.loads(row[0])
                meanings.append(ContextualMeaning.from_dict(meaning_data))
            
            return meanings
    
    def ground_utterance(
        self,
        utterance: str,
        context: str = "",
        modalities: List[str] = None
    ) -> Dict[str, Any]:
        """
        Ground an entire utterance to meaning.
        
        Args:
            utterance: The utterance to ground
            context: Context of the utterance
            modalities: Modalities involved
        
        Returns:
            Dictionary with grounding information
        """
        # Tokenize utterance (simple word-based for now)
        words = utterance.split()
        
        # Get groundings for each word
        word_groundings = {}
        for word in words:
            perceptual = self.get_perceptual_groundings(symbol=word, limit=5)
            actions = self.get_action_groundings(symbol=word, limit=5)
            multimodal = self.get_multimodal_groundings(symbol=word, limit=5)
            
            word_groundings[word] = {
                'perceptual': perceptual,
                'actions': actions,
                'multimodal': multimodal
            }
        
        # Create contextual meaning for the utterance
        all_grounding_ids = []
        for word_data in word_groundings.values():
            for p in word_data['perceptual']:
                all_grounding_ids.append(p.grounding_id)
            for a in word_data['actions']:
                all_grounding_ids.append(a.grounding_id)
            for m in word_data['multimodal']:
                all_grounding_ids.append(m.grounding_id)
        
        meaning = self.infer_contextual_meaning(
            symbol=utterance,
            context=context,
            grounding_ids=all_grounding_ids,
            confidence=0.7
        )
        
        return {
            'utterance': utterance,
            'context': context,
            'word_groundings': word_groundings,
            'meaning': meaning,
            'total_groundings': len(all_grounding_ids)
        }
    
    def get_grounding_summary(self) -> Dict[str, Any]:
        """
        Get summary of language grounding activity.
        
        Returns:
            Dictionary with grounding metrics
        """
        with sqlite3.connect(self.db_path) as conn:
            # Count perceptual groundings
            cursor = conn.execute("SELECT COUNT(*) FROM perceptual_groundings")
            perceptual_count = cursor.fetchone()[0]
            
            # Count by modality
            cursor = conn.execute("""
                SELECT modality, COUNT(*)
                FROM perceptual_groundings
                GROUP BY modality
            """)
            perceptual_by_modality = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Count action groundings
            cursor = conn.execute("SELECT COUNT(*) FROM action_groundings")
            action_count = cursor.fetchone()[0]
            
            # Count multimodal groundings
            cursor = conn.execute("SELECT COUNT(*) FROM multimodal_groundings")
            multimodal_count = cursor.fetchone()[0]
            
            # Count contextual meanings
            cursor = conn.execute("SELECT COUNT(*) FROM contextual_meanings")
            meaning_count = cursor.fetchone()[0]
            
            # Get unique symbols
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT symbol) FROM perceptual_groundings
            """)
            unique_perceptual_symbols = cursor.fetchone()[0]
            
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT symbol) FROM action_groundings
            """)
            unique_action_symbols = cursor.fetchone()[0]
            
            # Average confidence
            cursor = conn.execute("""
                SELECT AVG(json_extract(grounding_data, '$.confidence'))
                FROM perceptual_groundings
            """)
            avg_perceptual_confidence = cursor.fetchone()[0] or 0.0
            
            cursor = conn.execute("""
                SELECT AVG(json_extract(grounding_data, '$.confidence'))
                FROM action_groundings
            """)
            avg_action_confidence = cursor.fetchone()[0] or 0.0
            
            return {
                "total_perceptual_groundings": perceptual_count,
                "perceptual_by_modality": perceptual_by_modality,
                "total_action_groundings": action_count,
                "total_multimodal_groundings": multimodal_count,
                "total_contextual_meanings": meaning_count,
                "unique_perceptual_symbols": unique_perceptual_symbols,
                "unique_action_symbols": unique_action_symbols,
                "average_perceptual_confidence": avg_perceptual_confidence,
                "average_action_confidence": avg_action_confidence
            }
    
    def _save_perceptual_grounding(self, grounding: PerceptualGrounding) -> None:
        """Save perceptual grounding to database."""
        grounding_data = json.dumps(grounding.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO perceptual_groundings
                (grounding_id, symbol, symbol_type, modality, grounding_data, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                grounding.grounding_id,
                grounding.symbol,
                grounding.symbol_type.value,
                grounding.modality,
                grounding_data,
                grounding.timestamp
            ))
            conn.commit()
    
    def _save_action_grounding(self, grounding: ActionGrounding) -> None:
        """Save action grounding to database."""
        grounding_data = json.dumps(grounding.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO action_groundings
                (grounding_id, symbol, symbol_type, grounding_data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                grounding.grounding_id,
                grounding.symbol,
                grounding.symbol_type.value,
                grounding_data,
                grounding.timestamp
            ))
            conn.commit()
    
    def _save_multimodal_grounding(self, grounding: MultimodalGrounding) -> None:
        """Save multimodal grounding to database."""
        grounding_data = json.dumps(grounding.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO multimodal_groundings
                (grounding_id, symbol, symbol_type, grounding_data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                grounding.grounding_id,
                grounding.symbol,
                grounding.symbol_type.value,
                grounding_data,
                grounding.timestamp
            ))
            conn.commit()
    
    def _save_contextual_meaning(self, meaning: ContextualMeaning) -> None:
        """Save contextual meaning to database."""
        meaning_data = json.dumps(meaning.to_dict())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO contextual_meanings
                (meaning_id, symbol, context, meaning_data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                meaning.meaning_id,
                meaning.symbol,
                meaning.context,
                meaning_data,
                meaning.timestamp
            ))
            conn.commit()
