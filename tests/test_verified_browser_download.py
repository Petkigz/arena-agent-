import sys
from types import SimpleNamespace
from unittest.mock import patch
from app.tools.browser_automation import BrowserAutomation
from app.cognition.browser_grounding import BrowserGroundingStore
from app.cognition.execution_control import ExecutionControlRegistry

class Download:
 suggested_filename='../report.txt'
 def save_as(self,path):open(path,'wb').write(b'exact download')
class Expect:
 value=Download()
 def __enter__(self):return self
 def __exit__(self,*args):return False
class Page:
 url='https://example.test/file'
 def goto(self,*a,**k):pass
 def click(self,*a,**k):pass
 def expect_download(self,**k):return Expect()
 def title(self):return 'Files'
class Browser:
 def new_page(self):return Page()
 def close(self):pass
class Playwright:
 chromium=SimpleNamespace(launch=lambda **k:Browser())
class Context:
 def __enter__(self):return Playwright()
 def __exit__(self,*a):return False

def test_browser_download_verifies_artifact_and_receipt(tmp_path,monkeypatch):
 fake=SimpleNamespace(sync_playwright=lambda:Context());monkeypatch.setitem(sys.modules,'playwright.sync_api',fake)
 monkeypatch.setattr(BrowserAutomation,'DOWNLOADS_DIR',tmp_path/'downloads');monkeypatch.setattr(BrowserAutomation,'GROUNDING',BrowserGroundingStore(tmp_path/'browser.db'))
 result=BrowserAutomation.download_file('https://example.test','a.download')
 assert result['success'] is True and result['environment_verified'] is True
 assert result['download_path'].startswith(str(tmp_path/'downloads')) and '..' not in result['download_path']
 registry=ExecutionControlRegistry(tmp_path/'exec.db');record=registry.begin('p','browser_download');receipt=registry.create_rollback_receipt(record.execution_id,'browser_download',{},result)
 assert receipt.compensation_action=='remove_verified_copy'

def test_download_destination_never_overwrites(tmp_path,monkeypatch):
 monkeypatch.setattr(BrowserAutomation,'DOWNLOADS_DIR',tmp_path);(tmp_path/'x.txt').write_text('owner')
 destination=BrowserAutomation._download_destination('x.txt')
 assert destination.name!='x.txt' and (tmp_path/'x.txt').read_text()=='owner'
