"""Small offline v2 flow checks; no paid model, broker or external SaaS calls."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4
import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from unlockops.common.workflow_contracts import AccessJob, ReclaimJob, GrantPlanV2
from unlockops.common.runtime import WorkflowTools
from unlockops.common.models import ToolFailure
from unlockops.common.settings import settings
from unlockops_rag.revisions import revision_index
from unlockops_worker.runtime import parse_delivery, checkpoint_config, run_job
from unlockops_mcp.workflow_backend import WorkflowBackend

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((ROOT / 'contracts/phase2/examples/vectors.json').read_text())
PLAN = VECTORS['valid'][0]['payload']
CANDIDATE = json.loads((ROOT / 'contracts/phase2/examples/candidate.json').read_text())
CATALOG = json.loads((ROOT / 'data/phase2/catalog.json').read_text())


def policy():
    content = (ROOT / 'data/phase2/company-a-policy.md').read_text()
    import hashlib
    return {'policy_id': PLAN['policy_id'], 'company_id': PLAN['company_id'], 'revision': 1,
            'doc_id': 'P2-A-POLICY', 'article': 'POL-06', 'source_hash': hashlib.sha256(content.encode()).hexdigest(), 'content': content}


def policy_reply(mode='exact'):
    p = policy()
    index = revision_index(p['company_id'], p['policy_id'], p['revision'], p['doc_id'], p['source_hash'], p['content'])
    return {'source_hash': p['source_hash'], 'evidence': index.read(), 'retrieval_mode': mode}


def context(job, execution=False):
    p = deepcopy(PLAN)
    workflow = {'schema_version': 2, 'task_type': 'ACCESS_REQUEST', 'problem_id': str(job.problem_id),
        'status': 'EXECUTING' if execution else 'RECEIVED', 'reason_code': 'HUMAN_APPROVED' if execution else None,
        'message': '진행 중', 'current_step': None, 'total_steps': 2 if execution else 0,
        'approval_steps': [{'step': i+1, 'approver_id': actor, 'status': 'APPROVED', 'acted_at': '2026-10-22T09:00:00+09:00'} for i, actor in enumerate(p['approver_ids'])] if execution else []}
    return {'schema_version': 2, 'problem': {'id': str(job.problem_id), 'company_id': p['company_id'], 'requester_id': p['requester_id'],
        'platform': p['platform'], 'contents': 'Snowflake ANALYST 권한을 신청합니다.', 'status': workflow['status'],
        'active_job_event_id': str(job.event_id), 'requested_entitlement_id': p['entitlement_id'], 'resource_id': p['resource_id'],
        'plan': p if execution else None, 'plan_hash': job.plan_hash, 'approved_plan_hash': job.plan_hash, 'idempotency_key': job.idempotency_key},
        'requester': {'id': p['requester_id'], 'company_id': p['company_id'], 'department_id': CATALOG['companies']['A']['department_id'],
        'employment_status': 'ACTIVE', 'job_grade': '사원', 'job_family': 'DEV'},
        'entitlements': [{'id': p['entitlement_id'], 'resource_id': p['resource_id'], 'platform': p['platform'], 'name': 'Snowflake', 'external_id': 'p2-a-snowflake', 'kind': 'ROLE', 'code': 'ANALYST'}],
        'facts': [], 'policies': [policy()], 'workflow': workflow}


class AccessTools:
    def __init__(self, job, execution=False, verified=True):
        self.job, self.execution, self.verified, self.calls = job, execution, verified, []
    async def call(self, name, args):
        self.calls.append(name)
        if name == 'get_access_request_context': return context(self.job, self.execution)
        if name in {'search_workflow_policy', 'read_workflow_policy'}: return policy_reply()
        if name == 'assess_access_request': return {'status': 'WAITING_APPROVAL', 'reason': 'ELIGIBLE', 'message': '승인이 필요합니다.', 'plan': deepcopy(PLAN), 'evidence': policy_reply()['evidence']}
        if name == 'execute_access_plan': return {'schema_version': 2, 'executed': True, 'problem_id': str(self.job.problem_id), 'assignment_id': str(uuid4()),
            'plan_hash': self.job.plan_hash, 'idempotency_key': self.job.idempotency_key, 'charged_amount': PLAN['monthly_amount'], 'currency': PLAN['currency']}
        if name == 'verify_access_plan': return {'schema_version': 2, 'problem_id': str(self.job.problem_id), 'receipt_exists': True, 'verification_ok': self.verified, 'source': 'mock_entitlement_memberships'}
        raise AssertionError(name)


def access_job(execute=False):
    return AccessJob(schema_version=2, event_id=uuid4(), job_type='EXECUTE' if execute else 'ANALYZE', problem_id=PLAN['problem_id'],
        plan_hash=GrantPlanV2.model_validate(PLAN).digest() if execute else None, idempotency_key='approved-execution' if execute else None)


async def test_analysis_and_durable_redelivery_do_not_repeat_tools(tmp_path, monkeypatch):
    from unlockops.access import graph
    from unlockops.common import reporting
    monkeypatch.setattr(reporting, 'settings', replace(settings, mode='demo'))
    async def interpret(*args):
        from unlockops.common.models import Intent
        return Intent(request_type='ACCESS_REQUEST', requested_role='ANALYST')
    monkeypatch.setattr(graph, 'interpret', interpret)
    job = access_job(); tools = AccessTools(job); path = str(tmp_path / 'v2.sqlite')
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        result = await run_job(job, saver, tools)
    assert result['result']['status'] == 'WAITING_APPROVAL'
    assert result['result']['plan_hash'] == GrantPlanV2.model_validate(PLAN).digest()
    assert result['job_event_id'] == str(job.event_id)
    assert [s['status'] for s in result['result']['approval_steps']] == ['WAITING', 'PENDING']
    before = list(tools.calls)
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        assert await run_job(job, saver, tools) == result
    assert tools.calls == before
    assert 'execute_access_plan' not in tools.calls
    renewed = job.model_copy(update={'event_id': uuid4()})
    assert checkpoint_config(renewed) != checkpoint_config(job)


@pytest.mark.parametrize('platform,code,kind', [('FIGMA', 'EDITOR_SEAT', 'SEAT'), ('JIRA', 'DEVELOPER', 'ROLE')])
async def test_unmatched_viewer_role_requires_manual_review(platform, code, kind, monkeypatch):
    from unlockops.access import graph, selection
    from unlockops.common.models import Intent
    # Even LLM mode cannot replace an unresolved explicit role with another permission.
    monkeypatch.setattr(selection, 'settings', replace(settings, mode='llm'))
    def forbidden_model():
        pytest.fail('Mismatched roles must not reach LLM selection')
    monkeypatch.setattr(selection, 'model', forbidden_model)
    async def interpret(*args):
        return Intent(request_type='ACCESS_REQUEST', requested_role='Viewer')
    monkeypatch.setattr(graph, 'interpret', interpret)
    job = access_job()
    ctx = context(job)
    ctx['problem'].update(platform=platform, contents=f'{platform} Viewer 권한을 신청합니다.', requested_entitlement_id=None)
    ctx['entitlements'][0].update(platform=platform, name=platform, code=code, kind=kind)
    class ViewerTools(AccessTools):
        async def call(self, name, args):
            if name == 'get_access_request_context':
                self.calls.append(name)
                return ctx
            return await super().call(name, args)
    tools = ViewerTools(job)
    result = await run_job(job, InMemorySaver(), tools)
    assert (result['result']['status'], result['result']['reason_code']) == ('MANUAL_REVIEW', 'OUT_OF_SCOPE')
    assert 'assess_access_request' not in tools.calls
    assert 'execute_access_plan' not in tools.calls
    # Exact roles and the existing Admin -> Read proposal remain available.
    assert await selection.select_entitlement(ctx, {'requested_role': code.lower()}) == (PLAN['entitlement_id'], False)
    ctx['entitlements'][0]['code'] = 'READ'
    ctx['problem'].update(platform='GITHUB', contents='GitHub 저장소 Admin 요청, 목적은 코드 열람뿐입니다.')
    assert await selection.select_entitlement(ctx, {'requested_role': 'Admin'}) == (PLAN['entitlement_id'], True)
    ctx['problem']['contents']='GitHub 저장소 Admin 권한으로 배포 설정을 수정해야 합니다.'
    with pytest.raises(ToolFailure):
        await selection.select_entitlement(ctx, {'requested_role': 'Admin'})


async def test_execution_requires_fresh_verification_and_preserves_mismatch(monkeypatch):
    from unlockops.access import execution
    monkeypatch.setattr(execution, 'settings', replace(settings, max_verification_attempts=1))
    for verified, status in [(True, 'DONE'), (False, 'FAILED')]:
        job = access_job(True); tools = AccessTools(job, True, verified)
        saver = InMemorySaver()
        result = await run_job(job, saver, tools)
        assert result['result']['status'] == status
        assert result['result']['verification_ok'] is verified
        assert tools.calls == ['get_access_request_context', 'execute_access_plan', 'verify_access_plan']
        assert await run_job(job, saver, tools) == result
        assert tools.calls.count('execute_access_plan') == 1


@pytest.mark.parametrize('fault', [None, 'article', 'revision'])
async def test_approval_report_uses_observed_budget_and_rejects_misbound_sources(monkeypatch, fault):
    from unlockops.access import graph
    from unlockops.common import reporting
    from unlockops.common.models import Intent
    monkeypatch.setattr(reporting, 'settings', replace(settings, mode='demo'))
    async def interpret(*args):
        return Intent(request_type='ACCESS_REQUEST', requested_role='ANALYST')
    monkeypatch.setattr(graph, 'interpret', interpret)
    job = access_job()
    class ObservedTools(AccessTools):
        async def call(self, name, args):
            result = await super().call(name, args)
            if name == 'read_workflow_policy' and fault == 'article':
                result['evidence'][0]['article'] = 'POL-06 제5조 — 회수 후보'
            if name == 'assess_access_request':
                if fault == 'revision':
                    result['plan']['policy_revision'] += 1
                result['review_facts'] = {
                    'checked_at': '2026-10-23T11:00:00+09:00', 'resource_name': 'Snowflake',
                    'entitlement_code': 'ANALYST', 'entitlement_kind': 'ROLE', 'access_scope': 'GENERAL', 'tf_member': None,
                    'monthly_amount': PLAN['monthly_amount'], 'currency': PLAN['currency'], 'remaining_budget': '150.00',
                    'price_source_kind': 'SYNTHETIC_CONTRACT',
                }
            return result
    tools = ObservedTools(job)
    result = await run_job(job, InMemorySaver(), tools)
    if fault:
        assert (result['result']['status'], result['result']['reason_code']) == ('MANUAL_REVIEW', 'MISSING_SOURCE_EVIDENCE')
    else:
        assert result['result']['status'] == 'WAITING_APPROVAL'
        assert '150.00 → 30.00 USD' in result['result']['message']
        assert '회수 후보' not in '\n'.join(e['article'] for e in result['policy_evidence'])
    assert 'execute_access_plan' not in tools.calls


class ReclaimTools:
    def __init__(self, job, duplicate=False):
        self.job, self.duplicate, self.calls = job, duplicate, []
        self.snapshot = str(uuid4())
    async def call(self, name, args):
        self.calls.append(name)
        p = policy()
        if name == 'get_reclaim_check_context': return {'schema_version': 2, 'run_id': str(self.job.run_id), 'job_event_id': str(self.job.event_id),
            'snapshot_id': self.snapshot, 'as_of': CATALOG['as_of'], 'expected_count': 2, 'context': {'policy': p, 'policy_hash': p['source_hash'], 'rules': []}}
        if name in {'search_workflow_policy', 'read_workflow_policy'}: return policy_reply()
        if name == 'list_revocation_candidates':
            row = deepcopy(CANDIDATE)
            if args['cursor'] and not self.duplicate:
                row.update(assignment_id=str(uuid4()), candidate_status=None, review_required=True)
            return {'run_id': str(self.job.run_id), 'snapshot_id': self.snapshot, 'as_of': CATALOG['as_of'], 'expected_count': 2,
                    'next_cursor': 'page-2' if args['cursor'] is None else None, 'items': [row]}
        if name == 'get_reclaim_notification_history': return {'items': []}
        raise AssertionError(name)


async def test_reclaim_requires_all_unique_rows_and_never_claims_done(monkeypatch):
    from unlockops.common import reporting
    monkeypatch.setattr(reporting, 'settings', replace(settings, mode='demo'))
    for duplicate in [False, True]:
        job = ReclaimJob(schema_version=2, event_id=uuid4(), run_id=uuid4(), trigger='MANUAL_DEMO', scope_key='test', scheduled_for=CATALOG['as_of'])
        tools = ReclaimTools(job, duplicate)
        result = await run_job(job, InMemorySaver(), tools)
        assert result['result']['status'] != 'DONE'
        if duplicate:
            assert result['result']['status'] == 'FAILED'
            assert result['result']['scan_complete'] is False
        else:
            assert result['result']['status'] == 'EXECUTING'
            assert result['result']['needs_review_count'] == 1
            assert result['result']['scan_complete'] is True
            assert len(result['targets']) == 2
        assert not {'execute_access_plan', 'grant_permission'} & set(tools.calls)
        with pytest.raises(ToolFailure, match='not allowed'):
            await WorkflowTools(tools, job).call('execute_access_plan', {})


def test_queue_boundary_rejects_wrong_versions_and_commands():
    job = access_job()
    body = job.model_dump_json().encode()
    assert parse_delivery(body, 'v2.analysis') == job
    for queue in ['analysis', 'execution', 'v2.execution']:
        with pytest.raises(ValueError): parse_delivery(body, queue)
    raw = job.model_dump(mode='json'); raw['schema_version'] = 3
    with pytest.raises(ValueError): parse_delivery(json.dumps(raw).encode(), 'v2.analysis')


async def test_v4_natural_requests_resolve_only_the_selected_platform(monkeypatch):
    from unlockops.access.intent import interpret_v4, scoped_text
    from unlockops.access.selection import select_entitlement
    from unlockops.access import planner
    monkeypatch.setattr(planner, 'settings', replace(settings, mode='demo'))
    cases=json.loads((ROOT/'data/phase2/scenarios-v4.json').read_text())['scenarios']
    for case in cases:
        if case['id'].startswith('R-') or case['id'] in {'B-02','B-03','B-05'}: continue
        item=next(x for x in CATALOG['catalog'] if x['company']==case['company'] and x['platform']==case['platform'])
        ctx={'problem':{'platform':case['platform'],'contents':case['input_text'],'resource_id':item['resource_id']},
             'entitlements':[{**item,'id':item['entitlement_id'],'name':'test resource','external_id':'test-resource'}]}
        intent=await interpret_v4(case['input_text'],case['platform'])
        assert await select_entitlement(ctx,intent.model_dump())==(item['entitlement_id'],False),case['id']
    text='GitHub Copilot 좌석과 Jira 프로젝트 Admin 권한을 신청합니다.'
    assert 'Jira' not in scoped_text(text,'GITHUB')
    assert (await interpret_v4(text,'GITHUB')).requested_role=='Seat'


async def test_v4_reclaim_narrates_only_new_confirmed_candidates(monkeypatch):
    from unlockops.reclaim import reporting as graph
    calls=[]
    async def spy(facts,evidence,template):
        calls.append(facts)
        return template,'template'
    monkeypatch.setattr(graph,'report',spy)
    excluded={**CANDIDATE,'candidate_status':'EXCLUDED','exclusion_reason_code':'ACTIVE_OTHER_TF'}
    unknown={**CANDIDATE,'assignment_id':str(uuid4()),'candidate_status':None,'review_required':True}
    state={'targets':[excluded,unknown],'policy_evidence':policy_reply()['evidence'],'history':[]}
    await graph.compose_reports(state)
    assert calls==[]
    state.update(targets=[CANDIDATE],history=[{'assignment_id':CANDIDATE['assignment_id'],'candidate_status':'PENDING_REVIEW','notified_at':CATALOG['as_of']}])
    await graph.compose_reports(state)
    assert calls==[]
    state['history']=[]
    await graph.compose_reports(state)
    assert len(calls)==1


def test_phase2_http_adapter_preserves_verification_and_scoped_policy():
    job = access_job(True); calls = []
    def handle(request):
        calls.append(request)
        assert request.headers['authorization'] == 'Bearer internal-test'
        if request.url.path.endswith('/context'): return httpx.Response(200, json=context(job, True))
        return httpx.Response(200, json={'schema_version': 2, 'problem_id': str(job.problem_id), 'receipt_exists': True, 'verification_ok': False, 'source': 'mock_entitlement_memberships'})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        backend = WorkflowBackend(client, base_url='http://backend', token='internal-test')
        value = backend.invoke('get_access_request_context', {'problem_id': str(job.problem_id)})
        assert value['problem']['id'] == str(job.problem_id)
        args = {'problem_id': str(job.problem_id), 'job_event_id': str(job.event_id), 'plan_hash': job.plan_hash, 'idempotency_key': job.idempotency_key}
        assert backend.invoke('verify_access_plan', args)['verification_ok'] is False
        from unlockops_mcp.policy_tools import scoped_index
        with pytest.raises(ToolFailure): scoped_index(backend, 'ACCESS_REQUEST', str(job.problem_id), '0' * 64)
    assert calls[0].method == 'GET'
