"""Tests for Phase 4: Verified Reflection System."""

import pytest
from app.cognition.verified_reflection import (
    VerifiedReflection,
    VerifiedReflectionStore,
    VerificationMethod,
    VerificationRecord,
    VERIFICATION_WEIGHTS,
)


class TestVerificationRecord:
    """Tests for VerificationRecord."""
    
    def test_create_record(self):
        """Test creating a verification record."""
        record = VerificationRecord(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.9,
        )
        assert record.method == VerificationMethod.DIRECT_OBSERVATION
        assert record.confidence == 0.9
        assert record.evidence_id is None
    
    def test_weighted_confidence(self):
        """Test weighted confidence calculation."""
        record = VerificationRecord(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.8,
        )
        expected = 0.8 * VERIFICATION_WEIGHTS[VerificationMethod.DIRECT_OBSERVATION]
        assert record.weighted_confidence() == expected
    
    def test_invalid_confidence(self):
        """Test that invalid confidence raises ValueError."""
        with pytest.raises(ValueError, match="confidence must be between 0 and 1"):
            VerificationRecord(
                method=VerificationMethod.DIRECT_OBSERVATION,
                confidence=1.5,
            )


class TestVerifiedReflection:
    """Tests for VerifiedReflection."""
    
    def test_create_reflection(self):
        """Test creating a verified reflection."""
        reflection = VerifiedReflection(content="Test reflection")
        assert reflection.content == "Test reflection"
        assert len(reflection.verifications) == 0
        assert reflection.confidence() == 0.0
    
    def test_add_verification(self):
        """Test adding a verification."""
        reflection = VerifiedReflection(content="Test")
        record = reflection.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.9,
        )
        assert len(reflection.verifications) == 1
        assert record.method == VerificationMethod.DIRECT_OBSERVATION
    
    def test_verification_quality_single(self):
        """Test verification quality with single verification."""
        reflection = VerifiedReflection(content="Test")
        reflection.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=1.0,
        )
        quality = reflection.verification_quality()
        assert quality == 1.0  # Best method with full confidence
    
    def test_verification_quality_multiple(self):
        """Test verification quality with multiple verifications."""
        reflection = VerifiedReflection(content="Test")
        reflection.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.9,
        )
        reflection.add_verification(
            method=VerificationMethod.EXECUTION_RESULT,
            confidence=0.85,
        )
        quality = reflection.verification_quality()
        # Should be close to 1.0 (best method + diversity bonus)
        assert quality > 0.9
    
    def test_verification_quality_unverified(self):
        """Test verification quality with unverified method."""
        reflection = VerifiedReflection(content="Test")
        reflection.add_verification(
            method=VerificationMethod.UNVERIFIED,
            confidence=1.0,
        )
        quality = reflection.verification_quality()
        assert quality == 0.1  # Lowest weight
    
    def test_is_verified(self):
        """Test is_verified threshold check."""
        reflection = VerifiedReflection(content="Test")
        assert not reflection.is_verified()
        
        reflection.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.9,
        )
        assert reflection.is_verified()
    
    def test_primary_verification_method(self):
        """Test getting primary verification method."""
        reflection = VerifiedReflection(content="Test")
        assert reflection.primary_verification_method() is None
        
        reflection.add_verification(
            method=VerificationMethod.SELF_REPORTED,
            confidence=0.9,
        )
        reflection.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.8,
        )
        # Should return DIRECT_OBSERVATION (higher weight)
        assert reflection.primary_verification_method() == VerificationMethod.DIRECT_OBSERVATION
    
    def test_verification_summary(self):
        """Test verification summary."""
        reflection = VerifiedReflection(content="Test")
        summary = reflection.verification_summary()
        assert summary["verified"] is False
        assert summary["quality"] == 0.0
        assert summary["count"] == 0
        
        reflection.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.9,
        )
        summary = reflection.verification_summary()
        assert summary["verified"] is True
        assert summary["quality"] > 0.8
        assert summary["count"] == 1
        assert "direct_observation" in summary["methods"]
    
    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        reflection = VerifiedReflection(
            content="Test reflection",
            tags=["test", "example"],
        )
        reflection.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            evidence_id="ev_123",
            confidence=0.95,
            details="Direct system probe",
        )
        
        data = reflection.to_dict()
        restored = VerifiedReflection.from_dict(data)
        
        assert restored.content == reflection.content
        assert restored.reflection_id == reflection.reflection_id
        assert len(restored.verifications) == len(reflection.verifications)
        assert restored.tags == reflection.tags
        
        orig_verif = reflection.verifications[0]
        rest_verif = restored.verifications[0]
        assert rest_verif.method == orig_verif.method
        assert rest_verif.evidence_id == orig_verif.evidence_id
        assert rest_verif.confidence == orig_verif.confidence


class TestVerifiedReflectionStore:
    """Tests for VerifiedReflectionStore."""
    
    def test_store_and_retrieve(self):
        """Test storing and retrieving a reflection."""
        store = VerifiedReflectionStore(":memory:")
        
        reflection = VerifiedReflection(content="Test reflection")
        reflection.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.9,
        )
        
        store.store(reflection)
        retrieved = store.get(reflection.reflection_id)
        
        assert retrieved is not None
        assert retrieved.content == reflection.content
        assert len(retrieved.verifications) == 1
        store.close()
    
    def test_query_by_quality(self):
        """Test querying reflections by quality threshold."""
        store = VerifiedReflectionStore(":memory:")
        
        # High quality reflection
        high = VerifiedReflection(content="High quality")
        high.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.95,
        )
        store.store(high)
        
        # Low quality reflection
        low = VerifiedReflection(content="Low quality")
        low.add_verification(
            method=VerificationMethod.UNVERIFIED,
            confidence=0.5,
        )
        store.store(low)
        
        # Query high quality only
        results = store.query(min_quality=0.5)
        assert len(results) == 1
        assert results[0].content == "High quality"
        
        # Query all
        results = store.query(min_quality=0.0)
        assert len(results) == 2
        store.close()
    
    def test_query_by_tags(self):
        """Test querying reflections by tags."""
        store = VerifiedReflectionStore(":memory:")
        
        r1 = VerifiedReflection(content="Tagged 1", tags=["python", "test"])
        r1.add_verification(method=VerificationMethod.DIRECT_OBSERVATION, confidence=0.9)
        store.store(r1)
        
        r2 = VerifiedReflection(content="Tagged 2", tags=["javascript"])
        r2.add_verification(method=VerificationMethod.DIRECT_OBSERVATION, confidence=0.9)
        store.store(r2)
        
        # Query by tag
        results = store.query(tags=["python"])
        assert len(results) == 1
        assert results[0].content == "Tagged 1"
        store.close()
    
    def test_count(self):
        """Test counting reflections."""
        store = VerifiedReflectionStore(":memory:")
        
        r1 = VerifiedReflection(content="High")
        r1.add_verification(method=VerificationMethod.DIRECT_OBSERVATION, confidence=0.9)
        store.store(r1)
        
        r2 = VerifiedReflection(content="Low")
        r2.add_verification(method=VerificationMethod.UNVERIFIED, confidence=0.5)
        store.store(r2)
        
        assert store.count(min_quality=0.0) == 2
        assert store.count(min_quality=0.5) == 1
        store.close()
    
    def test_update_reflection(self):
        """Test updating an existing reflection."""
        store = VerifiedReflectionStore(":memory:")
        
        reflection = VerifiedReflection(content="Original")
        reflection.add_verification(method=VerificationMethod.SELF_REPORTED, confidence=0.5)
        store.store(reflection)
        
        # Update with better verification
        reflection.add_verification(
            method=VerificationMethod.DIRECT_OBSERVATION,
            confidence=0.95,
        )
        store.store(reflection)
        
        retrieved = store.get(reflection.reflection_id)
        assert retrieved is not None
        assert len(retrieved.verifications) == 2
        assert retrieved.verification_quality() > 0.9
        store.close()
