"""Current analysis graph -> real MCP HTTP -> mocked Spring HTTP; no legacy engine."""
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from dataclasses import replace
import httpx
from langgraph.checkpoint.memory import InMemorySaver
from unlockops.common.workflow_contracts import AccessJob
from unlockops.common import reporting
from unlockops.access import planner
from unlockops_rag.revisions import revision_index
from unlockops_worker.runtime import run_job
from unlockops_mcp import business, policy
from unlockops_mcp.workflow_backend import WorkflowBackend
from unlockops_mcp.backend_client import BackendClient
from test_http import rpc

ROOT=Path(__file__).resolve().parents[2]


def test_current_graph_uses_only_current_tools_and_approved_plan_hash(monkeypatch):
    monkeypatch.setattr(reporting,'settings',replace(reporting.settings,mode='demo'))
    monkeypatch.setattr(planner,'settings',replace(planner.settings,mode='demo'))
    vectors=json.loads((ROOT/'contracts/phase2/examples/vectors.json').read_text())
    plan=vectors['valid'][0]['payload']
    job=AccessJob(schema_version=2,event_id=uuid4(),problem_id=plan['problem_id'],job_type='ANALYZE')
    content=(ROOT/'data/phase2/company-a-policy.md').read_text()
    revision={'company_id':plan['company_id'],'policy_id':plan['policy_id'],'revision':1,'doc_id':'P2-A-POLICY',
              'article':'POL-06','content':content,'source_hash':hashlib.sha256(content.encode()).hexdigest()}
    evidence=revision_index(revision['company_id'],revision['policy_id'],1,revision['doc_id'],revision['source_hash'],content).read()
    ctx={'schema_version':2,'problem':{'id':plan['problem_id'],'company_id':plan['company_id'],'requester_id':plan['requester_id'],
        'platform':plan['platform'],'contents':'Snowflake ANALYST 권한을 신청합니다.','status':'RECEIVED','active_job_event_id':str(job.event_id),
        'requested_entitlement_id':plan['entitlement_id'],'resource_id':plan['resource_id']},
        'requester':{'id':plan['requester_id'],'company_id':plan['company_id'],'department_id':str(uuid4()),
            'employment_status':'ACTIVE','job_grade':'사원','job_family':'DEV'},
        'entitlements':[{'id':plan['entitlement_id'],'code':'ANALYST','kind':'ROLE','resource_id':plan['resource_id'],
            'name':'Snowflake','external_id':'warehouse','platform':plan['platform']}],
        'facts':[],'policies':[revision],
        'workflow':{'schema_version':2,'problem_id':plan['problem_id'],'status':'RECEIVED','message':'접수'}}
    calls=[]
    def handle(request):
        calls.append(request.url.path)
        assert request.headers['Authorization']=='Bearer internal-test'
        if request.url.path.endswith('/context'):return httpx.Response(200,json=ctx)
        assert request.url.path.endswith('/assessment')
        assert json.loads(request.content)=={'job_event_id':str(job.event_id),'entitlement_id':plan['entitlement_id']}
        return httpx.Response(200,json={'status':'WAITING_APPROVAL','reason':'ELIGIBLE','message':'승인 필요','plan':plan,'evidence':evidence})
    client=BackendClient(httpx.Client(transport=httpx.MockTransport(handle)),base_url='http://backend',token='internal-test')
    def request(self,*args,**kwargs):return client._request(*args,**kwargs)
    monkeypatch.setattr(WorkflowBackend,'_request',request)
    with rpc(business) as b, rpc(policy) as p:
        class Tools:
            async def call(self,name,args):
                call=p if name in {'read_workflow_policy','search_workflow_policy'} else b
                result=call('tools/call',{'name':name,'arguments':args})
                assert not result.get('isError'),result
                return result['structuredContent']
        result=asyncio.run(run_job(job,InMemorySaver(),Tools()))
    assert result['result']['status']=='WAITING_APPROVAL'
    assert result['result']['plan_hash']==vectors['plan_sha256']
    assert len(result['result']['approval_steps'])==2
    assert all('/internal/v2/problems/' in path for path in calls)
    assert not any(path.endswith('/execute') for path in calls)
