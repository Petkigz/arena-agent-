import json,httpx
from desktop.backend_client import ArenaBackendClient

def test_desktop_autonomy_routes_and_stage_separation():
 calls=[]
 def handler(request):
  calls.append((request.method,request.url.path,json.loads(request.content) if request.content else None));return httpx.Response(200,json={'success':True})
 c=ArenaBackendClient();c._client=httpx.Client(transport=httpx.MockTransport(handler))
 c.create_autonomous_goal('Task','Description','critical');c.decide_autonomous_goal('g/1',True);c.defer_autonomous_goal('g/1');c.execute_next_autonomous_goal();c.update_autonomy_envelope({'limits_enabled':False});c.create_scheduled_directive('Daily','2026-08-24T09:00:00','daily','Africa/Kampala');c.update_schedule_status('s/1','paused');c.close()
 assert calls[0]==('POST','/owner-control/autonomous-goals',{'title':'Task','description':'Description','priority':'critical','approve_for_planning':True})
 assert calls[1]==('POST','/owner-control/autonomous-goals/g/1/decision',{'approved':True})
 assert calls[2][1].endswith('/defer') and calls[3][1].endswith('/execute-next')
 assert calls[4]==('PUT','/owner-control/autonomy-envelope',{'limits_enabled':False})
 assert calls[5][2]['timezone_name']=='Africa/Kampala'
 assert calls[6][1]=='/owner-control/autonomy-schedule/s/1/status'

def test_desktop_concurrency_budget_client():
 calls=[]
 def handler(request):
  calls.append((request.method,request.url.path,json.loads(request.content) if request.content else None));return httpx.Response(200,json={'success':True})
 c=ArenaBackendClient();c._client=httpx.Client(transport=httpx.MockTransport(handler))
 c.concurrency_budget();c.set_concurrency_budget(max_workers=6);c.set_concurrency_budget(enabled=False,max_workers=None);c.concurrency_receipts(limit=5);c.close()
 assert calls[0]==('GET','/owner-control/concurrency-budget',None)
 assert calls[1]==('PUT','/owner-control/concurrency-budget',{'max_workers':6})
 assert calls[2]==('PUT','/owner-control/concurrency-budget',{'enabled':False,'max_workers':None})
 assert calls[3][0]=='GET' and calls[3][1].startswith('/owner-control/concurrency-budget/receipts')
