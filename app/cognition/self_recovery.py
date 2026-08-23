"""Advisory-only recovery plans for identity discontinuities."""
from typing import Any,Dict,List
class SelfRecoveryProtocol:
 @staticmethod
 def assess(report:Dict[str,Any], *, owner_change_evidence:List[str]|None=None)->Dict[str,Any]:
  owner_change_evidence=owner_change_evidence or []; actions=[]; causes=[]
  for issue in report.get('issues',[]):
   kind=issue.get('type')
   if owner_change_evidence: cause='owner_approved_change'
   elif kind in ('missing_interfaces','capability_count_decreased'): cause='dependency_or_hardware_loss'
   elif kind=='owner_policy_revision_rollback': cause='state_rollback_or_corruption'
   else: cause='unknown'
   causes.append({'issue':kind,'cause':cause,'confidence':.9 if owner_change_evidence else .6})
   actions.append({'issue':kind,'recommendation':'Re-probe and compare evidence; request owner approval before reinstalling, restoring, or changing policy.','execution_authorized':False})
  return {'continuous':report.get('continuous',False),'causes':causes,'recommendations':actions,
   'automatic_actions':[], 'requires_owner_authorization':bool(actions),
   'note':'Advisory recovery only; no authority, package, policy, or state is restored automatically.'}
