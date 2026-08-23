from app.cognition.identity_continuity import IdentityContinuityLedger

def state(**kw):
 d={"claim_predicates":["authority.owner_policy","hardware.profile"],"active_commitment_sources":["project:p1"],"interface_ids":["desktop_screen","desktop_pointer"],"tool_count":133,"owner_policy_revision":4}; d.update(kw); return d

def test_expected_restart_preserves_functional_continuity(tmp_path):
 l=IdentityContinuityLedger(tmp_path/'id.db')
 assert l.checkpoint(state(),'boot-1')['previous_exists'] is False
 report=l.checkpoint(state(),'boot-2')
 assert report['continuous'] is True
 assert 'not persistence of consciousness' in report['note']

def test_missing_capability_and_policy_rollback_are_detected(tmp_path):
 l=IdentityContinuityLedger(tmp_path/'id.db'); l.checkpoint(state(),'boot-1')
 report=l.checkpoint(state(claim_predicates=['authority.owner_policy'],interface_ids=['desktop_screen'],tool_count=120,owner_policy_revision=2),'boot-2')
 kinds={x['type'] for x in report['issues']}
 assert report['continuous'] is False
 assert {'missing_self_claims','missing_interfaces','capability_count_decreased','owner_policy_revision_rollback'} <= kinds
