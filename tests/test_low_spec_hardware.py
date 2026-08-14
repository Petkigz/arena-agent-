import pytest
from app.utils.hardware_governor import HardwareGovernor

def test_hardware_tier_detection():
    tier = HardwareGovernor.detect_hardware_tier()
    assert "tier_level" in tier
    assert "tier_name" in tier
    assert tier["allocated_max_threads"] > 0
    assert "ultra_lean_mode" in tier

def test_hardware_governor_adaptation():
    aff = HardwareGovernor.set_thread_affinity()
    assert aff["success"] is True
    assert "hardware_tier" in aff
