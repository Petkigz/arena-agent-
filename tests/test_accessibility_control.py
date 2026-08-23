from unittest.mock import patch
from app.tools.accessibility_control import AccessibilityStore,AccessibilityControlTool

def test_semantic_resolution_requires_unique_target(tmp_path):
 s=AccessibilityStore(tmp_path/'a.db');s.ingest([{'role':'button','name':'Save','bounds':{'x':10,'y':20,'width':40,'height':20}}],interface='browser_accessibility',window_id='w1',evidence=['playwright accessibility tree'])
 r=s.resolve(role='button',name='Save',window_id='w1')
 assert r['success'] is True and r['target']['name']=='Save'
 s.ingest([{'role':'button','name':'Delete item'},{'role':'button','name':'Delete account'}],interface='browser_accessibility',window_id='w2',evidence=['tree'])
 assert s.resolve(role='button',name='Delete',window_id='w2')['ambiguous'] is True

def test_semantic_activation_uses_observed_bounds(tmp_path,monkeypatch):
 s=AccessibilityStore(tmp_path/'a.db');s.ingest([{'role':'button','name':'Submit','bounds':{'x':0,'y':0,'width':100,'height':40}}],interface='test',evidence=['native tree'])
 monkeypatch.setattr(AccessibilityControlTool,'store',s)
 with patch('app.tools.deep_os_controller.DeepOSController.mouse_click',return_value={'success':True}) as click:
  r=AccessibilityControlTool.activate_target('button','Submit')
 assert r['success'] is True and r['semantic_target_verified'] is True
 click.assert_called_once_with(50,20)

def test_no_bounds_means_no_fake_activation(tmp_path,monkeypatch):
 s=AccessibilityStore(tmp_path/'a.db');s.ingest([{'role':'button','name':'Submit'}],interface='test',evidence=['tree'])
 monkeypatch.setattr(AccessibilityControlTool,'store',s)
 assert AccessibilityControlTool.activate_target('button','Submit')['success'] is False
