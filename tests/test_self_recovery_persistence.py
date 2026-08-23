from app.cognition.self_recovery import SelfRecoveryStore

def report(): return {'checkpoint_id':'identity-1','continuous':False,'issues':[{'type':'capability_count_decreased'}]}
def test_recovery_persists_and_decision_is_final(tmp_path):
 p=tmp_path/'r.db'; s=SelfRecoveryStore(p); item=s.save(report()); restored=SelfRecoveryStore(p).list()[0]
 assert restored.assessment_id==item.assessment_id and restored.status=='pending'
 decided=s.decide(item.assessment_id,'acknowledged','reviewed')
 assert decided.status=='acknowledged'
 try: s.decide(item.assessment_id,'dismissed'); assert False
 except ValueError: pass

def test_action_request_does_not_execute(tmp_path):
 s=SelfRecoveryStore(tmp_path/'r.db'); item=s.save(report()); marked=s.mark_action_requested(item.assessment_id,'approval:a1')
 assert marked.status=='action_requested'
 assert marked.report['automatic_actions']==[]
 assert all(not r['execution_authorized'] for r in marked.report['recommendations'])
