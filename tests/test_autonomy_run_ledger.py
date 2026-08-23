from types import SimpleNamespace
from app.cognition.autonomy_run_ledger import AutonomyRunLedger
from app.cognition.autonomy_envelope import AutonomyEnvelopeStore
from app.cognition.periodic_autonomous_cycle import PeriodicAutonomousCycle,CycleStatus

def test_ledger_preserves_stage_separation(tmp_path):
 l=AutonomyRunLedger(tmp_path/'l.db'); l.record('c1','considered',goal_id='g1'); l.record('c1','approved_for_planning',goal_id='g1',details={'execution_authorized':False}); l.record('c1','blocked',goal_id='g1',reason='action approval required')
 stages=[e.stage for e in reversed(l.list(cycle_id='c1'))]
 assert stages==['considered','approved_for_planning','blocked']
 assert l.list(goal_id='g1')[1].details['execution_authorized'] is False

def test_disabled_cycle_records_skip(tmp_path,monkeypatch):
 envelope=AutonomyEnvelopeStore(tmp_path/'e.json'); envelope.update({'cycles_enabled':False})
 ledger=AutonomyRunLedger(tmp_path/'l.db')
 cycle=PeriodicAutonomousCycle(SimpleNamespace(),SimpleNamespace(),SimpleNamespace(),db_path=str(tmp_path/'c.db'),autonomy_envelope=envelope,run_ledger=ledger).run_cycle()
 assert cycle.status==CycleStatus.SKIPPED
 assert {e.stage for e in ledger.list(cycle_id=cycle.cycle_id)}=={'cycle_started','cycle_skipped'}
