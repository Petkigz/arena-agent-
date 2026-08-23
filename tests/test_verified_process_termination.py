from unittest.mock import Mock,patch
import psutil
from app.tools.process_manager import ProcessManager
from app.cognition.execution_control import ExecutionControlRegistry

def proc():
 p=Mock();p.create_time.return_value=100.5;p.exe.return_value='/bin/editor';p.name.return_value='editor';p.username.return_value='owner';p.wait.return_value=0;return p

def test_exact_process_identity_is_verified_before_and_after(tmp_path):
 p=proc();priv=Mock(is_elevated=False)
 with patch('app.tools.process_manager.psutil.Process',side_effect=[p,psutil.NoSuchProcess(42)]),patch('app.tools.process_manager.getpass.getuser',return_value='owner'),patch('app.cognition.privilege_model.PrivilegeModel.probe',return_value=priv):
  r=ProcessManager.terminate_verified(42,100.5,'/bin/editor')
 assert r['success'] is True and r['environment_verified'] is True
 p.terminate.assert_called_once();assert r['rollback_supported'] is False
 reg=ExecutionControlRegistry(tmp_path/'e.db');record=reg.begin('p','terminate_process_verified');receipt=reg.create_rollback_receipt(record.execution_id,'terminate_process_verified',{},r)
 assert receipt.supported is False and 'cannot be restored' in receipt.reason

def test_pid_reuse_or_executable_drift_blocks_termination():
 p=proc();p.create_time.return_value=200
 with patch('app.tools.process_manager.psutil.Process',return_value=p):
  r=ProcessManager.terminate_verified(42,100.5,'/bin/editor')
 assert r['success'] is False and 'PID instance changed' in r['error'];p.terminate.assert_not_called()
 p=proc()
 with patch('app.tools.process_manager.psutil.Process',return_value=p):
  r=ProcessManager.terminate_verified(42,100.5,'/other')
 assert r['success'] is False and 'Executable path' in r['error']
