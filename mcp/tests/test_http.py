"""Real MCP HTTP discovery, authentication, schemas and structured failures."""
import asyncio
from contextlib import contextmanager
import httpx
import jsonschema
import pytest
from starlette.testclient import TestClient
from unlockops.common.settings import settings
from unlockops.common.contracts import INPUTS, OUTPUTS
from unlockops_mcp.auth import TokenAuth
from unlockops_mcp.contracts import ContractMCP
from unlockops_mcp import business, policy
from unlockops_mcp.workflow_backend import WorkflowBackend

BUSINESS = {'get_access_request_context','assess_access_request','execute_access_plan','verify_access_plan',
            'get_reclaim_check_context','list_revocation_candidates','get_reclaim_notification_history'}
POLICY = {'search_workflow_policy','read_workflow_policy'}
ID = '10000000-0000-0000-0000-000000000001'
ARGS = {'problem_id':ID,'job_event_id':ID,'plan_hash':'a'*64,'idempotency_key':'approved-key'}
VALID = {'schema_version':2,'problem_id':ID,'receipt_exists':True,'verification_ok':False,'source':'mock_entitlement_memberships'}


@contextmanager
def rpc(module):
    fresh = ContractMCP('unlockops-test',host='127.0.0.1',stateless_http=True,json_response=True)
    definitions = {tool.name:tool for tool in asyncio.run(module.mcp.list_tools())}
    for name, fn in module.tools.items(): fresh.add_tool(fn, annotations=definitions[name].annotations)
    with TestClient(TokenAuth(fresh.streamable_http_app()),base_url='http://127.0.0.1:8000') as client:
        def request(method,params):
            r=client.post('/mcp',headers={'Authorization':'Bearer '+settings.mcp_token,'Accept':'application/json, text/event-stream'},
                json={'jsonrpc':'2.0','id':1,'method':method,'params':params})
            assert r.status_code==200
            return r.json()['result']
        yield request


@pytest.mark.parametrize('module,names',[(business,BUSINESS),(policy,POLICY)])
def test_authenticated_discovery_exposes_only_current_tools(module,names):
    with TestClient(TokenAuth(module.mcp.streamable_http_app())) as client:
        assert client.get('/health').status_code==401
        assert client.get('/health',headers={'Authorization':'Bearer '+settings.mcp_token}).json()=={'status':'UP'}
    with rpc(module) as request:
        tools=request('tools/list',{})['tools']
    assert {t['name'] for t in tools}==names
    for tool in tools:
        name=tool['name']
        assert tool['inputSchema']==INPUTS[name].model_json_schema()
        assert tool['outputSchema']==OUTPUTS[name].model_json_schema()
        assert tool['annotations']['readOnlyHint']==(name!='execute_access_plan')
        assert tool['annotations']['idempotentHint'] is True


@pytest.mark.parametrize('name,args',[
    ('get_access_request_context',{'problem_id':'invalid'}),
    ('get_access_request_context',{'problem_id':ID,'employee_id':ID}),
    ('execute_access_plan',{**ARGS,'plan_hash':'invalid'}),
    ('verify_access_plan',{**ARGS,'idempotency_key':''}),
])
def test_invalid_input_is_rejected_before_spring(monkeypatch,name,args):
    monkeypatch.setattr(WorkflowBackend,'invoke',lambda *a:pytest.fail('Invalid input reached Spring'))
    with rpc(business) as request: result=request('tools/call',{'name':name,'arguments':args})
    assert result['isError'] and result['structuredContent']['error']['code']=='INVALID_TOOL_INPUT'


@pytest.mark.parametrize('payload,code',[(VALID,None), ({'verification_ok':'false'},'INVALID_TOOL_OUTPUT'),
    (httpx.ConnectError('private URL'),'UPSTREAM_UNAVAILABLE'),(RuntimeError('private token'),'INTERNAL_TOOL_ERROR')])
def test_http_outputs_are_typed_and_provider_details_are_hidden(monkeypatch,payload,code):
    def invoke(*args):
        if isinstance(payload,Exception):raise payload
        return payload
    monkeypatch.setattr(WorkflowBackend,'invoke',invoke)
    with rpc(business) as request:
        result=request('tools/call',{'name':'verify_access_plan','arguments':ARGS})
    assert 'private' not in str(result)
    if code:
        assert result['isError'] and result['structuredContent']['error']['code']==code
    else:
        assert not result.get('isError') and result['structuredContent']['verification_ok'] is False
        jsonschema.validate(result['structuredContent'],OUTPUTS['verify_access_plan'].model_json_schema())


def test_removed_tools_are_not_callable():
    with rpc(business) as request:
        result=request('tools/call',{'name':'grant_permission','arguments':{'problem_id':ID,'idempotency_key':'key'}})
    assert result['isError'] and result['structuredContent']['error']['code']=='UNKNOWN_TOOL'
