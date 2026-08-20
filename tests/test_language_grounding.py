"""
Tests for Phase 22: Language Grounding
"""

import pytest
import tempfile
import os
from app.cognition.language_grounding import (
    LanguageGroundingEngine,
    PerceptualGrounding,
    ActionGrounding,
    MultimodalGrounding,
    ContextualMeaning,
    SymbolType
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def engine(temp_db):
    """Create a language grounding engine with temp database."""
    return LanguageGroundingEngine(db_path=temp_db)


class TestLanguageGrounding:
    """Test suite for language grounding functionality."""
    
    def test_create_perceptual_grounding(self, engine):
        """Test creating a perceptual grounding."""
        grounding = engine.create_perceptual_grounding(
            symbol="red",
            modality="vision",
            perceptual_features={
                "hue": 0.0,
                "saturation": 1.0,
                "brightness": 1.0
            },
            sensory_experience="Bright red color perception",
            symbol_type=SymbolType.WORD,
            confidence=0.9,
            examples=["red apple", "red car", "red light"]
        )
        
        assert grounding.grounding_id is not None
        assert grounding.symbol == "red"
        assert grounding.modality == "vision"
        assert grounding.perceptual_features["hue"] == 0.0
        assert grounding.sensory_experience == "Bright red color perception"
        assert grounding.confidence == 0.9
        assert len(grounding.examples) == 3
    
    def test_create_action_grounding(self, engine):
        """Test creating an action grounding."""
        grounding = engine.create_action_grounding(
            symbol="grasp",
            associated_actions=["reach", "close_hand", "lift"],
            affordances=["pick_up", "hold", "manipulate"],
            motor_programs=[
                {"action": "reach", "duration": 500},
                {"action": "close_hand", "duration": 200},
                {"action": "lift", "duration": 300}
            ],
            action_outcomes=["object_held", "object_moved"],
            symbol_type=SymbolType.WORD,
            confidence=0.85
        )
        
        assert grounding.grounding_id is not None
        assert grounding.symbol == "grasp"
        assert len(grounding.associated_actions) == 3
        assert len(grounding.affordances) == 3
        assert len(grounding.motor_programs) == 3
        assert len(grounding.action_outcomes) == 2
        assert grounding.confidence == 0.85
    
    def test_create_multimodal_grounding(self, engine):
        """Test creating a multimodal grounding."""
        # First create perceptual and action groundings
        perceptual = engine.create_perceptual_grounding(
            symbol="cup",
            modality="vision",
            perceptual_features={"shape": "cylindrical", "size": "medium"},
            sensory_experience="Visual perception of a cup"
        )
        
        action = engine.create_action_grounding(
            symbol="cup",
            associated_actions=["grasp", "lift", "drink"],
            affordances=["hold_liquid", "drink_from"],
            confidence=0.8
        )
        
        # Create multimodal grounding
        multimodal = engine.create_multimodal_grounding(
            symbol="cup",
            modalities=["vision", "motor", "tactile"],
            perceptual_groundings=[perceptual.grounding_id],
            action_groundings=[action.grounding_id],
            integration_weights={
                "vision": 0.4,
                "motor": 0.4,
                "tactile": 0.2
            },
            symbol_type=SymbolType.WORD,
            confidence=0.9
        )
        
        assert multimodal.grounding_id is not None
        assert multimodal.symbol == "cup"
        assert len(multimodal.modalities) == 3
        assert len(multimodal.perceptual_groundings) == 1
        assert len(multimodal.action_groundings) == 1
        assert multimodal.integration_weights["vision"] == 0.4
        assert multimodal.confidence == 0.9
    
    def test_infer_contextual_meaning(self, engine):
        """Test inferring contextual meaning."""
        # Create some groundings
        grounding1 = engine.create_perceptual_grounding(
            symbol="bank",
            modality="vision",
            perceptual_features={"building": True},
            sensory_experience="Financial institution building"
        )
        
        grounding2 = engine.create_perceptual_grounding(
            symbol="bank",
            modality="vision",
            perceptual_features={"river": True},
            sensory_experience="River edge"
        )
        
        # Infer meaning in financial context
        meaning = engine.infer_contextual_meaning(
            symbol="bank",
            context="I need to deposit money at the bank",
            grounding_ids=[grounding1.grounding_id],
            pragmatic_inferences=[
                "Refers to financial institution",
                "Not river bank"
            ],
            confidence=0.95
        )
        
        assert meaning.meaning_id is not None
        assert meaning.symbol == "bank"
        assert meaning.context == "I need to deposit money at the bank"
        assert "financial" in meaning.intended_meaning.lower() or "symbol" in meaning.intended_meaning.lower()
        assert len(meaning.pragmatic_inferences) == 2
        assert meaning.confidence == 0.95
    
    def test_get_perceptual_groundings(self, engine):
        """Test getting perceptual groundings."""
        # Create multiple groundings
        engine.create_perceptual_grounding(
            symbol="red",
            modality="vision",
            perceptual_features={"hue": 0.0},
            sensory_experience="Red color"
        )
        
        engine.create_perceptual_grounding(
            symbol="blue",
            modality="vision",
            perceptual_features={"hue": 0.67},
            sensory_experience="Blue color"
        )
        
        engine.create_perceptual_grounding(
            symbol="loud",
            modality="auditory",
            perceptual_features={"volume": 0.9},
            sensory_experience="Loud sound"
        )
        
        # Get all groundings
        all_groundings = engine.get_perceptual_groundings(limit=10)
        assert len(all_groundings) == 3
        
        # Filter by symbol
        red_groundings = engine.get_perceptual_groundings(symbol="red")
        assert len(red_groundings) == 1
        assert red_groundings[0].symbol == "red"
        
        # Filter by modality
        vision_groundings = engine.get_perceptual_groundings(modality="vision")
        assert len(vision_groundings) == 2
        
        # Limit results
        limited = engine.get_perceptual_groundings(limit=2)
        assert len(limited) == 2
    
    def test_get_action_groundings(self, engine):
        """Test getting action groundings."""
        # Create multiple groundings
        engine.create_action_grounding(
            symbol="grasp",
            associated_actions=["reach", "close"],
            affordances=["pick_up"]
        )
        
        engine.create_action_grounding(
            symbol="push",
            associated_actions=["extend_arm", "apply_force"],
            affordances=["move_away"]
        )
        
        engine.create_action_grounding(
            symbol="pull",
            associated_actions=["grasp", "retract"],
            affordances=["move_toward"]
        )
        
        # Get all groundings
        all_groundings = engine.get_action_groundings(limit=10)
        assert len(all_groundings) == 3
        
        # Filter by symbol
        grasp_groundings = engine.get_action_groundings(symbol="grasp")
        assert len(grasp_groundings) == 1
        assert grasp_groundings[0].symbol == "grasp"
        
        # Limit results
        limited = engine.get_action_groundings(limit=2)
        assert len(limited) == 2
    
    def test_get_multimodal_groundings(self, engine):
        """Test getting multimodal groundings."""
        # Create multimodal groundings
        engine.create_multimodal_grounding(
            symbol="cup",
            modalities=["vision", "motor"],
            confidence=0.9
        )
        
        engine.create_multimodal_grounding(
            symbol="ball",
            modalities=["vision", "motor", "tactile"],
            confidence=0.85
        )
        
        # Get all groundings
        all_groundings = engine.get_multimodal_groundings(limit=10)
        assert len(all_groundings) == 2
        
        # Filter by symbol
        cup_groundings = engine.get_multimodal_groundings(symbol="cup")
        assert len(cup_groundings) == 1
        assert cup_groundings[0].symbol == "cup"
    
    def test_get_contextual_meanings(self, engine):
        """Test getting contextual meanings."""
        # Create contextual meanings
        engine.infer_contextual_meaning(
            symbol="bank",
            context="financial",
            grounding_ids=[],
            confidence=0.9
        )
        
        engine.infer_contextual_meaning(
            symbol="bank",
            context="river",
            grounding_ids=[],
            confidence=0.85
        )
        
        engine.infer_contextual_meaning(
            symbol="chair",
            context="furniture",
            grounding_ids=[],
            confidence=0.95
        )
        
        # Get all meanings
        all_meanings = engine.get_contextual_meanings(limit=10)
        assert len(all_meanings) == 3
        
        # Filter by symbol
        bank_meanings = engine.get_contextual_meanings(symbol="bank")
        assert len(bank_meanings) == 2
        
        # Filter by context
        financial_meanings = engine.get_contextual_meanings(context="financial")
        assert len(financial_meanings) == 1
        assert financial_meanings[0].symbol == "bank"
    
    def test_ground_utterance(self, engine):
        """Test grounding an entire utterance."""
        # Create groundings for words
        engine.create_perceptual_grounding(
            symbol="red",
            modality="vision",
            perceptual_features={"hue": 0.0},
            sensory_experience="Red color"
        )
        
        engine.create_action_grounding(
            symbol="grasp",
            associated_actions=["reach", "close"],
            affordances=["pick_up"]
        )
        
        engine.create_perceptual_grounding(
            symbol="cup",
            modality="vision",
            perceptual_features={"shape": "cylindrical"},
            sensory_experience="Cup shape"
        )
        
        # Ground an utterance
        result = engine.ground_utterance(
            utterance="grasp the red cup",
            context="kitchen task",
            modalities=["vision", "motor"]
        )
        
        assert result['utterance'] == "grasp the red cup"
        assert result['context'] == "kitchen task"
        assert 'word_groundings' in result
        assert 'meaning' in result
        assert result['total_groundings'] > 0
        
        # Check word groundings
        assert 'grasp' in result['word_groundings']
        assert 'red' in result['word_groundings']
        assert 'cup' in result['word_groundings']
        
        # Check that grasp has action groundings
        assert len(result['word_groundings']['grasp']['actions']) > 0
        
        # Check that red has perceptual groundings
        assert len(result['word_groundings']['red']['perceptual']) > 0
    
    def test_get_grounding_summary(self, engine):
        """Test getting grounding summary."""
        # Create various groundings
        engine.create_perceptual_grounding(
            symbol="red",
            modality="vision",
            perceptual_features={},
            sensory_experience="Red",
            confidence=0.9
        )
        
        engine.create_perceptual_grounding(
            symbol="blue",
            modality="vision",
            perceptual_features={},
            sensory_experience="Blue",
            confidence=0.85
        )
        
        engine.create_perceptual_grounding(
            symbol="loud",
            modality="auditory",
            perceptual_features={},
            sensory_experience="Loud",
            confidence=0.8
        )
        
        engine.create_action_grounding(
            symbol="grasp",
            associated_actions=["reach"],
            affordances=["pick_up"],
            confidence=0.9
        )
        
        engine.create_action_grounding(
            symbol="push",
            associated_actions=["extend"],
            affordances=["move"],
            confidence=0.85
        )
        
        engine.create_multimodal_grounding(
            symbol="cup",
            modalities=["vision", "motor"],
            confidence=0.9
        )
        
        engine.infer_contextual_meaning(
            symbol="bank",
            context="financial",
            confidence=0.95
        )
        
        # Get summary
        summary = engine.get_grounding_summary()
        
        assert summary["total_perceptual_groundings"] == 3
        assert summary["perceptual_by_modality"]["vision"] == 2
        assert summary["perceptual_by_modality"]["auditory"] == 1
        assert summary["total_action_groundings"] == 2
        assert summary["total_multimodal_groundings"] == 1
        assert summary["total_contextual_meanings"] == 1
        assert summary["unique_perceptual_symbols"] == 3
        assert summary["unique_action_symbols"] == 2
        assert summary["average_perceptual_confidence"] > 0.8
        assert summary["average_action_confidence"] > 0.8
    
    def test_perceptual_grounding_serialization(self):
        """Test perceptual grounding serialization."""
        grounding = PerceptualGrounding(
            grounding_id="ground123",
            symbol="red",
            symbol_type=SymbolType.WORD,
            modality="vision",
            perceptual_features={"hue": 0.0, "saturation": 1.0},
            sensory_experience="Bright red",
            confidence=0.9,
            examples=["red apple", "red car"]
        )
        
        # Serialize
        grounding_dict = grounding.to_dict()
        
        # Deserialize
        restored = PerceptualGrounding.from_dict(grounding_dict)
        
        assert restored.grounding_id == grounding.grounding_id
        assert restored.symbol == grounding.symbol
        assert restored.symbol_type == grounding.symbol_type
        assert restored.modality == grounding.modality
        assert restored.perceptual_features == grounding.perceptual_features
        assert restored.sensory_experience == grounding.sensory_experience
        assert restored.confidence == grounding.confidence
        assert restored.examples == grounding.examples
    
    def test_action_grounding_serialization(self):
        """Test action grounding serialization."""
        grounding = ActionGrounding(
            grounding_id="action123",
            symbol="grasp",
            symbol_type=SymbolType.WORD,
            associated_actions=["reach", "close"],
            affordances=["pick_up", "hold"],
            motor_programs=[{"action": "reach", "duration": 500}],
            action_outcomes=["object_held"],
            confidence=0.85
        )
        
        # Serialize
        grounding_dict = grounding.to_dict()
        
        # Deserialize
        restored = ActionGrounding.from_dict(grounding_dict)
        
        assert restored.grounding_id == grounding.grounding_id
        assert restored.symbol == grounding.symbol
        assert restored.symbol_type == grounding.symbol_type
        assert restored.associated_actions == grounding.associated_actions
        assert restored.affordances == grounding.affordances
        assert restored.motor_programs == grounding.motor_programs
        assert restored.action_outcomes == grounding.action_outcomes
        assert restored.confidence == grounding.confidence
    
    def test_multimodal_grounding_serialization(self):
        """Test multimodal grounding serialization."""
        grounding = MultimodalGrounding(
            grounding_id="multi123",
            symbol="cup",
            symbol_type=SymbolType.WORD,
            modalities=["vision", "motor"],
            perceptual_groundings=["ground1", "ground2"],
            action_groundings=["action1"],
            integration_weights={"vision": 0.6, "motor": 0.4},
            confidence=0.9
        )
        
        # Serialize
        grounding_dict = grounding.to_dict()
        
        # Deserialize
        restored = MultimodalGrounding.from_dict(grounding_dict)
        
        assert restored.grounding_id == grounding.grounding_id
        assert restored.symbol == grounding.symbol
        assert restored.symbol_type == grounding.symbol_type
        assert restored.modalities == grounding.modalities
        assert restored.perceptual_groundings == grounding.perceptual_groundings
        assert restored.action_groundings == grounding.action_groundings
        assert restored.integration_weights == grounding.integration_weights
        assert restored.confidence == grounding.confidence
    
    def test_contextual_meaning_serialization(self):
        """Test contextual meaning serialization."""
        meaning = ContextualMeaning(
            meaning_id="meaning123",
            symbol="bank",
            context="financial",
            intended_meaning="Financial institution",
            pragmatic_inferences=["Not river bank", "Place for money"],
            grounding_ids=["ground1", "ground2"],
            confidence=0.95
        )
        
        # Serialize
        meaning_dict = meaning.to_dict()
        
        # Deserialize
        restored = ContextualMeaning.from_dict(meaning_dict)
        
        assert restored.meaning_id == meaning.meaning_id
        assert restored.symbol == meaning.symbol
        assert restored.context == meaning.context
        assert restored.intended_meaning == meaning.intended_meaning
        assert restored.pragmatic_inferences == meaning.pragmatic_inferences
        assert restored.grounding_ids == meaning.grounding_ids
        assert restored.confidence == meaning.confidence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
