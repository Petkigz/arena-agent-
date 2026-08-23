from app.cognition.self_recovery import SelfRecoveryProtocol

def test_recovery_is_advisory_and_fail_closed():
 r=SelfRecoveryProtocol.assess({'continuous':False,'issues':[{'type':'capability_count_decreased'}]})
 assert r['causes'][0]['cause']=='dependency_or_hardware_loss'
 assert r['automatic_actions']==[] and r['requires_owner_authorization'] is True
 assert r['recommendations'][0]['execution_authorized'] is False

def test_owner_evidence_changes_classification_not_authority():
 r=SelfRecoveryProtocol.assess({'continuous':False,'issues':[{'type':'missing_interfaces'}]},owner_change_evidence=['owner changed camera'])
 assert r['causes'][0]['cause']=='owner_approved_change'
 assert r['automatic_actions']==[]
