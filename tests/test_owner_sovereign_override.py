from unittest.mock import patch
from app.cognition.action_proposal import ActionGate,ActionProposal
from app.cognition.owner_control import AuthorizationStore,OwnerControlStore
from app.main import AuthorizationIssueRequest,issue_sovereign_authorization_endpoint

def test_exact_sovereign_grant_overrides_owner_block_but_not_pause(tmp_path):
 policy=OwnerControlStore(tmp_path/'p.json'); policy.update({'blocked_actions':['search_files']})
 grants=AuthorizationStore(); payload={'query':'owner commanded'}
 grant=grants.issue('search_files',payload,override_owner_policy=True)
 proposal=ActionProposal(action_type='search_files',payload=payload,authorization_id=grant.authorization_id)
 with patch('app.cognition.action_proposal.owner_control_store',policy),patch('app.cognition.action_proposal.authorization_store',grants),patch('app.cognition.action_proposal.HardwareMonitor.get_hardware_stats',return_value={'ram_used_percent':10}):
  assert ActionGate.evaluate_proposal(proposal).allowed is True
 policy.set_paused(True); second=grants.issue('search_files',payload,override_owner_policy=True)
 with patch('app.cognition.action_proposal.owner_control_store',policy),patch('app.cognition.action_proposal.authorization_store',grants):
  result=ActionGate.evaluate_proposal(ActionProposal(action_type='search_files',payload=payload,authorization_id=second.authorization_id))
 assert result.allowed is False and 'pause' in result.reason.lower()

def test_sovereign_endpoint_authorizes_but_does_not_execute():
 result=issue_sovereign_authorization_endpoint(AuthorizationIssueRequest(action_type='search_files',payload={'query':'owner'},ttl_seconds=60))
 assert result['authorization']['override_owner_policy'] is True
 assert result['executed'] is False

def test_normal_grant_cannot_override_owner_block(tmp_path):
 policy=OwnerControlStore(tmp_path/'p.json'); policy.update({'blocked_actions':['search_files']})
 grants=AuthorizationStore(); payload={'query':'x'}; grant=grants.issue('search_files',payload)
 with patch('app.cognition.action_proposal.owner_control_store',policy),patch('app.cognition.action_proposal.authorization_store',grants):
  result=ActionGate.evaluate_proposal(ActionProposal(action_type='search_files',payload=payload,authorization_id=grant.authorization_id))
 assert result.allowed is False
