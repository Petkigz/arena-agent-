from app.cognition.browser_grounding import BrowserGroundingStore

def test_unique_tab_and_owner_takeover_boundary(tmp_path):
 s=BrowserGroundingStore(tmp_path/'b.db');t=s.observe_tab(session_id='s1',url='https://example.com',title='Example',evidence=['page.url','page.title'])
 assert s.resolve(url=t.url,session_id='s1')['success'] is True
 s.set_owner_takeover(t.tab_id,True)
 r=s.resolve(url=t.url,session_id='s1')
 assert r['success'] is False and r['owner_takeover'] is True

def test_ambiguous_tabs_and_transfer_evidence(tmp_path):
 s=BrowserGroundingStore(tmp_path/'b.db')
 a=s.observe_tab(session_id='s1',url='https://x',title='X',evidence=['tree'])
 s.observe_tab(session_id='s1',url='https://x',title='X',evidence=['tree'])
 assert s.resolve(url='https://x',session_id='s1')['ambiguous'] is True
 event=s.record_event(a.tab_id,'download','completed',evidence=['download path exists','hash matched'])
 assert event['state']=='completed'

def test_auth_state_is_never_inferred(tmp_path):
 s=BrowserGroundingStore(tmp_path/'b.db');t=s.observe_tab(session_id='s',url='https://private',title='Portal',profile_type='owner_profile',evidence=['owner attached profile'])
 assert t.auth_state=='unknown'
