from types import SimpleNamespace
from unittest.mock import patch
from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator,AutonomousGoal,GoalStatus,GoalPriority,GoalSource
from app.main import OwnerAutonomousGoalRequest,create_owner_autonomous_goal_endpoint

def test_owner_controls_goal_queue_without_authorizing_actions(tmp_path):
 g=AutonomousGoalGenerator(str(tmp_path/'goals.db')); goal=AutonomousGoal(title='Inspect reports',description='Find gaps')
 g.add_goal(goal); decided=g.owner_decide_goal(goal.goal_id,True)
 assert decided.status==GoalStatus.APPROVED
 assert decided.requires_owner_approval is True
 assert g.get_next_goal().goal_id==goal.goal_id

def test_owner_directive_api_creates_planning_goal_not_action_authority(tmp_path):
 g=AutonomousGoalGenerator(str(tmp_path/'goals.db'))
 with patch('app.cognition.runtime.CognitiveRuntime.get_instance',return_value=SimpleNamespace(goal_generator=g)):
  result=create_owner_autonomous_goal_endpoint(OwnerAutonomousGoalRequest(title='Do owner task',priority='critical'))
 assert result['goal']['source']==GoalSource.OWNER_DIRECTIVE.value
 assert result['goal']['status']=='approved'
 assert result['execution_authorized'] is False

def test_owner_can_defer_and_later_reapprove_planning(tmp_path):
 g=AutonomousGoalGenerator(str(tmp_path/'goals.db'));goal=AutonomousGoal(title='Later');g.add_goal(goal);g.owner_decide_goal(goal.goal_id,True)
 assert g.owner_defer_goal(goal.goal_id).status==GoalStatus.DEFERRED
 assert g.owner_decide_goal(goal.goal_id,True).status==GoalStatus.APPROVED

def test_owner_priority_preempts_higher_scored_goal(tmp_path):
 g=AutonomousGoalGenerator(str(tmp_path/'goals.db')); a=AutonomousGoal(title='A',overall_score=.1); b=AutonomousGoal(title='B',overall_score=.9)
 g.add_goal(a); g.add_goal(b)
 assert g.owner_set_priority(a.goal_id,'critical').priority==GoalPriority.CRITICAL
 assert g.owner_decide_goal(a.goal_id,True).status==GoalStatus.APPROVED
 assert g.owner_decide_goal(b.goal_id,True).status==GoalStatus.APPROVED
 assert g.get_next_goal().goal_id==a.goal_id
