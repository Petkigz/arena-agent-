from unittest.mock import patch
from app.cognition.os_grounding import OSGroundingStore
class P:
 def __init__(self,pid,name,exe):self.info={'pid':pid,'name':name,'exe':exe}
def test_exact_process_and_window_grounding(tmp_path):
 s=OSGroundingStore(tmp_path/'o.db')
 with patch('app.cognition.os_grounding.psutil.process_iter',return_value=[P(42,'editor','/bin/editor')]),patch('app.cognition.os_grounding.psutil.pid_exists',return_value=True):
  r=s.observe_application('editor',executable_path='/bin/editor',task_id='t1');assert r['verified'] is True
  g=s.bind_window(r['grounding']['grounding_id'],window_id='w1',title='Report',display_id='d1',region={'x':0,'y':0,'width':100,'height':100},evidence=['native window probe'])
  resolved=s.resolve_target('editor',require_window=True)
 assert g.pid==42 and resolved['success'] is True
 assert 'executable_path_exact_match' in g.evidence

def test_ambiguous_name_is_not_targeted(tmp_path):
 s=OSGroundingStore(tmp_path/'o.db')
 with patch('app.cognition.os_grounding.psutil.process_iter',return_value=[P(1,'editor','/a'),P(2,'editor','/b')]):
  r=s.observe_application('editor')
 assert r['success'] is False and r['ambiguous'] is True
