from app.cognition.autonomy_allocator import AutonomyResourceAllocator
from app.cognition.autonomous_goal_generator import AutonomousGoalGenerator,AutonomousGoal,GoalPriority,GoalStatus,GoalSource

def approved(title,priority,score,effort='unknown',deps=None,source=GoalSource.CURIOSITY):
 g=AutonomousGoal(title=title,priority=priority,overall_score=score,estimated_effort=effort,dependencies=deps or [],source=source,status=GoalStatus.APPROVED);return g

def test_owner_priority_dominates_model_score_and_pressure(tmp_path):
 gen=AutonomousGoalGenerator(str(tmp_path/'g.db'));critical=approved('Owner',GoalPriority.CRITICAL,.1,'high',source=GoalSource.OWNER_DIRECTIVE);normal=approved('Model',GoalPriority.NORMAL,1.0,'low')
 gen.add_goal(critical);gen.add_goal(normal)
 r=AutonomyResourceAllocator().select(gen,{'ram_used_percent':95})
 assert r['goal'].goal_id==critical.goal_id
 assert r['selected']['resource_penalty']>0

def test_incomplete_dependencies_make_goal_ineligible(tmp_path):
 gen=AutonomousGoalGenerator(str(tmp_path/'g.db'));dep=AutonomousGoal(title='Dependency',status=GoalStatus.APPROVED);goal=approved('Blocked',GoalPriority.CRITICAL,1,deps=[dep.goal_id]);fallback=approved('Ready',GoalPriority.NORMAL,.1)
 for g in (dep,goal,fallback):gen.add_goal(g)
 r=AutonomyResourceAllocator().select(gen,{})
 # Dependency itself is ready and may run, but dependent goal cannot.
 assert r['goal'].goal_id!=goal.goal_id
 blocked=next(x for x in r['rankings'] if x['goal_id']==goal.goal_id)
 assert blocked['eligible'] is False
