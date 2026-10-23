"""Opt-in current UI-origin HTTP/Spring/queue/MCP workflow on a fresh demo stack."""
import os
import time
from uuid import uuid4
import httpx
import pytest

pytestmark=pytest.mark.skipif(os.getenv('RUN_LIVE_STACK')!='1',reason='Live demo stack not explicitly enabled')


def mutation(client,path,body,**headers):
    response=client.get('/api/auth/csrf');response.raise_for_status();token=response.json()
    return client.post(path,json=body,headers={token['headerName']:token['token'],**headers})


def login(client,account):
    response=mutation(client,'/api/auth/demo-login',{'loginId':account});response.raise_for_status()
    assert response.json()['workflow_version']==2


def wait_status(client,problem_id,expected):
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        response=client.get('/api/v2/problems/'+problem_id);response.raise_for_status();workflow=response.json()
        if workflow['status']==expected:return workflow
        if workflow['status'] in {'FAILED','REJECTED','MANUAL_REVIEW','DONE'}:
            pytest.fail(f"Expected {expected}, got {workflow['status']}: {workflow.get('reason_code')}")
        time.sleep(.5)
    pytest.fail('Timed out waiting for current workflow')


def test_current_sequential_approval_and_independent_verification():
    base=os.getenv('LIVE_BASE_URL','http://localhost:8088')
    with httpx.Client(base_url=base,timeout=15) as requester, httpx.Client(base_url=base,timeout=15) as head, httpx.Client(base_url=base,timeout=15) as operator:
        assert requester.get('/api/v2/problems').status_code==401
        login(requester,'p2_a_requester');login(head,'p2_a_head');login(operator,'p2_a_operator')
        response=mutation(requester,'/api/v2/problems',{'schema_version':2,'platform':'GITHUB','contents':'GitHub Copilot 좌석을 신청합니다.'},**{'Idempotency-Key':str(uuid4())})
        response.raise_for_status();problem=response.json()['problem_id']
        waiting=wait_status(requester,problem,'WAITING_APPROVAL')
        assert waiting['current_step']==1 and waiting['total_steps']==2
        def decide(client,workflow):
            return mutation(client,f'/api/v2/problems/{problem}/decisions',{'action':'APPROVE',
                'expected_plan_hash':workflow['plan_hash'],'expected_plan_version':workflow['plan_version'],'reason':'통합 검증'})
        assert decide(requester,waiting).status_code==403
        assert decide(operator,waiting).status_code==403
        response=decide(head,waiting);response.raise_for_status();second=response.json()
        assert second['current_step']==2
        assert decide(head,second).status_code==403
        response=decide(operator,second);response.raise_for_status()
        done=wait_status(requester,problem,'DONE')
        assert done['result_type']=='ACCESS_VERIFIED' and done['verification_ok'] is True
        assert all(step['status']=='APPROVED' for step in done['approval_steps'])
        assert decide(operator,second).status_code==409
