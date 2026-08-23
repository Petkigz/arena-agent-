import sys
from types import SimpleNamespace
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

def test_linux_atspi_capture_is_bounded_and_evidenced(tmp_path,monkeypatch):
 class Node:
  name='Save';childCount=0
  def getRoleName(self):return 'push button'
  def queryComponent(self):return SimpleNamespace(getExtents=lambda coords:SimpleNamespace(x=1,y=2,width=30,height=10))
 fake=SimpleNamespace(DESKTOP_COORDS=0,Registry=SimpleNamespace(getDesktop=lambda index:Node()))
 monkeypatch.setitem(sys.modules,'pyatspi',fake);monkeypatch.setattr('platform.system',lambda:'Linux')
 monkeypatch.setattr(AccessibilityControlTool,'store',AccessibilityStore(tmp_path/'native.db'))
 result=AccessibilityControlTool.capture_desktop(max_nodes=5)
 assert result['success'] is True and result['engine']=='linux_atspi'
 assert result['nodes'][0]['bounds']['x']==1
 assert 'native accessibility tree' in result['nodes'][0]['evidence'][0]
