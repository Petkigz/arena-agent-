from types import SimpleNamespace
from unittest.mock import patch
from app.utils.hardware_governor import HardwareGovernor
from app.runtime.resource_manager import ResourceManager

def test_48gb_cpu_host_gets_high_memory_tier_without_cuda():
 ram=SimpleNamespace(total=48*1024**3)
 with patch('app.utils.hardware_governor.psutil.cpu_count',return_value=32),patch('app.utils.hardware_governor.psutil.virtual_memory',return_value=ram),patch.dict('sys.modules',{'torch':None}):
  tier=HardwareGovernor.detect_hardware_tier()
 assert tier['tier_level']==1
 assert tier['max_context_budget_tokens']==8192
 assert tier['background_daemon_enabled'] is True

def test_resource_manager_uses_detected_ram_not_16gb_constant():
 memory=SimpleNamespace(total=48*1024**3,percent=10,available=40*1024**3)
 with patch('app.runtime.resource_manager.psutil.virtual_memory',return_value=memory):
  manager=ResourceManager()
 assert 47 < manager.ram_limit_gb < 49
