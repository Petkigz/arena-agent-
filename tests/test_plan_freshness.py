from types import SimpleNamespace
from unittest.mock import patch
from app.cognition.plan_freshness import PlanFreshnessStore

def review(rev=1):return SimpleNamespace(plan_id='p1',revision=rev,goal_id='g1',snapshot_sha256='hash1',snapshot={'steps':[{'step_id':'s1','action_type':'search_files'}]})
class Registry:
 _registry={'search_files':{}}
 def get_tool_availability(self,a,probe=False):return {'status':'available'}
def runtime():return SimpleNamespace(registry=Registry(),embodied_boundary=SimpleNamespace(interfaces=lambda:[]),goal_generator=SimpleNamespace(get_goal=lambda x:SimpleNamespace(priority=SimpleNamespace(value='high'))))
def policy(revision):return SimpleNamespace(revision=revision)

def test_approved_plan_stays_fresh_until_assumption_changes(tmp_path):
 s=PlanFreshnessStore(tmp_path/'f.db');r=review();rt=runtime()
 with patch('app.cognition.owner_control.owner_control_store.get_policy',return_value=policy(2)):
  assert s.capture(r,rt).fresh is True
  assert s.validate(r,rt).fresh is True
 with patch('app.cognition.owner_control.owner_control_store.get_policy',return_value=policy(3)):
  stale=s.validate(r,rt)
 assert stale.fresh is False
 assert any(x['field']=='owner_policy_revision' for x in stale.changes)

def test_missing_baseline_fails_closed(tmp_path):
 s=PlanFreshnessStore(tmp_path/'f.db')
 with patch('app.cognition.owner_control.owner_control_store.get_policy',return_value=policy(1)):
  stale=s.validate(review(),runtime())
 assert stale.fresh is False and stale.changes[0]['field']=='baseline'
