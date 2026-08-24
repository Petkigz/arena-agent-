import sys
from types import SimpleNamespace
from app.tools.browser_automation import BrowserAutomation
from app.cognition.browser_grounding import BrowserGroundingStore
class Page:
 url='https://service.test/success'
 def __init__(self):self.submitted=False
 def goto(self,*a,**k):pass
 def set_input_files(self,*a):pass
 def click(self,*a):self.submitted=True
 def wait_for_selector(self,*a,**k):pass
 def is_visible(self,*a):return self.submitted
 def title(self):return 'Uploaded'
class Browser:
 def new_page(self):return Page()
 def close(self):pass
class Ctx:
 def __enter__(self):return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **k:Browser()))
 def __exit__(self,*a):return False

def test_upload_requires_observed_remote_success(tmp_path,monkeypatch):
 source=tmp_path/'report.txt';source.write_text('report')
 monkeypatch.setitem(sys.modules,'playwright.sync_api',SimpleNamespace(sync_playwright=lambda:Ctx()))
 monkeypatch.setattr(BrowserAutomation,'GROUNDING',BrowserGroundingStore(tmp_path/'b.db'))
 r=BrowserAutomation.upload_file('https://service.test','input','%s'%source,'button','div.success')
 assert r['success'] is True and r['environment_verified'] is True
 assert r['rollback_supported'] is False and r['auth_state']=='unknown'

def test_preexisting_success_marker_blocks_submission(tmp_path,monkeypatch):
 source=tmp_path/'r';source.write_text('x')
 class Pre(Page):
  def is_visible(self,*a):return True
 class PreBrowser(Browser):
  def new_page(self):return Pre()
 class PreCtx(Ctx):
  def __enter__(self):return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **k:PreBrowser()))
 monkeypatch.setitem(sys.modules,'playwright.sync_api',SimpleNamespace(sync_playwright=lambda:PreCtx()))
 r=BrowserAutomation.upload_file('https://service.test','input',str(source),'button','success')
 assert r['request_success'] is False and r['side_effects'] is False

def test_upload_failure_preserves_side_effect_uncertainty(tmp_path,monkeypatch):
 source=tmp_path/'r';source.write_text('x')
 class Bad(Page):
  def wait_for_selector(self,*a,**k):raise RuntimeError('no confirmation')
 class BadBrowser(Browser):
  def new_page(self):return Bad()
 class BadCtx(Ctx):
  def __enter__(self):return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **k:BadBrowser()))
 monkeypatch.setitem(sys.modules,'playwright.sync_api',SimpleNamespace(sync_playwright=lambda:BadCtx()))
 r=BrowserAutomation.upload_file('https://service.test','input',str(source),'button','success')
 assert r['success'] is False and r['verification_unknown'] is True and r['side_effects'] is True
