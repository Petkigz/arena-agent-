import pytest
from app.utils.hardware_governor import HardwareGovernor
from app.tools.security_canary import SecurityCanaryTrap

def test_hardware_governor():
    aff = HardwareGovernor.set_thread_affinity(p_cores_only=True)
    assert aff["success"] is True

    mem = HardwareGovernor.purge_vram_and_system_memory()
    assert mem["success"] is True
    assert mem["free_system_ram_gb"] > 0

def test_security_canary_trap():
    canary = SecurityCanaryTrap.spawn_canary_honeypots()
    assert canary["success"] is True
    assert canary["canary_files_count"] == 2

    entropy = SecurityCanaryTrap.calculate_entropy("decoy_canary_key_token_992184128941248")
    assert entropy > 3.0

    clip = SecurityCanaryTrap.inspect_clipboard_entropy()
    assert "success" in clip
