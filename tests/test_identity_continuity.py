from app.cognition.identity_continuity import IdentityContinuityLedger

def state(**kw):
 d={"claim_predicates":["authority.owner_policy","hardware.profile"],"active_commitment_sources":["project:p1"],"interface_ids":["desktop_screen","desktop_pointer"],"tool_count":133,"owner_policy_revision":4}; d.update(kw); return d

def test_expected_restart_preserves_functional_continuity(tmp_path):
 l=IdentityContinuityLedger(tmp_path/'id.db')
 assert l.checkpoint(state(),'boot-1')['previous_exists'] is False
 report=l.checkpoint(state(),'boot-2')
 assert report['continuous'] is True
 assert 'not persistence of consciousness' in report['note']

def test_claim_commitment_interface_and_provider_changes_are_detected(tmp_path):
 l=IdentityContinuityLedger(tmp_path/'id.db')
 before=state(claim_digests={'hardware.profile':'a'},interface_availability={'desktop_screen':True},provider_model='model-a')
 l.checkpoint(before,'boot-1')
 after=state(claim_digests={'hardware.profile':'b'},active_commitment_sources=[],interface_availability={'desktop_screen':False},provider_model='model-b')
 report=l.checkpoint(after,'boot-2');kinds={x['type'] for x in report['issues']}
 assert {'changed_self_claim_values','missing_active_commitments','interface_availability_changed','provider_model_changed'}<=kinds

def test_owner_expected_change_is_recorded_without_false_discontinuity(tmp_path):
 from app.cognition.owner_decisions import OwnerDecisionStore
 decisions=OwnerDecisionStore(tmp_path/'od.db')
 l=IdentityContinuityLedger(tmp_path/'id.db',owner_decisions=decisions);l.checkpoint(state(owner_policy_revision=3),'boot-1')
 decision=decisions.issue('expected_identity_change',{'expected_change_types':['owner_policy_revision_rollback']},note='owner lowered the ceiling')
 report=l.checkpoint(state(owner_policy_revision=2),'boot-2',expected_change_types=['owner_policy_revision_rollback'],owner_decision_id=decision.decision_id)
 assert report['continuous'] is True and report['issues']==[]
 assert report['expected_changes'][0]['type']=='owner_policy_revision_rollback'
 assert report['state_changed'] is True
 assert report['owner_decision_id']==decision.decision_id

def test_missing_capability_and_policy_rollback_are_detected(tmp_path):
 l=IdentityContinuityLedger(tmp_path/'id.db'); l.checkpoint(state(),'boot-1')
 report=l.checkpoint(state(claim_predicates=['authority.owner_policy'],interface_ids=['desktop_screen'],tool_count=120,owner_policy_revision=2),'boot-2')
 kinds={x['type'] for x in report['issues']}
 assert report['continuous'] is False
 assert {'missing_self_claims','missing_interfaces','capability_count_decreased','owner_policy_revision_rollback'} <= kinds
