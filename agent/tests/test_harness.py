"""Workflow tool scopes, retry budgets and execution authorization survive consolidation."""
from dataclasses import replace
from uuid import uuid4
import pytest
from unlockops.common import runtime
from unlockops.common.models import ToolFailure
from unlockops.common.runtime import WorkflowTools
from test_workflows import access_job, AccessTools


@pytest.mark.parametrize('name,args,code', [
    ('execute_access_plan', {}, 'TOOL_SCOPE'),
    ('get_access_request_context', {'problem_id': str(uuid4())}, 'REQUEST_SCOPE'),
    ('search_workflow_policy', {'task_type': 'RECLAIM_SCAN', 'work_id': str(uuid4()), 'query': '권한'}, 'REQUEST_SCOPE'),
])
async def test_analysis_cannot_write_or_switch_work_items(name,args,code):
    job = access_job(); tools = AccessTools(job)
    with pytest.raises(ToolFailure) as error: await WorkflowTools(tools, job).call(name,args)
    assert error.value.code == code and tools.calls == []


@pytest.mark.parametrize('field,value', [('plan_hash', '0'*64), ('idempotency_key','other-key'), ('job_event_id',str(uuid4()))])
async def test_execution_cannot_change_the_approved_identity(field,value):
    job = access_job(True); tools = AccessTools(job, True)
    args = {'problem_id':str(job.problem_id), 'job_event_id':str(job.event_id), 'plan_hash':job.plan_hash, 'idempotency_key':job.idempotency_key}
    with pytest.raises(ToolFailure): await WorkflowTools(tools,job).call('execute_access_plan',{**args,field:value})
    assert tools.calls == []


async def test_transient_retries_preserve_arguments_and_obey_total_budget(monkeypatch):
    monkeypatch.setattr(runtime, 'settings', replace(runtime.settings, max_tools=2))
    async def no_wait(delay): pass
    monkeypatch.setattr(runtime.asyncio,'sleep',no_wait)
    seen=[]
    class Tools:
        async def call(self,name,args):
            seen.append((name,dict(args)))
            raise ToolFailure('UPSTREAM_UNAVAILABLE','temporary',True)
    job=access_job(True); scoped=WorkflowTools(Tools(),job)
    args={'problem_id':str(job.problem_id),'job_event_id':str(job.event_id),'plan_hash':job.plan_hash,'idempotency_key':job.idempotency_key}
    with pytest.raises(ToolFailure) as error: await scoped.call('execute_access_plan',args,retry=True)
    assert error.value.code=='TOOL_BUDGET' and len(seen)==2 and seen[0]==seen[1]
