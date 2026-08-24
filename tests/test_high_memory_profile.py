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

def test_high_memory_self_model_exposes_wired_memory_capacity():
 tier={'cpu_threads':32,'total_ram_gb':48.0,'gpu_available':False,'tier_name':'TIER 1','ultra_lean_mode':False}
 live={'ram_total_gb':48.0,'ram_percent':10,'cpu_percent':5,'disk_percent':20,'disk_free_gb':100}
 with patch.object(HardwareGovernor,'detect_hardware_tier',return_value=tier),patch.object(HardwareGovernor,'_detect_cpu_model',return_value='cpu'),patch.object(HardwareGovernor,'_detect_gpu_model',return_value='gpu'),patch('app.utils.hardware_governor.HardwareMonitor.get_hardware_stats',return_value=live):
  model=HardwareGovernor.build_self_model()
 assert model['memory_consolidation_batch']==500 and model['memory_record_cap']==20000
 assert model['recommended_parallel_cpu_tasks']==6

def test_resource_manager_uses_detected_ram_not_16gb_constant():
 memory=SimpleNamespace(total=48*1024**3,percent=10,available=40*1024**3)
 with patch('app.runtime.resource_manager.psutil.virtual_memory',return_value=memory):
  manager=ResourceManager()
 assert 47 < manager.ram_limit_gb < 49
