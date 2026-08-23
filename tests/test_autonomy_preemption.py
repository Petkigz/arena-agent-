from app.cognition.autonomy_preemption import AutonomyPreemptionStore

def test_preemption_requires_observation_before_resume(tmp_path):
 s=AutonomyPreemptionStore(tmp_path/'p.db'); x=s.create('exec1','urgent',plan_id='plan1')
 pending=s.refresh(x.preemption_id,{'status':'running','cancellation_observed':False})
 assert pending.status=='cancellation_requested'
 try:s.request_resume(x.preemption_id);assert False
 except ValueError:pass
 ready=s.refresh(x.preemption_id,{'status':'cancelled','cancellation_observed':True})
 assert ready.status=='resume_ready' and ready.side_effect_state=='partial_or_unknown'
 resumed=s.request_resume(x.preemption_id)
 assert resumed.status=='resume_requested' and resumed.requires_observation_reconciliation is True

def test_late_cancel_blocks_resume(tmp_path):
 s=AutonomyPreemptionStore(tmp_path/'p.db');x=s.create('exec1','urgent',plan_id='plan1')
 x=s.refresh(x.preemption_id,{'status':'completed_after_cancel_request','cancellation_observed':False})
 assert x.status=='resume_blocked' and 'side_effects' in x.side_effect_state
 assert s.list()[0].preemption_id==x.preemption_id
