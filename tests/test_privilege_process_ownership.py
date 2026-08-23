from unittest.mock import patch
from app.cognition.privilege_model import ProcessOwnershipStore,PrivilegeModel
from app.tools.process_manager import ProcessManager
class Proc:
 def username(self):return 'other-user'
 def name(self):return 'editor'
 def is_running(self):return True

def test_arena_launch_provenance_persists(tmp_path):
 s=ProcessOwnershipStore(tmp_path/'p.db')
 fake=type('P',(),{'username':lambda self:'owner','exe':lambda self:'/bin/editor','ppid':lambda self:1})()
 with patch('app.cognition.privilege_model.psutil.Process',return_value=fake):
  r=s.register_arena_launch(42,task_id='task1',executable_path='/bin/editor')
 assert r['arena_launched'] is True and r['task_id']=='task1'

def test_non_elevated_session_refuses_other_users_process(tmp_path):
 privilege=type('S',(),{'is_elevated':False,'to_dict':lambda self:{'is_elevated':False}})()
 with patch('app.tools.process_manager.psutil.Process',return_value=Proc()),patch('app.tools.process_manager.getpass.getuser',return_value='owner'),patch.object(PrivilegeModel,'probe',return_value=privilege):
  r=ProcessManager.kill_process(4242)
 assert r['success'] is False and 'other-user' in r['error']

def test_privilege_probe_has_evidence():
 p=PrivilegeModel.probe();assert p.evidence and isinstance(p.is_elevated,bool)
