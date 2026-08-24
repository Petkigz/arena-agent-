from unittest.mock import patch
from app.cognition.owner_control import OwnerControlStore
from app.cognition.action_proposal import ActionGate,ActionProposal

def test_sensitive_autonomy_requires_explicit_owner_switch(tmp_path):
 store=OwnerControlStore(tmp_path/'p.json');store.update({'mode':'bounded_autonomy','max_autonomous_level':3})
 assert store.get_policy().max_autonomous_level==2
 store.update({'allow_sensitive_autonomy':True,'max_autonomous_level':3})
 assert store.get_policy().max_autonomous_level==3
 proposal=ActionProposal(action_type='kill_process',payload={'pid':4242})
 with patch('app.cognition.action_proposal.owner_control_store',store),patch('app.cognition.action_proposal.HardwareMonitor.get_hardware_stats',return_value={'ram_used_percent':10}):
  result=ActionGate.evaluate_proposal(proposal)
 assert result.allowed is True

def test_disabling_switch_reclamps_ceiling(tmp_path):
 store=OwnerControlStore(tmp_path/'p.json');store.update({'allow_sensitive_autonomy':True,'max_autonomous_level':3})
 store.update({'allow_sensitive_autonomy':False})
 assert store.get_policy().max_autonomous_level==2
