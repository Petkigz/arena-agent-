from types import SimpleNamespace
from datetime import datetime,timezone
from app.cognition.autonomy_envelope import AutonomyEnvelopeStore

def policy(mode='bounded_autonomy',paused=False): return SimpleNamespace(mode=SimpleNamespace(value=mode),paused=paused)
def test_owner_envelope_persists_and_clamps(tmp_path):
 s=AutonomyEnvelopeStore(tmp_path/'a.json'); p=s.update({'max_goal_executions_per_cycle':0,'max_cycle_seconds':30})
 assert p.max_goal_executions_per_cycle==0
 assert AutonomyEnvelopeStore(tmp_path/'a.json').get().max_cycle_seconds==30

def test_pause_and_suggest_mode_block_execution(tmp_path):
 s=AutonomyEnvelopeStore(tmp_path/'a.json')
 assert s.evaluate(owner_policy=policy(paused=True))['cycle_allowed'] is False
 d=s.evaluate(owner_policy=policy('suggest_only'))
 assert d['cycle_allowed'] is True and d['execution_allowed'] is False

def test_cooldown_blocks_duplicate_cycle(tmp_path):
 s=AutonomyEnvelopeStore(tmp_path/'a.json'); now=datetime.now(timezone.utc)
 d=s.evaluate(owner_policy=policy(),last_started_at=now.isoformat(),now=now)
 assert d['cycle_allowed'] is False
 assert 'cooldown' in d['reasons'][0].lower()
